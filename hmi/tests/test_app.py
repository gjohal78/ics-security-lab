"""Unit tests for the HMI backend (no PLC or network needed)."""

import os

os.environ["HMI_NO_AUTOSTART"] = "1"  # don't build the real app at import

import pytest  # noqa: E402

from app import PlcPoller, create_app, decode  # noqa: E402


# --- Fake Modbus client ---------------------------------------------------------

class _Resp:
    def __init__(self, registers=None, bits=None, error=False):
        self.registers, self.bits, self._error = registers, bits, error

    def isError(self):
        return self._error


class FakeClient:
    """Stands in for ModbusTcpClient; tests set level/coils/fail directly."""

    def __init__(self):
        self.connected = False
        self.level, self.coils = 500, [False, False, False, False]
        self.fail_connect = False
        self.error_response = False
        self.writes = 0

    def connect(self):
        self.connected = not self.fail_connect
        return self.connected

    def close(self):
        self.connected = False

    def read_holding_registers(self, address, count=1, device_id=1):
        assert address == 1024 and count == 1
        return _Resp(registers=[self.level], error=self.error_response)

    def read_coils(self, address, count=1, device_id=1):
        assert address == 0 and count == 4
        return _Resp(bits=self.coils + [False] * 4, error=self.error_response)

    # Any write would be a bug in a read-only HMI.
    def write_register(self, *a, **k):
        self.writes += 1

    write_coil = write_register


def make_poller(**kw):
    client = FakeClient()
    return PlcPoller("plc", 502, client=client, **kw), client


# --- decode -------------------------------------------------------------------

@pytest.mark.parametrize("raw, pct", [(0, 0.0), (1000, 100.0), (705, 70.5), (299, 29.9)])
def test_decode_scales_level(raw, pct):
    assert decode(0, raw, [False] * 4).level == pct


def test_decode_maps_coils_in_order():
    s = decode(0, 960, [True, True, False, True])
    assert (s.pump, s.alarm_hi, s.alarm_lo, s.trip_hihi) == (True, True, False, True)


# --- polling ------------------------------------------------------------------

def test_successful_poll_updates_snapshot():
    poller, client = make_poller()
    client.level, client.coils = 712, [True, False, False, False]
    poller.poll_once(now=100.0)
    snap = poller.snapshot(now=100.5)
    assert snap["online"] is True and snap["error"] is None
    assert snap["current"]["level"] == 71.2 and snap["current"]["pump"] is True
    assert snap["age"] == 0.5
    assert snap["history"] == [[100.0, 71.2, 1]]


def test_history_keeps_only_last_five_minutes():
    poller, _ = make_poller(history_seconds=300)
    for t in range(0, 400):            # 400 one-second polls
        poller.poll_once(now=float(t))
    hist = poller.snapshot(now=399.0)["history"]
    assert hist[0][0] == 99.0 and hist[-1][0] == 399.0
    assert len(hist) == 301


def test_connect_failure_marks_offline_and_keeps_last_values():
    poller, client = make_poller()
    poller.poll_once(now=1.0)
    client.connected, client.fail_connect = False, True
    assert poller.poll_once(now=2.0) is None
    snap = poller.snapshot(now=5.0)
    assert snap["online"] is False and "cannot connect" in snap["error"]
    assert snap["current"]["level"] == 50.0   # last good value still shown...
    assert snap["age"] == 4.0                 # ...but its age makes it visibly stale


def test_modbus_error_response_marks_offline():
    poller, client = make_poller()
    client.error_response = True
    assert poller.poll_once(now=1.0) is None
    assert poller.snapshot(now=1.0)["online"] is False


def test_recovers_after_comms_return():
    poller, client = make_poller()
    client.fail_connect = True
    poller.poll_once(now=1.0)
    client.fail_connect = False
    poller.poll_once(now=2.0)
    assert poller.snapshot(now=2.0)["online"] is True


def test_poller_never_writes():
    poller, client = make_poller()
    for t in range(10):
        poller.poll_once(now=float(t))
    assert client.writes == 0


# --- web API ------------------------------------------------------------------

@pytest.fixture
def client():
    poller, fake = make_poller()
    poller.poll_once(now=10.0)
    app = create_app(poller, start_poller=False)
    return app.test_client()


def test_api_state_returns_json(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) >= {"online", "error", "age", "current", "history"}
    assert r.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_api_is_read_only(client, method):
    assert getattr(client, method)("/api/state").status_code == 405


def test_security_headers_present(client):
    r = client.get("/healthz")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"


# --- front end ----------------------------------------------------------------

def test_index_serves_hmi_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"/static/app.js" in r.data and b"/static/style.css" in r.data


def test_page_has_no_inline_code():
    """The CSP (default-src 'self') blocks inline scripts/styles, so the page
    must load everything from /static. This catches an accidental regression."""
    html = open(os.path.join(os.path.dirname(__file__), "..", "static", "index.html")).read()
    assert "<script>" not in html and "<style>" not in html
    assert " style=" not in html and " onclick=" not in html


@pytest.mark.parametrize("name", ["app.js", "style.css"])
def test_static_assets_served(client, name):
    assert client.get(f"/static/{name}").status_code == 200

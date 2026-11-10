"""Read-only web HMI for ics-security-lab.

A background thread polls the PLC over Modbus/TCP once a second and keeps
the last 5 minutes of samples in memory. Flask serves:

  GET /            the HMI page (static/index.html)
  GET /api/state   current values, comms status and the trend history (JSON)
  GET /healthz     liveness probe

Read-only by design: the HMI only uses Modbus read function codes
(FC1 read coils, FC3 read holding registers) and exposes no write routes.

Modbus map (see docs/architecture.md):
  holding register 1024 (%MW0)  level, 0-1000 = 0.0-100.0 %
  coils 0-4 (%QX0.0-%QX0.4)      pump, HI alarm, LO alarm, HIHI trip, reset
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

from flask import Flask, jsonify, send_from_directory
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

log = logging.getLogger("hmi")

LEVEL_SCALE = 10.0  # register 1000 -> 100.0 %


# =============================================================================
# Data model
# =============================================================================

@dataclass(frozen=True)
class Sample:
    t: float          # Unix time the sample was taken
    level: float      # percent, 0.0-100.0
    pump: bool
    alarm_hi: bool
    alarm_lo: bool
    trip_hihi: bool


def decode(t: float, level_raw: int, coils: list[bool]) -> Sample:
    """Turn raw Modbus values into a Sample (pure function, easy to test)."""
    pump, alarm_hi, alarm_lo, trip_hihi = (bool(b) for b in coils[:4])
    return Sample(t=t, level=round(level_raw / LEVEL_SCALE, 1), pump=pump,
                  alarm_hi=alarm_hi, alarm_lo=alarm_lo, trip_hihi=trip_hihi)


# =============================================================================
# Poller
# =============================================================================

class PlcPoller:
    """Polls the PLC on a fixed schedule and keeps a rolling history.

    All shared state is guarded by a lock: the poll thread writes it and
    Flask request threads read it through snapshot().
    """

    def __init__(self, host: str, port: int, level_register: int = 1024,
                 coil_base: int = 0, device_id: int = 1, interval: float = 1.0,
                 history_seconds: float = 300.0, client=None):
        # Short timeout and no retries: a late answer is useless at 1 Hz.
        self.client = client or ModbusTcpClient(host, port=port, timeout=0.5, retries=0)
        self.host, self.port = host, port
        self.level_register = level_register
        self.coil_base = coil_base
        self.device_id = device_id
        self.interval = interval
        self.history_seconds = history_seconds

        self._lock = threading.Lock()
        # maxlen is a safety cap; trimming by timestamp does the real work.
        self._history: deque[Sample] = deque(maxlen=int(history_seconds / interval) + 10)
        self._latest: Sample | None = None
        self._online = False
        self._error: str | None = "not polled yet"

    # --- one poll -------------------------------------------------------------
    def poll_once(self, now: float | None = None) -> Sample | None:
        """Read the PLC once. Returns the new Sample, or None on failure."""
        now = time.time() if now is None else now
        try:
            if not self.client.connected and not self.client.connect():
                raise ConnectionError(f"cannot connect to {self.host}:{self.port}")
            rr = self.client.read_holding_registers(self.level_register, count=1,
                                                    device_id=self.device_id)
            rc = self.client.read_coils(self.coil_base, count=4, device_id=self.device_id)
            if rr.isError() or rc.isError():
                raise ModbusException(f"PLC returned an error: {rr if rr.isError() else rc}")
            sample = decode(now, rr.registers[0], rc.bits)
        except (ModbusException, ConnectionError, OSError) as exc:
            self._record_failure(str(exc))
            return None
        self._record_success(sample)
        return sample

    def _record_success(self, sample: Sample) -> None:
        with self._lock:
            if not self._online:
                log.info("PLC comms OK (%s:%d)", self.host, self.port)
            self._online, self._error = True, None
            self._latest = sample
            self._history.append(sample)
            cutoff = sample.t - self.history_seconds
            while self._history and self._history[0].t < cutoff:
                self._history.popleft()

    def _record_failure(self, reason: str) -> None:
        with self._lock:
            if self._online or self._error != reason:
                log.warning("PLC comms lost: %s", reason)
            self._online, self._error = False, reason
        self.client.close()

    # --- read side --------------------------------------------------------------
    def snapshot(self, now: float | None = None) -> dict:
        """Everything the page needs, as a JSON-ready dict."""
        now = time.time() if now is None else now
        with self._lock:
            latest = self._latest
            return {
                "online": self._online,
                "error": self._error,
                "server_time": now,
                "age": None if latest is None else round(now - latest.t, 1),
                "current": None if latest is None else asdict(latest),
                # Compact rows for the chart: [time, level, pump 0/1]
                "history": [[s.t, s.level, int(s.pump)] for s in self._history],
            }

    # --- background loop ------------------------------------------------------
    def run_forever(self) -> None:
        next_tick = time.monotonic()
        while True:
            self.poll_once()
            next_tick += self.interval
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()  # overran (slow connect): resync

    def start(self) -> None:
        threading.Thread(target=self.run_forever, name="plc-poller", daemon=True).start()


# =============================================================================
# Web app
# =============================================================================

def create_app(poller: PlcPoller | None = None, start_poller: bool = True) -> Flask:
    if poller is None:
        poller = PlcPoller(
            host=os.getenv("PLC_HOST", "openplc"),
            port=int(os.getenv("PLC_PORT", "502")),
            level_register=int(os.getenv("LEVEL_REGISTER", "1024")),
            coil_base=int(os.getenv("COIL_BASE", "0")),
            device_id=int(os.getenv("MODBUS_DEVICE_ID", "1")),
        )
    if start_poller:
        poller.start()

    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["POLLER"] = poller

    # Flask routes answer GET (and HEAD/OPTIONS) only, so anything else
    # gets 405 Method Not Allowed: there is nothing to write to.
    @app.get("/")
    def index():
        if not os.path.exists(os.path.join(app.static_folder, "index.html")):
            # Front end not added yet: say so plainly instead of a bare 404.
            return ("HMI page not built yet. Live data: /api/state\n", 200,
                    {"Content-Type": "text/plain; charset=utf-8"})
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/state")
    def state():
        resp = jsonify(poller.snapshot())
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.after_request
    def security_headers(resp):
        # Only our own files: no external scripts, styles or frames.
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    return app


if os.getenv("HMI_NO_AUTOSTART") != "1":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # gunicorn imports `app:app`. Run it with ONE worker: the poller and its
    # history live in this process, and extra workers would each poll the PLC.
    app = create_app()

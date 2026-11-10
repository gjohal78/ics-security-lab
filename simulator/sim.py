"""Water-tank process simulator for ics-security-lab.

The simulator plays the role of the physical process (the tank, its
level sensor and the pump motor). On a fixed 100 ms timestep it:

  1. reads the pump command from the PLC   (coil 0         = %QX0.0)
  2. advances the tank physics by one step
  3. writes the measured level to the PLC  (holding reg 1024 = %MW0)

Level is a float in percent (0-100) internally and is sent to the PLC
as an integer 0-1000 (tenths of a percent), since Modbus registers are
16-bit integers.

The physics (`Tank`, `level_to_register`) has no Modbus dependency at
runtime so it can be unit-tested on its own.
"""

from __future__ import annotations

import logging
import os
import random
import signal
import time
from dataclasses import dataclass

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

log = logging.getLogger("simulator")

# --- Timing -----------------------------------------------------------------
DT = 0.1                          # simulation timestep, seconds (100 ms)
LOG_EVERY_TICKS = round(1.0 / DT)  # log once per second

# --- Level scaling ----------------------------------------------------------
LEVEL_MIN, LEVEL_MAX = 0.0, 100.0  # percent
REGISTER_SCALE = 10                # 100.0 % -> 1000 in the register


# =============================================================================
# Tank physics
# =============================================================================

@dataclass(frozen=True)
class TankParams:
    """Physical constants of the tank. Rates are in percent per second."""

    inflow_rate: float = 2.0     # mean inlet flow
    inflow_noise: float = 0.2    # std-dev of inlet flow noise
    pump_rate: float = 5.0       # outflow while the pump runs
    initial_level: float = 50.0  # starting level, percent

    def __post_init__(self) -> None:
        if self.pump_rate <= self.inflow_rate:
            raise ValueError("pump_rate must exceed inflow_rate so the pump can drain the tank")
        if self.inflow_rate < 0 or self.inflow_noise < 0:
            raise ValueError("inflow_rate and inflow_noise must be non-negative")
        if not LEVEL_MIN <= self.initial_level <= LEVEL_MAX:
            raise ValueError("initial_level must be within 0-100 %")


class Tank:
    """A single tank with a constant (noisy) inlet and a pumped outlet."""

    def __init__(self, params: TankParams | None = None, rng: random.Random | None = None):
        self.params = params or TankParams()
        # Injecting the RNG lets tests make the noise reproducible.
        self._rng = rng or random.Random()
        self.level = self.params.initial_level

    def inflow(self) -> float:
        """Current inlet flow (%/s): nominal value plus Gaussian noise, never negative."""
        p = self.params
        return max(0.0, self._rng.gauss(p.inflow_rate, p.inflow_noise))

    def step(self, pump_on: bool, dt: float = DT) -> float:
        """Advance the tank by `dt` seconds and return the new level (%)."""
        if dt <= 0:
            raise ValueError("dt must be positive")
        outflow = self.params.pump_rate if pump_on else 0.0
        # Explicit Euler integration; fine at this timestep for a linear model.
        self.level += (self.inflow() - outflow) * dt
        # The tank can't be more than full or less than empty
        # (overflow spills out; an empty tank stops the outflow).
        self.level = min(LEVEL_MAX, max(LEVEL_MIN, self.level))
        return self.level


def level_to_register(level: float) -> int:
    """Convert a level in percent to the PLC's 0-1000 integer scale."""
    raw = round(level * REGISTER_SCALE)
    return int(min(LEVEL_MAX * REGISTER_SCALE, max(LEVEL_MIN * REGISTER_SCALE, raw)))


# =============================================================================
# Modbus link to the PLC
# =============================================================================

class PlcLink:
    """Small wrapper around the pymodbus client.

    Never raises on communication errors: it returns None/False instead and
    retries the connection at most every `reconnect_interval` seconds, so a
    missing or restarting PLC never stalls the 100 ms loop for long.
    """

    def __init__(self, host: str, port: int, pump_coil: int, level_register: int,
                 device_id: int = 1, reconnect_interval: float = 2.0):
        # Short timeout, no automatic retries: a late answer is useless at 10 Hz.
        self.client = ModbusTcpClient(host, port=port, timeout=0.5, retries=0)
        self.host, self.port = host, port
        self.pump_coil = pump_coil
        self.level_register = level_register
        self.device_id = device_id
        self.reconnect_interval = reconnect_interval
        self._next_connect_attempt = 0.0
        self.online = False

    def _ensure_connected(self) -> bool:
        if self.client.connected:
            return True
        now = time.monotonic()
        if now < self._next_connect_attempt:
            return False
        self._next_connect_attempt = now + self.reconnect_interval
        if self.client.connect():
            log.info("connected to PLC at %s:%d", self.host, self.port)
            self.online = True
            return True
        self._set_offline("connect failed")
        return False

    def _set_offline(self, reason: str) -> None:
        if self.online:
            log.warning("lost PLC connection (%s); keeping last pump state", reason)
        self.online = False
        self.client.close()

    def read_pump(self) -> bool | None:
        """Return the pump coil state, or None if the PLC couldn't be read."""
        if not self._ensure_connected():
            return None
        try:
            rr = self.client.read_coils(self.pump_coil, count=1, device_id=self.device_id)
        except ModbusException as exc:
            self._set_offline(str(exc))
            return None
        if rr.isError():
            log.warning("pump coil read error: %s", rr)
            return None
        return bool(rr.bits[0])

    def write_level(self, raw: int) -> bool:
        """Write the scaled level to the PLC. Returns True on success."""
        if not self._ensure_connected():
            return False
        try:
            rr = self.client.write_register(self.level_register, raw, device_id=self.device_id)
        except ModbusException as exc:
            self._set_offline(str(exc))
            return False
        if rr.isError():
            log.warning("level register write error: %s", rr)
            return False
        return True

    def close(self) -> None:
        self.client.close()


# =============================================================================
# Main loop
# =============================================================================

def run() -> None:
    link = PlcLink(
        host=os.getenv("PLC_HOST", "openplc"),
        port=int(os.getenv("PLC_PORT", "502")),
        pump_coil=int(os.getenv("PUMP_COIL", "0")),             # %QX0.0
        level_register=int(os.getenv("LEVEL_REGISTER", "1024")),  # %MW0
        device_id=int(os.getenv("MODBUS_DEVICE_ID", "1")),
    )
    tank = Tank()
    pump_on = False  # the motor starts stopped until the PLC says otherwise

    # `docker stop` sends SIGTERM; turn it into a clean loop exit.
    running = True

    def _stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("simulator started: dt=%.0f ms, PLC %s:%d", DT * 1000, link.host, link.port)
    next_tick = time.monotonic()
    tick = 0

    while running:
        # 1. Actuator: follow the PLC's pump command. If the PLC can't be
        #    reached, the motor keeps doing whatever it was last told.
        cmd = link.read_pump()
        if cmd is not None:
            pump_on = cmd

        # 2. Physics: the tank keeps evolving whether or not the PLC answers.
        level = tank.step(pump_on, DT)

        # 3. Sensor: report the level to the PLC.
        link.write_level(level_to_register(level))

        tick += 1
        if tick % LOG_EVERY_TICKS == 0:
            log.info("level=%5.1f%%  pump=%s  plc=%s",
                     level, "ON " if pump_on else "OFF", "online" if link.online else "OFFLINE")

        # Fixed timestep: schedule against an absolute clock so small delays
        # don't accumulate into drift.
        next_tick += DT
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            # Overran (e.g. a slow connect). Resync instead of bursting to catch up.
            next_tick = time.monotonic()

    link.close()
    log.info("simulator stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run()

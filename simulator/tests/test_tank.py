"""Unit tests for the tank physics (no PLC or network needed)."""

import random

import pytest

from sim import DT, Tank, TankParams, level_to_register

# Noise-free tank for exact arithmetic checks.
QUIET = TankParams(inflow_rate=2.0, inflow_noise=0.0, pump_rate=5.0, initial_level=50.0)


def make_tank(params=QUIET, seed=0):
    return Tank(params, rng=random.Random(seed))


# --- Single steps -------------------------------------------------------------

def test_pump_off_fills_by_inflow_times_dt():
    tank = make_tank()
    assert tank.step(pump_on=False, dt=DT) == pytest.approx(50.0 + 2.0 * DT)


def test_pump_on_drains_net_of_inflow():
    tank = make_tank()
    assert tank.step(pump_on=True, dt=DT) == pytest.approx(50.0 + (2.0 - 5.0) * DT)


def test_step_rejects_non_positive_dt():
    with pytest.raises(ValueError):
        make_tank().step(False, dt=0)


# --- Behaviour over time (with noise) --------------------------------------

def test_noisy_tank_rises_with_pump_off_and_falls_with_pump_on():
    tank = make_tank(TankParams(), seed=42)
    start = tank.level
    for _ in range(50):          # 5 s
        tank.step(False)
    assert tank.level > start
    peak = tank.level
    for _ in range(50):
        tank.step(True)
    assert tank.level < peak


def test_level_clamps_at_full():
    tank = make_tank(TankParams(initial_level=99.0), seed=1)
    for _ in range(1000):
        tank.step(False)
    assert tank.level == 100.0


def test_level_clamps_at_empty():
    tank = make_tank(TankParams(initial_level=1.0), seed=1)
    for _ in range(1000):
        tank.step(True)
    assert tank.level == 0.0


def test_noise_never_makes_inflow_negative():
    # Huge noise relative to the mean: a raw Gaussian would go negative often.
    params = TankParams(inflow_rate=0.1, inflow_noise=5.0, pump_rate=6.0, initial_level=10.0)
    tank = make_tank(params, seed=7)
    for _ in range(2000):
        before = tank.level
        tank.step(False)
        assert tank.level >= before  # pump off: level can only stay or rise


def test_same_seed_gives_same_trajectory():
    a, b = make_tank(TankParams(), seed=123), make_tank(TankParams(), seed=123)
    for i in range(100):
        pump = i % 20 < 10
        assert a.step(pump) == b.step(pump)


# --- Parameter validation ----------------------------------------------------

def test_pump_must_drain_faster_than_inlet_fills():
    with pytest.raises(ValueError):
        TankParams(inflow_rate=5.0, pump_rate=5.0)


@pytest.mark.parametrize("level", [-1.0, 100.1])
def test_initial_level_must_be_in_range(level):
    with pytest.raises(ValueError):
        TankParams(initial_level=level)


# --- Register scaling ------------------------------------------------------

@pytest.mark.parametrize("level, raw", [
    (0.0, 0),
    (100.0, 1000),
    (50.0, 500),
    (12.34, 123),
    (12.36, 124),
    (-5.0, 0),       # clamped
    (150.0, 1000),   # clamped
])
def test_level_to_register(level, raw):
    assert level_to_register(level) == raw
    assert isinstance(level_to_register(level), int)

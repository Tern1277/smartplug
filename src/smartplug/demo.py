"""Simulated plug, so the app can be tried and tested without Tuya keys."""

from __future__ import annotations

import math
import random
import time

from .devices import DeviceInfo

DEMO_DEVICE_ID = "demo-plug-0001"


class DemoClient:
    """Behaves like TuyaCloudClient for a single metering plug.

    The load imitates a fridge compressor cycling plus a kettle now and then;
    the grid voltage drifts around 228 V with occasional dips and short
    outages (the plug goes offline), like a real evening with blackouts.
    """

    def __init__(self, seed: int | None = None, outage_every: int = 90, clock=time.time):
        self._rng = random.Random(seed)
        self._clock = clock
        self._is_on = True
        self._reads = 0
        self._outage_every = outage_every
        self._outage_left = 0
        self._dip_left = 0

    def list_devices(self) -> list[DeviceInfo]:
        return [DeviceInfo(DEMO_DEVICE_ID, "Демо-розетка", "cz", True, "Smart Plug 16A")]

    def specification(self, device_id: str) -> list[dict]:
        return [
            {"code": "switch_1", "type": "Boolean", "values": "{}"},
            {"code": "cur_power", "type": "Integer", "values": '{"unit":"W","scale":1}'},
            {"code": "cur_voltage", "type": "Integer", "values": '{"unit":"V","scale":1}'},
            {"code": "cur_current", "type": "Integer", "values": '{"unit":"mA","scale":0}'},
            {"code": "add_ele", "type": "Integer", "values": '{"unit":"kwh","scale":3}'},
        ]

    def set_switch(self, device_id: str, code: str, value: bool) -> None:
        self._is_on = bool(value)

    def _voltage(self, t: float) -> float:
        v = 228 + 4 * math.sin(t / 1800) + self._rng.gauss(0, 1.2)
        if self._dip_left > 0:
            self._dip_left -= 1
            v -= self._rng.uniform(25, 40)
        elif self._rng.random() < 0.03:
            self._dip_left = self._rng.randint(1, 3)
        return v

    def _power(self, t: float) -> float:
        if not self._is_on:
            return 0.0
        fridge = 95 + self._rng.gauss(0, 3) if (t // 600) % 3 != 0 else 1.5
        kettle = 2000 + self._rng.gauss(0, 30) if self._rng.random() < 0.04 else 0.0
        return max(0.0, fridge + kettle)

    def read(self, device_id: str) -> tuple[bool, list[dict]]:
        self._reads += 1
        if self._outage_left > 0:
            self._outage_left -= 1
            return False, []
        if self._outage_every and self._reads % self._outage_every == 0:
            self._outage_left = self._rng.randint(2, 6)
            return False, []

        t = self._clock()
        volts = self._voltage(t)
        watts = self._power(t)
        milliamps = watts / volts * 1000 if volts > 0 else 0
        status = [
            {"code": "switch_1", "value": self._is_on},
            {"code": "cur_power", "value": round(watts * 10)},
            {"code": "cur_voltage", "value": round(volts * 10)},
            {"code": "cur_current", "value": round(milliamps)},
            {"code": "add_ele", "value": self._rng.randint(0, 3)},
        ]
        return True, status


def seed_history(storage, hours: float = 6, step: float = 60, seed: int = 7) -> None:
    """Fill an empty demo database with a few hours of simulated history."""
    from .analysis import EventTracker
    from .cloud import PlugService

    if storage.last_reading(DEMO_DEVICE_ID) is not None:
        return
    now = time.time()
    clock = {"t": now - hours * 3600}
    service = PlugService(DemoClient(seed=seed, outage_every=120, clock=lambda: clock["t"]),
                          DEMO_DEVICE_ID)
    tracker = EventTracker(storage, DEMO_DEVICE_ID, 207, 253)
    while clock["t"] < now - step:
        reading = service.read()
        reading.ts = clock["t"]
        storage.add_reading(DEMO_DEVICE_ID, reading)
        tracker.process(reading)
        clock["t"] += step

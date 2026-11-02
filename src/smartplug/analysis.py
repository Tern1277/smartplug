"""Event detection (outages, voltage out of range) and statistics."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .devices import PlugReading
from .storage import Storage

OFFLINE = "offline"
VOLTAGE_LOW = "voltage_low"
VOLTAGE_HIGH = "voltage_high"

EVENT_TITLES = {
    OFFLINE: "Розетка offline (можливо, немає світла)",
    VOLTAGE_LOW: "Просідання напруги",
    VOLTAGE_HIGH: "Підвищена напруга",
}


@dataclass
class Notice:
    title: str
    text: str
    critical: bool = False


class EventTracker:
    """Opens and closes events in storage as readings arrive.

    Open events are reloaded from the database, so restarting the app in
    the middle of an outage doesn't create a duplicate.
    """

    def __init__(self, storage: Storage, device_id: str, low: float, high: float):
        self.storage = storage
        self.device_id = device_id
        self.low = low
        self.high = high
        self._open = {e.kind: e for e in storage.open_events(device_id)}

    def is_open(self, kind: str) -> bool:
        return kind in self._open

    def _start(self, kind: str, ts: float, value: float | None) -> None:
        self._open[kind] = self.storage.open_event(self.device_id, kind, ts, value)

    def _stop(self, kind: str, ts: float):
        event = self._open.pop(kind, None)
        if event:
            self.storage.close_event(event.id, ts)
        return event

    def process(self, r: PlugReading) -> list[Notice]:
        notices: list[Notice] = []

        if not r.online:
            if OFFLINE not in self._open:
                self._start(OFFLINE, r.ts, None)
                notices.append(Notice(
                    "⚠️ Розетка не на зв'язку",
                    "Можливо, вдома зникло світло або інтернет.",
                    critical=True,
                ))
            return notices  # no fresh measurements while offline

        ended = self._stop(OFFLINE, r.ts)
        if ended:
            notices.append(Notice(
                "✅ Розетка знову online",
                f"Не було зв'язку {format_duration(r.ts - ended.ts_start)}.",
            ))

        v = r.voltage_v
        if v is None:
            return notices

        # low voltage
        if v < self.low:
            ev = self._open.get(VOLTAGE_LOW)
            if ev is None:
                self._start(VOLTAGE_LOW, r.ts, v)
                notices.append(Notice(
                    "⚡ Просідання напруги",
                    f"{v:.0f} В (норма від {self.low:.0f} В).",
                    critical=v < self.low - 20,
                ))
            elif ev.value is None or v < ev.value:
                ev.value = v
                self.storage.update_event_value(ev.id, v)
        else:
            self._stop(VOLTAGE_LOW, r.ts)

        # high voltage
        if v > self.high:
            ev = self._open.get(VOLTAGE_HIGH)
            if ev is None:
                self._start(VOLTAGE_HIGH, r.ts, v)
                notices.append(Notice(
                    "⚡ Підвищена напруга",
                    f"{v:.0f} В (норма до {self.high:.0f} В).",
                    critical=True,
                ))
            elif ev.value is None or v > ev.value:
                ev.value = v
                self.storage.update_event_value(ev.id, v)
        else:
            self._stop(VOLTAGE_HIGH, r.ts)

        return notices


def integrate_energy_kwh(readings: list[PlugReading], max_gap: float = 600) -> float:
    """Energy from power samples (trapezoidal rule).

    Intervals longer than max_gap seconds or with the plug offline are
    skipped, because we don't know what happened there.
    """
    total_wh = 0.0
    prev = None
    for r in readings:
        if not r.online or r.power_w is None:
            prev = None
            continue
        if prev is not None:
            dt = r.ts - prev.ts
            if 0 < dt <= max_gap:
                total_wh += (prev.power_w + r.power_w) / 2 * dt / 3600
        prev = r
    return total_wh / 1000


@dataclass
class Stats:
    count: int = 0
    min: float | None = None
    max: float | None = None
    avg: float | None = None


def stats(values) -> Stats:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if not vals:
        return Stats()
    return Stats(len(vals), min(vals), max(vals), sum(vals) / len(vals))


def uptime_ratio(readings: list[PlugReading]) -> float | None:
    """Share of readings where the plug was online (0..1)."""
    if not readings:
        return None
    return sum(1 for r in readings if r.online) / len(readings)


def format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} год {m} хв"
    if m:
        return f"{m} хв {s} с"
    return f"{s} с"

"""SQLite history of readings and detected events."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .devices import PlugReading

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    device_id TEXT NOT NULL,
    ts        REAL NOT NULL,
    online    INTEGER NOT NULL,
    is_on     INTEGER,
    power     REAL,
    voltage   REAL,
    current   REAL,
    energy    REAL
);
CREATE INDEX IF NOT EXISTS readings_dev_ts ON readings(device_id, ts);

CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    kind      TEXT NOT NULL,
    ts_start  REAL NOT NULL,
    ts_end    REAL,
    value     REAL
);
CREATE INDEX IF NOT EXISTS events_dev_ts ON events(device_id, ts_start);
"""


@dataclass
class Event:
    id: int
    device_id: str
    kind: str
    ts_start: float
    ts_end: float | None
    value: float | None

    @property
    def is_open(self) -> bool:
        return self.ts_end is None


def _opt_bool(v):
    return None if v is None else bool(v)


class Storage:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    # readings -----------------------------------------------------------
    def add_reading(self, device_id: str, r: PlugReading) -> None:
        self._db.execute(
            "INSERT INTO readings VALUES (?,?,?,?,?,?,?,?)",
            (
                device_id, r.ts, int(r.online),
                None if r.is_on is None else int(r.is_on),
                r.power_w, r.voltage_v, r.current_a, r.energy_kwh,
            ),
        )
        self._db.commit()

    def readings(self, device_id: str, since: float, until: float | None = None) -> list[PlugReading]:
        until = time.time() + 1 if until is None else until
        rows = self._db.execute(
            "SELECT ts, online, is_on, power, voltage, current, energy FROM readings "
            "WHERE device_id=? AND ts>=? AND ts<=? ORDER BY ts",
            (device_id, since, until),
        ).fetchall()
        return [
            PlugReading(ts, bool(online), _opt_bool(is_on), p, v, c, e)
            for ts, online, is_on, p, v, c, e in rows
        ]

    def last_reading(self, device_id: str) -> PlugReading | None:
        rows = self._db.execute(
            "SELECT ts, online, is_on, power, voltage, current, energy FROM readings "
            "WHERE device_id=? ORDER BY ts DESC LIMIT 1",
            (device_id,),
        ).fetchall()
        if not rows:
            return None
        ts, online, is_on, p, v, c, e = rows[0]
        return PlugReading(ts, bool(online), _opt_bool(is_on), p, v, c, e)

    def prune(self, older_than_days: float = 90) -> None:
        cutoff = time.time() - older_than_days * 86400
        self._db.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
        self._db.execute("DELETE FROM events WHERE ts_end IS NOT NULL AND ts_end < ?", (cutoff,))
        self._db.commit()

    # events -------------------------------------------------------------
    def open_event(self, device_id: str, kind: str, ts: float, value: float | None = None) -> Event:
        cur = self._db.execute(
            "INSERT INTO events(device_id, kind, ts_start, value) VALUES (?,?,?,?)",
            (device_id, kind, ts, value),
        )
        self._db.commit()
        return Event(cur.lastrowid, device_id, kind, ts, None, value)

    def update_event_value(self, event_id: int, value: float) -> None:
        self._db.execute("UPDATE events SET value=? WHERE id=?", (value, event_id))
        self._db.commit()

    def close_event(self, event_id: int, ts: float) -> None:
        self._db.execute("UPDATE events SET ts_end=? WHERE id=?", (ts, event_id))
        self._db.commit()

    def open_events(self, device_id: str) -> list[Event]:
        rows = self._db.execute(
            "SELECT id, device_id, kind, ts_start, ts_end, value FROM events "
            "WHERE device_id=? AND ts_end IS NULL ORDER BY ts_start",
            (device_id,),
        ).fetchall()
        return [Event(*row) for row in rows]

    def events(self, device_id: str, since: float, limit: int = 500) -> list[Event]:
        rows = self._db.execute(
            "SELECT id, device_id, kind, ts_start, ts_end, value FROM events "
            "WHERE device_id=? AND (ts_end IS NULL OR ts_end>=?) "
            "ORDER BY ts_start DESC LIMIT ?",
            (device_id, since, limit),
        ).fetchall()
        return [Event(*row) for row in rows]

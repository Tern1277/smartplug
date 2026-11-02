"""Device models and conversion of raw Tuya data points into readable values.

Tuya reports measurements as integers plus a "scale" from the device
specification: real value = raw / 10**scale. Typical smart plug codes:

    switch_1     bool   relay on/off
    cur_power    W      scale 1  (raw 1234 -> 123.4 W)
    cur_voltage  V      scale 1  (raw 2301 -> 230.1 V)
    cur_current  mA     scale 0
    add_ele      kWh    scale 3  (energy counter reported by the plug)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .i18n import _

SWITCH_CODES = ("switch_1", "switch")
POWER_CODE = "cur_power"
VOLTAGE_CODE = "cur_voltage"
CURRENT_CODE = "cur_current"
ENERGY_CODE = "add_ele"

# Fallback scales/units if the specification can't be fetched.
DEFAULT_SPEC: dict[str, tuple[int, str]] = {
    POWER_CODE: (1, "W"),
    VOLTAGE_CODE: (1, "V"),
    CURRENT_CODE: (0, "mA"),
    ENERGY_CODE: (3, "kwh"),
}

# Tuya category codes that behave like a plug with a relay.
PLUG_CATEGORIES = {
    "cz": "Plug",
    "pc": "Power strip",
    "kg": "Switch",
    "tdq": "Breaker",
}


@dataclass(frozen=True)
class DeviceInfo:
    id: str
    name: str
    category: str = ""
    online: bool = False
    product_name: str = ""

    @property
    def kind(self) -> str:
        if self.category in PLUG_CATEGORIES:
            return _(PLUG_CATEGORIES[self.category])
        return self.category or _("Device")

    @property
    def is_plug(self) -> bool:
        return self.category in PLUG_CATEGORIES

    def label(self) -> str:
        state = _("online") if self.online else _("offline")
        return f"{self.name} · {self.kind} · {state}"


@dataclass
class PlugReading:
    ts: float
    online: bool
    is_on: bool | None = None
    power_w: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    energy_kwh: float | None = None
    switch_code: str | None = field(default=None, compare=False)

    @property
    def has_metering(self) -> bool:
        return any(v is not None for v in (self.power_w, self.voltage_v, self.current_a))


def parse_specification(spec_status: list[dict] | None) -> dict[str, tuple[int, str]]:
    """Read {code: (scale, unit)} from the 'status' list of a device specification."""
    spec = dict(DEFAULT_SPEC)
    for item in spec_status or []:
        code = item.get("code")
        values = item.get("values")
        if not code or not values:
            continue
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError:
                continue
        if not isinstance(values, dict) or "scale" not in values:
            continue
        try:
            scale = int(values.get("scale", 0))
        except (TypeError, ValueError):
            continue
        spec[code] = (scale, str(values.get("unit", "")))
    return spec


def status_to_dict(status: list[dict] | dict | None) -> dict:
    """Tuya returns status as [{"code": ..., "value": ...}]; turn it into a dict."""
    if isinstance(status, dict):
        return dict(status)
    return {item["code"]: item.get("value") for item in status or [] if "code" in item}


def _scaled(status: dict, code: str, spec: dict[str, tuple[int, str]]) -> float | None:
    raw = status.get(code)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return None
    scale, _unit = spec.get(code, (0, ""))
    return raw / (10 ** scale)


def find_switch_code(status: dict) -> str | None:
    for code in SWITCH_CODES:
        if code in status:
            return code
    return None


def parse_plug(
    status: list[dict] | dict | None,
    online: bool,
    spec: dict[str, tuple[int, str]] | None = None,
    ts: float | None = None,
) -> PlugReading:
    """Convert raw status of a plug into a PlugReading in SI-like units."""
    ts = time.time() if ts is None else ts
    data = status_to_dict(status)
    spec = spec or DEFAULT_SPEC
    switch_code = find_switch_code(data)

    if not online:
        # Values reported by the cloud for an offline device are stale.
        return PlugReading(ts=ts, online=False, switch_code=switch_code)

    current = _scaled(data, CURRENT_CODE, spec)
    if current is not None:
        unit = spec.get(CURRENT_CODE, (0, "mA"))[1].lower()
        if unit in ("", "ma"):
            current /= 1000.0

    is_on = bool(data[switch_code]) if switch_code else None
    return PlugReading(
        ts=ts,
        online=True,
        is_on=is_on,
        power_w=_scaled(data, POWER_CODE, spec),
        voltage_v=_scaled(data, VOLTAGE_CODE, spec),
        current_a=current,
        energy_kwh=_scaled(data, ENERGY_CODE, spec),
        switch_code=switch_code,
    )

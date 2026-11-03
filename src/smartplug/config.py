"""Application settings stored in ~/.config/smartplug/config.json (mode 600)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .i18n import LANGUAGES

# Tuya data centers supported by tinytuya (code -> human readable name).
# Names are English source strings; translate with i18n._() when displaying.
REGIONS: dict[str, str] = {
    "eu": "Central Europe",
    "eu-w": "Western Europe",
    "us": "Western America",
    "us-e": "Eastern America",
    "in": "India",
    "sg": "Singapore",
    "cn": "China",
}

MIN_POLL_SECONDS = 10
MIN_CYCLE_SECONDS = 5
MAX_CYCLE_SECONDS = 300


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "smartplug"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "smartplug"


def default_config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class AppConfig:
    access_id: str = ""
    access_secret: str = ""
    region: str = "eu"
    device_id: str = ""
    device_name: str = ""
    poll_seconds: int = 60
    nominal_voltage: float = 230.0
    tolerance_pct: float = 10.0
    confirm_switch: bool = True
    power_cycle_seconds: int = 30
    notifications: bool = True
    language: str = "en"

    @property
    def configured(self) -> bool:
        return bool(self.access_id and self.access_secret and self.device_id)

    @property
    def voltage_low(self) -> float:
        return self.nominal_voltage * (1 - self.tolerance_pct / 100)

    @property
    def voltage_high(self) -> float:
        return self.nominal_voltage * (1 + self.tolerance_pct / 100)

    def masked(self) -> dict:
        """Settings safe to print or log (secret hidden)."""
        data = asdict(self)
        if data["access_secret"]:
            data["access_secret"] = "***"
        return data


def load_config(path: Path | None = None) -> AppConfig:
    path = path or default_config_path()
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppConfig()
    known = {f.name for f in fields(AppConfig)}
    cfg = AppConfig(**{k: v for k, v in raw.items() if k in known})
    cfg.poll_seconds = max(MIN_POLL_SECONDS, int(cfg.poll_seconds))
    try:
        cycle = int(cfg.power_cycle_seconds)
    except (TypeError, ValueError):
        cycle = AppConfig.power_cycle_seconds
    cfg.power_cycle_seconds = min(MAX_CYCLE_SECONDS, max(MIN_CYCLE_SECONDS, cycle))
    if cfg.region not in REGIONS:
        cfg.region = "eu"
    if cfg.language not in LANGUAGES:
        cfg.language = "en"
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    """Write settings atomically; the file is readable only by the owner."""
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def save_language(lang: str, path: Path | None = None) -> None:
    """Remember only the interface language (used by the demo mode too)."""
    cfg = load_config(path)
    cfg.language = lang
    save_config(cfg, path)

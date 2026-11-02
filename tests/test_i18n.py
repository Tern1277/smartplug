import ast
import string
from pathlib import Path

import pytest

from smartplug import i18n
from smartplug.analysis import EVENT_TITLES, format_duration
from smartplug.config import REGIONS
from smartplug.devices import PLUG_CATEGORIES, DeviceInfo
from smartplug.gui.mainwindow import RANGES
from smartplug.gui.settings import HELP

SRC = Path(__file__).resolve().parents[1] / "src" / "smartplug"


@pytest.fixture(autouse=True)
def english_after_test():
    yield
    i18n.set_language("en")


def literal_keys():
    """All string literals passed directly to _() in the sources."""
    keys = set()
    for path in SRC.rglob("*.py"):
        if path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return keys


def indirect_keys():
    """Strings kept in tables and translated later with _(value)."""
    return (set(EVENT_TITLES.values()) | set(PLUG_CATEGORIES.values())
            | set(REGIONS.values()) | {name for name, _ in RANGES} | {HELP})


def fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_ui_string_has_ukrainian_translation():
    keys = literal_keys() | indirect_keys()
    assert len(keys) > 60
    missing = sorted(k for k in keys if k not in i18n.UK)
    assert missing == []


def test_translations_keep_placeholders():
    for en, uk in i18n.UK.items():
        assert fields(en) == fields(uk), en


def test_english_is_default_and_unknown_falls_back():
    assert i18n.get_language() == "en"
    assert i18n._("Voltage") == "Voltage"
    assert i18n.set_language("de") == "en"


def test_switch_to_ukrainian():
    i18n.set_language("uk")
    assert i18n._("Voltage") == "Напруга"
    assert format_duration(65) == "1 хв 5 с"
    assert DeviceInfo("x", "Кухня", "cz", True).kind == "Розетка"
    assert i18n._("not in catalog") == "not in catalog"

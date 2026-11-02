import json
import stat

import pytest

from smartplug.analysis import (
    OFFLINE, VOLTAGE_HIGH, VOLTAGE_LOW, EventTracker, format_duration,
    integrate_energy_kwh, stats, uptime_ratio,
)
from smartplug.cloud import CloudError, PlugService, TuyaCloudClient
from smartplug.config import AppConfig, load_config, save_config
from smartplug.demo import DEMO_DEVICE_ID, DemoClient
from smartplug.devices import DeviceInfo, PlugReading, parse_plug, parse_specification
from smartplug.storage import Storage

SPEC = [
    {"code": "cur_power", "values": '{"unit":"W","scale":1}'},
    {"code": "cur_voltage", "values": '{"unit":"V","scale":1}'},
    {"code": "cur_current", "values": '{"unit":"mA","scale":0}'},
    {"code": "add_ele", "values": '{"unit":"kwh","scale":3}'},
    {"code": "switch_1", "values": "{}"},
]
STATUS = [
    {"code": "switch_1", "value": True},
    {"code": "cur_power", "value": 1234},
    {"code": "cur_voltage", "value": 2301},
    {"code": "cur_current", "value": 537},
    {"code": "add_ele", "value": 12},
]


# devices ---------------------------------------------------------------
def test_parse_specification_reads_scales_and_skips_bad_items():
    spec = parse_specification(SPEC + [{"code": "x", "values": "not json"}])
    assert spec["cur_power"] == (1, "W")
    assert spec["cur_current"] == (0, "mA")
    assert "switch_1" not in spec or spec["switch_1"] != (None, None)


def test_parse_plug_scales_values():
    r = parse_plug(STATUS, True, parse_specification(SPEC), ts=100)
    assert r.online and r.is_on is True
    assert r.power_w == pytest.approx(123.4)
    assert r.voltage_v == pytest.approx(230.1)
    assert r.current_a == pytest.approx(0.537)
    assert r.energy_kwh == pytest.approx(0.012)
    assert r.switch_code == "switch_1"


def test_parse_plug_uses_spec_scale_not_default():
    spec = parse_specification([{"code": "cur_voltage", "values": {"unit": "V", "scale": 0}}])
    r = parse_plug([{"code": "cur_voltage", "value": 229}], True, spec)
    assert r.voltage_v == 229


def test_parse_plug_offline_discards_stale_values():
    r = parse_plug(STATUS, False, None, ts=5)
    assert not r.online
    assert r.power_w is None and r.voltage_v is None and r.is_on is None


def test_parse_plug_without_metering():
    r = parse_plug({"switch": False}, True)
    assert r.is_on is False and r.switch_code == "switch"
    assert not r.has_metering


def test_device_info_label_and_kind():
    d = DeviceInfo("id1", "Кухня", "cz", True)
    assert d.is_plug and d.kind == "Розетка"
    assert "online" in d.label()
    assert not DeviceInfo("id2", "Лампа", "dj").is_plug


# config ----------------------------------------------------------------
def test_config_roundtrip_and_permissions(tmp_path):
    path = tmp_path / "cfg" / "config.json"
    cfg = AppConfig(access_id="id", access_secret="secret", device_id="dev", poll_seconds=30)
    save_config(cfg, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    loaded = load_config(path)
    assert loaded == cfg and loaded.configured


def test_config_sanitizes_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"poll_seconds": 1, "region": "mars", "unknown": 1}))
    cfg = load_config(path)
    assert cfg.poll_seconds == 10 and cfg.region == "eu"


def test_config_masked_hides_secret():
    assert AppConfig(access_secret="abc").masked()["access_secret"] == "***"


def test_voltage_thresholds():
    cfg = AppConfig(nominal_voltage=230, tolerance_pct=10)
    assert cfg.voltage_low == pytest.approx(207)
    assert cfg.voltage_high == pytest.approx(253)


# cloud client (with a fake tinytuya.Cloud) -------------------------------
class FakeCloud:
    token = "tok"

    def __init__(self):
        self.posts = []

    def cloudrequest(self, url, action=None, post=None, query=None):
        if url.endswith("/specification"):
            return {"success": True, "result": {"status": SPEC}}
        if url.endswith("/commands"):
            self.posts.append(post)
            return {"success": True, "result": True}
        if url.startswith("/v1.0/devices/bad"):
            return {"success": False, "msg": "permission deny"}
        return {"success": True, "result": {"online": True, "status": STATUS}}

    def getdevices(self, verbose=False):
        return [{"id": "d1", "name": "Розетка", "category": "cz", "online": True}]


def test_cloud_client_requires_keys():
    with pytest.raises(CloudError):
        TuyaCloudClient("", "", cloud=FakeCloud())


def test_cloud_client_reports_auth_failure():
    class NoToken:
        token = None
        error = {"Error": "sign invalid"}

    with pytest.raises(CloudError, match="sign invalid"):
        TuyaCloudClient("id", "secret", cloud=NoToken())


def test_service_reads_and_switches():
    cloud = FakeCloud()
    client = TuyaCloudClient("id", "secret", cloud=cloud)
    assert client.list_devices()[0].is_plug
    svc = PlugService(client, "d1")
    r = svc.read()
    assert r.voltage_v == pytest.approx(230.1)
    svc.set_on(False)
    assert cloud.posts == [{"commands": [{"code": "switch_1", "value": False}]}]


def test_service_raises_cloud_error_message():
    client = TuyaCloudClient("id", "secret", cloud=FakeCloud())
    with pytest.raises(CloudError, match="permission deny"):
        PlugService(client, "bad").read()


# demo ------------------------------------------------------------------
def test_demo_client_produces_plausible_readings_and_switches_off():
    demo = DemoClient(seed=1, outage_every=0)
    svc = PlugService(demo, DEMO_DEVICE_ID)
    r = svc.read()
    assert r.online and 150 < r.voltage_v < 260
    svc.set_on(False)
    r = svc.read()
    assert r.is_on is False and r.power_w == 0


def test_demo_client_has_outages():
    demo = DemoClient(seed=2, outage_every=5)
    states = [demo.read(DEMO_DEVICE_ID)[0] for _ in range(12)]
    assert False in states and True in states


# storage + events --------------------------------------------------------
def R(ts, online=True, v=230.0, p=100.0):
    return PlugReading(ts, online, True if online else None,
                       p if online else None, v if online else None, None, None)


def test_storage_roundtrip():
    st = Storage(":memory:")
    st.add_reading("d", R(1))
    st.add_reading("d", R(2, online=False))
    rows = st.readings("d", 0, 10)
    assert [r.online for r in rows] == [True, False]
    assert st.last_reading("d").ts == 2
    assert st.readings("other", 0, 10) == []


def test_tracker_outage_open_close_and_restart():
    st = Storage(":memory:")
    tr = EventTracker(st, "d", 207, 253)
    assert tr.process(R(0)) == []
    notices = tr.process(R(60, online=False))
    assert notices and notices[0].critical
    assert tr.process(R(120, online=False)) == []  # no duplicate notice
    # app restarted during the outage: open event is reloaded
    tr2 = EventTracker(st, "d", 207, 253)
    assert tr2.is_open(OFFLINE)
    back = tr2.process(R(300))
    assert back and "online" in back[0].title
    ev = st.events("d", 0)[0]
    assert ev.kind == OFFLINE and ev.ts_start == 60 and ev.ts_end == 300


def test_tracker_voltage_dip_records_minimum():
    st = Storage(":memory:")
    tr = EventTracker(st, "d", 207, 253)
    tr.process(R(0, v=200))
    tr.process(R(60, v=190))
    tr.process(R(120, v=198))
    tr.process(R(180, v=229))
    ev = st.events("d", 0)[0]
    assert ev.kind == VOLTAGE_LOW and ev.value == 190 and ev.ts_end == 180


def test_tracker_high_voltage():
    st = Storage(":memory:")
    tr = EventTracker(st, "d", 207, 253)
    assert tr.process(R(0, v=260))[0].critical
    assert tr.is_open(VOLTAGE_HIGH)


def test_energy_integration_skips_gaps_and_offline():
    rows = [R(0, p=1000), R(3600, p=1000)]  # 1 kW for 1 h
    assert integrate_energy_kwh(rows, max_gap=7200) == pytest.approx(1.0)
    assert integrate_energy_kwh(rows, max_gap=600) == 0.0
    rows = [R(0, p=600), R(60, online=False), R(120, p=600), R(180, p=600)]
    assert integrate_energy_kwh(rows) == pytest.approx(600 * 60 / 3600 / 1000)


def test_stats_uptime_and_duration():
    s = stats([1, None, 3, float("nan")])
    assert (s.count, s.min, s.max, s.avg) == (2, 1, 3, 2)
    assert stats([]).count == 0
    assert uptime_ratio([R(0), R(1, online=False)]) == 0.5
    assert uptime_ratio([]) is None
    assert format_duration(3725) == "1 год 2 хв"
    assert format_duration(65) == "1 хв 5 с"

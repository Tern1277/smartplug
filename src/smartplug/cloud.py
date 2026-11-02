"""Access to devices: Tuya Cloud client and a service that produces PlugReadings."""

from __future__ import annotations

from typing import Protocol

from .i18n import _
from .devices import DeviceInfo, PlugReading, parse_plug, parse_specification


class CloudError(Exception):
    """Any problem talking to the cloud (network, credentials, device)."""


class DeviceClient(Protocol):
    def list_devices(self) -> list[DeviceInfo]: ...
    def read(self, device_id: str) -> tuple[bool, list[dict]]: ...
    def specification(self, device_id: str) -> list[dict]: ...
    def set_switch(self, device_id: str, code: str, value: bool) -> None: ...


def _error_text(resp) -> str:
    if isinstance(resp, dict):
        for key in ("msg", "Error", "Payload"):
            if resp.get(key):
                return str(resp[key])
    return _("no response from Tuya Cloud")


class TuyaCloudClient:
    """Thin wrapper over tinytuya.Cloud (Tuya IoT Platform OpenAPI)."""

    def __init__(self, access_id: str, access_secret: str, region: str = "eu", cloud=None):
        if not access_id or not access_secret:
            raise CloudError(_("Access ID or Access Secret is missing"))
        if cloud is None:
            import tinytuya  # imported lazily: tests and demo mode don't need it

            cloud = tinytuya.Cloud(apiRegion=region, apiKey=access_id, apiSecret=access_secret)
        if not getattr(cloud, "token", None):
            raise CloudError(_(
                "Could not sign in to Tuya Cloud: {err}. Check the keys and the data center.",
                err=_error_text(getattr(cloud, "error", None)),
            ))
        self._cloud = cloud

    def _request(self, url: str, **kw) -> dict:
        try:
            resp = self._cloud.cloudrequest(url, **kw)
        except Exception as exc:  # network errors from requests etc.
            raise CloudError(_("Network error: {err}", err=exc)) from exc
        if not isinstance(resp, dict) or not resp.get("success"):
            raise CloudError(_error_text(resp))
        return resp.get("result")

    def list_devices(self) -> list[DeviceInfo]:
        try:
            devices = self._cloud.getdevices(verbose=False)
        except Exception as exc:
            raise CloudError(_("Network error: {err}", err=exc)) from exc
        if isinstance(devices, dict):
            raise CloudError(_error_text(devices))
        result = []
        for dev in devices or []:
            if not isinstance(dev, dict) or "id" not in dev:
                continue
            result.append(
                DeviceInfo(
                    id=dev["id"],
                    name=dev.get("name") or dev["id"],
                    category=dev.get("category", ""),
                    online=bool(dev.get("online", False)),
                    product_name=dev.get("product_name", ""),
                )
            )
        return result

    def read(self, device_id: str) -> tuple[bool, list[dict]]:
        # One call returns both the online flag and the current data points.
        result = self._request(f"/v1.0/devices/{device_id}") or {}
        return bool(result.get("online", False)), result.get("status") or []

    def specification(self, device_id: str) -> list[dict]:
        result = self._request(f"/v1.0/iot-03/devices/{device_id}/specification") or {}
        return result.get("status") or []

    def set_switch(self, device_id: str, code: str, value: bool) -> None:
        self._request(
            f"/v1.0/iot-03/devices/{device_id}/commands",
            action="POST",
            post={"commands": [{"code": code, "value": bool(value)}]},
        )


class PlugService:
    """Reads one plug through any DeviceClient and converts data to PlugReading."""

    def __init__(self, client: DeviceClient, device_id: str):
        self.client = client
        self.device_id = device_id
        self._spec: dict | None = None
        self.switch_code: str | None = None

    def _ensure_spec(self) -> dict:
        if self._spec is None:
            try:
                self._spec = parse_specification(self.client.specification(self.device_id))
            except CloudError:
                # Not fatal: fall back to default scales, retry next time.
                return parse_specification(None)
        return self._spec

    def read(self) -> PlugReading:
        online, status = self.client.read(self.device_id)
        reading = parse_plug(status, online, self._ensure_spec())
        if reading.switch_code:
            self.switch_code = reading.switch_code
        return reading

    def set_on(self, value: bool) -> None:
        if not self.switch_code:
            self.read()
        if not self.switch_code:
            raise CloudError(_("The device has no controllable relay (switch_1)"))
        self.client.set_switch(self.device_id, self.switch_code, value)

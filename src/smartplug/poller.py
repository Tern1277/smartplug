"""Background worker: all network calls run outside the GUI thread."""

from __future__ import annotations

import time

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from .cloud import CloudError, PlugService
from .i18n import _


class PlugWorker(QObject):
    reading = pyqtSignal(object)      # PlugReading
    switched = pyqtSignal(bool)       # new requested state
    failed = pyqtSignal(str)

    # Tuya Cloud updates the device status a moment after the command is accepted,
    # so an immediate read still shows the old state. Re-read until it matches.
    CONFIRM_ATTEMPTS = 6
    CONFIRM_DELAY = 1.0

    def __init__(self, service_factory, sleep=time.sleep):
        super().__init__()
        self._factory = service_factory
        self._sleep = sleep
        self._service: PlugService | None = None

    def _get_service(self) -> PlugService:
        if self._service is None:
            self._service = self._factory()
        return self._service

    @pyqtSlot()
    def poll(self) -> None:
        try:
            self.reading.emit(self._get_service().read())
        except CloudError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # keep the worker alive on unexpected errors
            self._service = None
            self.failed.emit(_("Unexpected error: {err}", err=exc))

    @pyqtSlot(bool)
    def set_on(self, value: bool) -> None:
        try:
            service = self._get_service()
            service.set_on(value)
            self.switched.emit(value)
            reading = None
            for _attempt in range(self.CONFIRM_ATTEMPTS):
                self._sleep(self.CONFIRM_DELAY)
                reading = service.read()
                if reading.is_on == value or not reading.online:
                    break
            self.reading.emit(reading)
        except CloudError as exc:
            self.failed.emit(_("Could not switch: {err}", err=exc))
        except Exception as exc:
            self.failed.emit(_("Could not switch: {err}", err=exc))

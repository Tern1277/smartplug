"""Background worker: all network calls run outside the GUI thread."""

from __future__ import annotations

import time

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from .cloud import PlugService
from .i18n import _


class PlugWorker(QObject):
    reading = pyqtSignal(object)      # PlugReading
    switched = pyqtSignal(bool)       # new requested state
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)        # status text during a power cycle
    cycled = pyqtSignal(bool)         # power cycle finished (True = plug is on again)

    # Tuya Cloud updates the device status a moment after the command is accepted,
    # so an immediate read still shows the old state. Re-read until it matches.
    CONFIRM_ATTEMPTS = 6
    CONFIRM_DELAY = 1.0
    TURN_ON_ATTEMPTS = 3

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

    def _switch(self, service: PlugService, value: bool):
        """Send the command and re-read until the cloud reports the new state."""
        service.set_on(value)
        self.switched.emit(value)
        reading = None
        for _attempt in range(self.CONFIRM_ATTEMPTS):
            self._sleep(self.CONFIRM_DELAY)
            reading = service.read()
            if reading.is_on == value or not reading.online:
                break
        return reading

    @pyqtSlot(bool)
    def set_on(self, value: bool) -> None:
        try:
            self.reading.emit(self._switch(self._get_service(), value))
        except Exception as exc:  # CloudError or anything unexpected
            self.failed.emit(_("Could not switch: {err}", err=exc))

    @pyqtSlot(int)
    def power_cycle(self, seconds: int) -> None:
        """Turn the plug off, wait so the connected device fully loses power, turn it on."""
        try:
            service = self._get_service()
            self.progress.emit(_("Power cycle: turning off…"))
            self.reading.emit(self._switch(service, False))
        except Exception as exc:
            self.failed.emit(_("Could not switch: {err}", err=exc))
            self.cycled.emit(False)
            return

        for left in range(int(seconds), 0, -1):
            self.progress.emit(_("Power cycle: off, turning on in {s} s", s=left))
            self._sleep(1)

        error = None
        for _attempt in range(self.TURN_ON_ATTEMPTS):
            self.progress.emit(_("Power cycle: turning on…"))
            try:
                reading = self._switch(service, True)
                self.reading.emit(reading)
                if reading.is_on:
                    self.cycled.emit(True)
                    return
            except Exception as exc:
                error = exc
            self._sleep(2)
        self.failed.emit(_("Power cycle: could not turn the plug back on ({err}). "
                           "It may still be OFF — turn it on manually.",
                           err=error or _("state not confirmed")))
        self.cycled.emit(False)

"""Background worker: all network calls run outside the GUI thread."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from .cloud import CloudError, PlugService


class PlugWorker(QObject):
    reading = pyqtSignal(object)      # PlugReading
    switched = pyqtSignal(bool)       # new requested state
    failed = pyqtSignal(str)

    def __init__(self, service_factory):
        super().__init__()
        self._factory = service_factory
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
            self.failed.emit(f"Неочікувана помилка: {exc}")

    @pyqtSlot(bool)
    def set_on(self, value: bool) -> None:
        try:
            self._get_service().set_on(value)
            self.switched.emit(value)
            self.reading.emit(self._get_service().read())
        except CloudError as exc:
            self.failed.emit(f"Не вдалося перемкнути: {exc}")
        except Exception as exc:
            self.failed.emit(f"Не вдалося перемкнути: {exc}")

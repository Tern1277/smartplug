"""Settings dialog: Tuya keys, region, device choice, thresholds."""

from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from ..cloud import CloudError, TuyaCloudClient
from ..config import MIN_POLL_SECONDS, REGIONS, AppConfig

HELP = (
    "<b>Де взяти ключі:</b> iot.tuya.com → Cloud → Development → Create Cloud Project "
    "(Data Center: <i>Central Europe</i>) → Devices → Link App Account → "
    "відскануй QR у Smart Life (Я → ⚙ → сканер). Access ID та Access Secret — "
    "на вкладці Overview проєкту.<br>"
    "Ключі зберігаються лише на цьому ноутбуці у ~/.config/smartplug/config.json (права 600)."
)


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Налаштування — SmartPlug")
        self.setMinimumWidth(560)
        self._cfg = cfg
        self._devices = []

        help_label = QLabel(HELP)
        help_label.setWordWrap(True)
        help_label.setTextFormat(Qt.TextFormat.RichText)

        self.access_id = QLineEdit(cfg.access_id)
        self.access_id.setPlaceholderText("наприклад, 7xk3...")
        self.secret = QLineEdit(cfg.access_secret)
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        show = QPushButton("👁")
        show.setCheckable(True)
        show.setFixedWidth(36)
        show.setToolTip("Показати / сховати")
        show.toggled.connect(lambda on: self.secret.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        secret_row = QHBoxLayout()
        secret_row.addWidget(self.secret)
        secret_row.addWidget(show)

        self.region = QComboBox()
        for code, name in REGIONS.items():
            self.region.addItem(f"{name} ({code})", code)
        self.region.setCurrentIndex(max(0, self.region.findData(cfg.region)))

        self.find_btn = QPushButton("Підключитись і знайти пристрої")
        self.find_btn.clicked.connect(self._find_devices)
        self.device = QComboBox()
        if cfg.device_id:
            self.device.addItem(cfg.device_name or cfg.device_id, (cfg.device_id, cfg.device_name))

        self.poll = QSpinBox()
        self.poll.setRange(MIN_POLL_SECONDS, 3600)
        self.poll.setSuffix(" с")
        self.poll.setValue(cfg.poll_seconds)
        self.poll.setToolTip("Як часто питати хмару. Частіше = більше запитів до API.")

        self.nominal = QDoubleSpinBox()
        self.nominal.setRange(100, 260)
        self.nominal.setSuffix(" В")
        self.nominal.setValue(cfg.nominal_voltage)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(1, 30)
        self.tolerance.setSuffix(" %")
        self.tolerance.setValue(cfg.tolerance_pct)

        self.confirm = QCheckBox("Питати підтвердження перед перемиканням")
        self.confirm.setChecked(cfg.confirm_switch)
        self.notify = QCheckBox("Сповіщення про відключення та стрибки напруги")
        self.notify.setChecked(cfg.notifications)

        form = QFormLayout()
        form.addRow("Access ID:", self.access_id)
        form.addRow("Access Secret:", secret_row)
        form.addRow("Дата-центр:", self.region)
        form.addRow("", self.find_btn)
        form.addRow("Пристрій:", self.device)
        form.addRow("Опитувати кожні:", self.poll)
        form.addRow("Номінальна напруга:", self.nominal)
        form.addRow("Допустиме відхилення:", self.tolerance)
        form.addRow("", self.confirm)
        form.addRow("", self.notify)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _find_devices(self) -> None:
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            client = TuyaCloudClient(
                self.access_id.text().strip(), self.secret.text().strip(), self.region.currentData())
            devices = client.list_devices()
        except CloudError as exc:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Tuya Cloud", str(exc))
            return
        QGuiApplication.restoreOverrideCursor()

        self.device.clear()
        plugs = [d for d in devices if d.is_plug] or devices
        for d in plugs:
            self.device.addItem(d.label(), (d.id, d.name))
        if not plugs:
            QMessageBox.information(
                self, "Tuya Cloud",
                "Підключення є, але пристроїв не знайдено. Перевір, що акаунт Smart Life "
                "прив'язаний до проєкту (Devices → Link App Account) і вибрано правильний дата-центр.")
            return
        idx = self.device.findData((self._cfg.device_id, self._cfg.device_name))
        self.device.setCurrentIndex(max(0, idx))

    def _accept(self) -> None:
        if not self.access_id.text().strip() or not self.secret.text().strip():
            QMessageBox.warning(self, "SmartPlug", "Вкажи Access ID та Access Secret.")
            return
        if self.device.currentData() is None:
            QMessageBox.warning(self, "SmartPlug", "Натисни «Знайти пристрої» і вибери розетку.")
            return
        self.accept()

    def result_config(self) -> AppConfig:
        device_id, device_name = self.device.currentData() or ("", "")
        return replace(
            self._cfg,
            access_id=self.access_id.text().strip(),
            access_secret=self.secret.text().strip(),
            region=self.region.currentData(),
            device_id=device_id,
            device_name=device_name,
            poll_seconds=self.poll.value(),
            nominal_voltage=self.nominal.value(),
            tolerance_pct=self.tolerance.value(),
            confirm_switch=self.confirm.isChecked(),
            notifications=self.notify.isChecked(),
        )

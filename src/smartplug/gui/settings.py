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
from ..config import MAX_CYCLE_SECONDS, MIN_CYCLE_SECONDS, MIN_POLL_SECONDS, REGIONS, AppConfig
from ..i18n import _

HELP = (
    "<b>Where to get the keys:</b> iot.tuya.com → Cloud → Development → Create Cloud Project "
    "(Data Center: <i>Central Europe</i>) → Devices → Link App Account → scan the QR code "
    "in Smart Life (Me → scanner icon). Access ID and Access Secret are on the project's "
    "Overview tab.<br>The keys are stored only on this computer in "
    "~/.config/smartplug/config.json (mode 600)."
)


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Settings — SmartPlug"))
        self.setMinimumWidth(560)
        self._cfg = cfg

        help_label = QLabel(_(HELP))
        help_label.setWordWrap(True)
        help_label.setTextFormat(Qt.TextFormat.RichText)

        self.access_id = QLineEdit(cfg.access_id)
        self.access_id.setPlaceholderText(_("e.g. 7xk3..."))
        self.secret = QLineEdit(cfg.access_secret)
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        show = QPushButton("👁")
        show.setCheckable(True)
        show.setFixedWidth(36)
        show.setToolTip(_("Show / hide"))
        show.toggled.connect(lambda on: self.secret.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        secret_row = QHBoxLayout()
        secret_row.addWidget(self.secret)
        secret_row.addWidget(show)

        self.region = QComboBox()
        for code, name in REGIONS.items():
            self.region.addItem(f"{_(name)} ({code})", code)
        self.region.setCurrentIndex(max(0, self.region.findData(cfg.region)))

        self.find_btn = QPushButton(_("Connect and find devices"))
        self.find_btn.clicked.connect(self._find_devices)
        self.device = QComboBox()
        if cfg.device_id:
            self.device.addItem(cfg.device_name or cfg.device_id, (cfg.device_id, cfg.device_name))

        self.poll = QSpinBox()
        self.poll.setRange(MIN_POLL_SECONDS, 3600)
        self.poll.setSuffix(_(" s"))
        self.poll.setValue(cfg.poll_seconds)
        self.poll.setToolTip(_("How often to ask the cloud. More often = more API requests."))

        self.nominal = QDoubleSpinBox()
        self.nominal.setRange(100, 260)
        self.nominal.setSuffix(_(" V"))
        self.nominal.setValue(cfg.nominal_voltage)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(1, 30)
        self.tolerance.setSuffix(" %")
        self.tolerance.setValue(cfg.tolerance_pct)

        self.cycle = QSpinBox()
        self.cycle.setRange(MIN_CYCLE_SECONDS, MAX_CYCLE_SECONDS)
        self.cycle.setSuffix(_(" s"))
        self.cycle.setValue(cfg.power_cycle_seconds)
        self.cycle.setToolTip(_("How long the plug stays off during “Power cycle”. "
                                "A PC usually needs 15–30 s to fully lose power."))

        self.confirm = QCheckBox(_("Ask for confirmation before switching"))
        self.confirm.setChecked(cfg.confirm_switch)
        self.notify = QCheckBox(_("Notify about outages and voltage problems"))
        self.notify.setChecked(cfg.notifications)

        form = QFormLayout()
        form.addRow("Access ID:", self.access_id)
        form.addRow("Access Secret:", secret_row)
        form.addRow(_("Data center:"), self.region)
        form.addRow("", self.find_btn)
        form.addRow(_("Device:"), self.device)
        form.addRow(_("Poll every:"), self.poll)
        form.addRow(_("Nominal voltage:"), self.nominal)
        form.addRow(_("Allowed deviation:"), self.tolerance)
        form.addRow(_("Power cycle off time:"), self.cycle)
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
            QMessageBox.information(self, "Tuya Cloud", _(
                "Connected, but no devices found. Make sure the Smart Life account is linked to the "
                "project (Devices → Link App Account) and the right data center is selected."))
            return
        idx = self.device.findData((self._cfg.device_id, self._cfg.device_name))
        self.device.setCurrentIndex(max(0, idx))

    def _accept(self) -> None:
        if not self.access_id.text().strip() or not self.secret.text().strip():
            QMessageBox.warning(self, "SmartPlug", _("Enter the Access ID and Access Secret."))
            return
        if self.device.currentData() is None:
            QMessageBox.warning(self, "SmartPlug",
                                _("Click “Connect and find devices” and choose the plug."))
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
            power_cycle_seconds=self.cycle.value(),
            confirm_switch=self.confirm.isChecked(),
            notifications=self.notify.isChecked(),
        )

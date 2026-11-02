"""Main window: live cards, voltage/power charts, events, on/off control, tray."""

from __future__ import annotations

import math
import time
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QSystemTrayIcon, QMenu, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QApplication,
)

from ..analysis import (
    EVENT_TITLES, OFFLINE, EventTracker, format_duration, integrate_energy_kwh, stats,
    uptime_ratio,
)
from ..config import AppConfig, save_config
from ..devices import PlugReading
from ..poller import PlugWorker
from ..storage import Storage

RANGES = [
    ("1 година", 3600),
    ("6 годин", 6 * 3600),
    ("24 години", 86400),
    ("7 днів", 7 * 86400),
    ("30 днів", 30 * 86400),
]

GREEN, RED, GRAY, AMBER = "#2e9d57", "#d64545", "#8a8f98", "#d9962b"


def dot_icon(color: str) -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(6, 6, 52, 52)
    p.end()
    return QIcon(pix)


def fmt(value: float | None, unit: str, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f} {unit}"


class Card(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.title = QLabel(title)
        self.title.setStyleSheet("color: palette(placeholder-text);")
        self.value = QLabel("—")
        font = self.value.font()
        font.setPointSizeF(font.pointSizeF() * 1.9)
        font.setBold(True)
        self.value.setFont(font)
        self.sub = QLabel("")
        self.sub.setStyleSheet("color: palette(placeholder-text);")
        lay = QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set(self, value: str, sub: str = "", color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.sub.setText(sub)


class MainWindow(QMainWindow):
    poll_requested = pyqtSignal()
    switch_requested = pyqtSignal(bool)

    def __init__(self, cfg: AppConfig, storage: Storage, service_factory, demo: bool = False,
                 config_path=None):
        super().__init__()
        self.cfg = cfg
        self.storage = storage
        self.service_factory = service_factory  # callable(cfg) -> PlugService
        self.demo = demo
        self.config_path = config_path
        self.last: PlugReading | None = None
        self.tracker: EventTracker | None = None
        self._thread: QThread | None = None
        self._worker: PlugWorker | None = None
        self._busy = False
        self._really_quit = False
        self._tray_hint_shown = False

        self.setWindowTitle("SmartPlug — монітор розетки" + (" [ДЕМО]" if demo else ""))
        self.resize(1180, 820)
        pg.setConfigOptions(antialias=True)
        self._build_ui()
        self._build_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        if cfg.configured or demo:
            self._start()
        else:
            QTimer.singleShot(0, self.open_settings)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        self.device_label = QLabel()
        f = self.device_label.font()
        f.setPointSizeF(f.pointSizeF() * 1.3)
        f.setBold(True)
        self.device_label.setFont(f)
        top.addWidget(self.device_label)
        top.addStretch()
        top.addWidget(QLabel("Період:"))
        self.range_box = QComboBox()
        for name, secs in RANGES:
            self.range_box.addItem(name, secs)
        self.range_box.setCurrentIndex(2)
        self.range_box.currentIndexChanged.connect(self.refresh_history)
        top.addWidget(self.range_box)
        self.refresh_btn = QPushButton("⟳ Оновити")
        self.refresh_btn.clicked.connect(self._tick)
        top.addWidget(self.refresh_btn)
        settings_btn = QPushButton("⚙ Налаштування")
        settings_btn.clicked.connect(self.open_settings)
        settings_btn.setEnabled(not self.demo)
        top.addWidget(settings_btn)
        root.addLayout(top)

        grid = QGridLayout()
        self.card_grid = Card("Електрика вдома")
        self.card_relay = Card("Розетка")
        self.toggle_btn = QPushButton("—")
        self.toggle_btn.setMinimumHeight(34)
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self._toggle)
        self.card_relay.layout().addWidget(self.toggle_btn)
        self.card_power = Card("Потужність")
        self.card_voltage = Card("Напруга")
        self.card_current = Card("Струм")
        self.card_energy = Card("Енергія за період")
        for i, card in enumerate([self.card_grid, self.card_relay, self.card_power,
                                  self.card_voltage, self.card_current, self.card_energy]):
            grid.addWidget(card, 0, i)
        root.addLayout(grid)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.voltage_plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.voltage_plot.setLabel("left", "Напруга", units="V")
        self.voltage_plot.showGrid(x=True, y=True, alpha=0.25)
        self.voltage_curve = self.voltage_plot.plot(pen=pg.mkPen("#4e9be6", width=2))
        dash = Qt.PenStyle.DashLine
        self.nominal_line = pg.InfiniteLine(angle=0, pen=pg.mkPen(GRAY, style=dash))
        self.low_line = pg.InfiniteLine(angle=0, pen=pg.mkPen(RED, style=dash))
        self.high_line = pg.InfiniteLine(angle=0, pen=pg.mkPen(RED, style=dash))
        for line in (self.nominal_line, self.low_line, self.high_line):
            self.voltage_plot.addItem(line)

        self.power_plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.power_plot.setLabel("left", "Потужність", units="W")
        self.power_plot.showGrid(x=True, y=True, alpha=0.25)
        self.power_curve = self.power_plot.plot(
            pen=pg.mkPen(AMBER, width=2), fillLevel=0, brush=pg.mkBrush(217, 150, 43, 60))
        self.power_plot.setXLink(self.voltage_plot)

        for plot in (self.voltage_plot, self.power_plot):
            plot.setDownsampling(auto=True, mode="peak")
            plot.setClipToView(True)
        self._outage_regions: list = []

        splitter.addWidget(self.voltage_plot)
        splitter.addWidget(self.power_plot)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        bl.addWidget(self.stats_label)
        self.events_table = QTableWidget(0, 4)
        self.events_table.setHorizontalHeaderLabels(["Початок", "Тривалість", "Подія", "Значення"])
        self.events_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.events_table.verticalHeader().setVisible(False)
        self.events_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        bl.addWidget(self.events_table)
        splitter.addWidget(bottom)
        splitter.setSizes([300, 220, 200])

        root.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self._update_device_label()

    def _build_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(dot_icon(GRAY), self)
        menu = QMenu()
        show = QAction("Відкрити", self)
        show.triggered.connect(self._show_window)
        quit_ = QAction("Вийти", self)
        quit_.triggered.connect(self.quit)
        menu.addAction(show)
        menu.addSeparator()
        menu.addAction(quit_)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._show_window()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.setToolTip("SmartPlug")
        self.tray.show()

    def _update_device_label(self) -> None:
        name = self.cfg.device_name or self.cfg.device_id or "Пристрій не вибрано"
        self.device_label.setText("🔌 " + name)
        self.nominal_line.setValue(self.cfg.nominal_voltage)
        self.low_line.setValue(self.cfg.voltage_low)
        self.high_line.setValue(self.cfg.voltage_high)

    # ------------------------------------------------------------ worker
    def _start(self) -> None:
        self._stop_worker()
        self.tracker = EventTracker(
            self.storage, self.cfg.device_id, self.cfg.voltage_low, self.cfg.voltage_high)
        self.last = self.storage.last_reading(self.cfg.device_id)

        cfg = self.cfg
        self._thread = QThread(self)
        self._worker = PlugWorker(lambda: self.service_factory(cfg))
        self._worker.moveToThread(self._thread)
        self.poll_requested.connect(self._worker.poll)
        self.switch_requested.connect(self._worker.set_on)
        self._worker.reading.connect(self._on_reading)
        self._worker.failed.connect(self._on_error)
        self._thread.start()

        self.timer.start(self.cfg.poll_seconds * 1000)
        self._update_device_label()
        self.refresh_history()
        self._tick()

    def _stop_worker(self) -> None:
        if self._thread is not None:
            self.timer.stop()
            try:
                self.poll_requested.disconnect()
                self.switch_requested.disconnect()
            except TypeError:
                pass
            self._thread.quit()
            self._thread.wait(5000)
            self._thread = None
            self._worker = None

    def _tick(self) -> None:
        if self._worker is None or self._busy:
            return
        self._busy = True
        self.statusBar().showMessage("Оновлення…")
        self.poll_requested.emit()

    # ----------------------------------------------------------- results
    def _on_reading(self, r: PlugReading) -> None:
        self._busy = False
        self.storage.add_reading(self.cfg.device_id, r)
        notices = self.tracker.process(r) if self.tracker else []
        self.last = r
        self._show_live(r)
        self.refresh_history()
        stamp = datetime.fromtimestamp(r.ts).strftime("%H:%M:%S")
        self.statusBar().showMessage(f"Оновлено о {stamp} · наступне через {self.cfg.poll_seconds} с")
        if self.tray and self.cfg.notifications:
            for n in notices:
                icon = (QSystemTrayIcon.MessageIcon.Warning if n.critical
                        else QSystemTrayIcon.MessageIcon.Information)
                self.tray.showMessage(n.title, n.text, icon, 10000)

    def _on_error(self, message: str) -> None:
        self._busy = False
        self.statusBar().showMessage("⚠ " + message)
        self.toggle_btn.setEnabled(bool(self.last and self.last.online))

    def _show_live(self, r: PlugReading) -> None:
        if not r.online:
            since = self._offline_since()
            sub = f"немає зв'язку {format_duration(time.time() - since)}" if since else ""
            self.card_grid.set("Offline", sub or "можливо, немає світла", RED)
            self.card_relay.set("—", "")
            for card in (self.card_power, self.card_voltage, self.card_current):
                card.set("—")
            self.toggle_btn.setText("Немає зв'язку")
            self.toggle_btn.setEnabled(False)
            self._set_tray(RED, "Розетка offline — можливо, немає світла")
            return

        self.card_grid.set("Є ✓", "розетка на зв'язку", GREEN)
        if r.is_on is None:
            self.card_relay.set("—", "реле не знайдено")
            self.toggle_btn.setEnabled(False)
        else:
            self.card_relay.set("Увімкнена" if r.is_on else "Вимкнена", "",
                                GREEN if r.is_on else GRAY)
            self.toggle_btn.setText("Вимкнути" if r.is_on else "Увімкнути")
            self.toggle_btn.setEnabled(True)

        self.card_power.set(fmt(r.power_w, "Вт"))
        v = r.voltage_v
        v_color = None
        v_sub = ""
        if v is not None and (v < self.cfg.voltage_low or v > self.cfg.voltage_high):
            v_color, v_sub = RED, "поза нормою"
        self.card_voltage.set(fmt(v, "В"), v_sub, v_color)
        self.card_current.set(fmt(r.current_a, "А", 2))
        if not r.has_metering:
            self.card_power.set("—", "розетка без вимірювання")

        tip = f"Світло є · {fmt(r.power_w, 'Вт')} · {fmt(v, 'В')}"
        self._set_tray(AMBER if v_color else GREEN, tip)

    def _offline_since(self) -> float | None:
        if self.tracker and self.tracker.is_open(OFFLINE):
            return self.tracker._open[OFFLINE].ts_start
        return None

    def _set_tray(self, color: str, tip: str) -> None:
        self.setWindowIcon(dot_icon(color))
        if self.tray:
            self.tray.setIcon(dot_icon(color))
            self.tray.setToolTip("SmartPlug\n" + tip)

    # ----------------------------------------------------------- history
    def refresh_history(self) -> None:
        if not self.cfg.device_id:
            return
        span = self.range_box.currentData()
        now = time.time()
        since = now - span
        rows = self.storage.readings(self.cfg.device_id, since)
        max_gap = max(3 * self.cfg.poll_seconds, 180)

        xs, vs, ps = [], [], []
        prev_ts = None
        for r in rows:
            if prev_ts is not None and r.ts - prev_ts > max_gap:
                xs.append(prev_ts + 1); vs.append(math.nan); ps.append(math.nan)
            xs.append(r.ts)
            vs.append(r.voltage_v if r.online and r.voltage_v is not None else math.nan)
            ps.append(r.power_w if r.online and r.power_w is not None else math.nan)
            prev_ts = r.ts
        self.voltage_curve.setData(xs, vs, connect="finite")
        self.power_curve.setData(xs, ps, connect="finite")
        self.voltage_plot.setXRange(since, now, padding=0.01)

        for region in self._outage_regions:
            self.voltage_plot.removeItem(region)
        self._outage_regions = []
        events = self.storage.events(self.cfg.device_id, since)
        for ev in events:
            if ev.kind != OFFLINE:
                continue
            region = pg.LinearRegionItem(
                (max(ev.ts_start, since), ev.ts_end or now), movable=False,
                brush=pg.mkBrush(214, 69, 69, 45), pen=pg.mkPen(None))
            region.setZValue(-10)
            self.voltage_plot.addItem(region)
            self._outage_regions.append(region)

        energy = integrate_energy_kwh(rows, max_gap=max_gap)
        self.card_energy.set(f"{energy:.3f} кВт·год", self.range_box.currentText())
        self._update_stats(rows, events, span)
        self._fill_events(events, now)

    def _update_stats(self, rows, events, span) -> None:
        v = stats(r.voltage_v for r in rows if r.online)
        p = stats(r.power_w for r in rows if r.online)
        up = uptime_ratio(rows)
        outages = [e for e in events if e.kind == OFFLINE]
        dips = [e for e in events if e.kind != OFFLINE]
        parts = []
        if v.count:
            parts.append(f"<b>Напруга:</b> мін {v.min:.0f} В · сер {v.avg:.0f} В · макс {v.max:.0f} В")
        if p.count:
            parts.append(f"<b>Потужність:</b> сер {p.avg:.0f} Вт · пік {p.max:.0f} Вт")
        if up is not None:
            parts.append(f"<b>На зв'язку:</b> {up * 100:.0f}% часу")
        parts.append(f"<b>Відключень:</b> {len(outages)} · <b>стрибків напруги:</b> {len(dips)}")
        if not rows:
            parts = ["Ще немає даних за цей період — історія накопичується, поки програма працює."]
        self.stats_label.setText(" &nbsp;|&nbsp; ".join(parts))

    def _fill_events(self, events, now) -> None:
        self.events_table.setRowCount(len(events))
        for row, ev in enumerate(events):
            start = datetime.fromtimestamp(ev.ts_start).strftime("%d.%m %H:%M:%S")
            dur = format_duration((ev.ts_end or now) - ev.ts_start)
            if ev.ts_end is None:
                dur += " (триває)"
            value = "" if ev.value is None else f"{ev.value:.0f} В"
            for col, text in enumerate([start, dur, EVENT_TITLES.get(ev.kind, ev.kind), value]):
                item = QTableWidgetItem(text)
                if ev.ts_end is None:
                    item.setForeground(QColor(RED))
                self.events_table.setItem(row, col, item)
        self.events_table.resizeColumnsToContents()
        self.events_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    # ----------------------------------------------------------- actions
    def _toggle(self) -> None:
        if not self.last or self.last.is_on is None or self._worker is None:
            return
        target = not self.last.is_on
        if self.cfg.confirm_switch:
            verb = "Увімкнути" if target else "Вимкнути"
            warn = "" if target else "\n\nВсе, що підключено до розетки, знеструмиться."
            answer = QMessageBox.question(
                self, "SmartPlug", f"{verb} розетку «{self.cfg.device_name or 'розетка'}»?{warn}")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.toggle_btn.setEnabled(False)
        self.statusBar().showMessage("Надсилаю команду…")
        self.switch_requested.emit(target)

    def open_settings(self) -> None:
        if self.demo:
            return
        from .settings import SettingsDialog

        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            self.cfg = dlg.result_config()
            save_config(self.cfg, self.config_path)
            self._start()
        elif not self.cfg.configured:
            self.statusBar().showMessage("Відкрий ⚙ Налаштування і встав ключі з iot.tuya.com")

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit(self) -> None:
        self._really_quit = True
        self.close()

    def closeEvent(self, event) -> None:
        if self.tray and not self._really_quit:
            # keep monitoring in the background
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.showMessage("SmartPlug", "Працюю у треї. Вийти: ПКМ на іконці → Вийти.",
                                      QSystemTrayIcon.MessageIcon.Information, 5000)
            return
        self._stop_worker()
        self.storage.close()
        event.accept()
        QApplication.quit()

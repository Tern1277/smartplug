"""Entry point: `smartplug` (real plug) or `smartplug --demo` (simulated)."""

from __future__ import annotations

import argparse
import sys

from .cloud import PlugService, TuyaCloudClient
from .config import AppConfig, data_dir, load_config
from .demo import DEMO_DEVICE_ID, DemoClient, seed_history
from .storage import Storage


def cloud_service(cfg: AppConfig) -> PlugService:
    client = TuyaCloudClient(cfg.access_id, cfg.access_secret, cfg.region)
    return PlugService(client, cfg.device_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Монітор і керування розумною розеткою Tuya / Smart Life")
    parser.add_argument("--demo", action="store_true", help="симульована розетка, ключі не потрібні")
    parser.add_argument("--poll", type=int, help="інтервал опитування в секундах (для цього запуску)")
    args = parser.parse_args(argv)

    from PyQt6.QtWidgets import QApplication

    from .gui.mainwindow import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("SmartPlug")
    app.setDesktopFileName("smartplug")
    app.setQuitOnLastWindowClosed(False)

    if args.demo:
        cfg = AppConfig(device_id=DEMO_DEVICE_ID, device_name="Демо-розетка", poll_seconds=3)
        storage = Storage(data_dir() / "demo.db")
        seed_history(storage)
        demo_client = DemoClient()
        factory = lambda _cfg: PlugService(demo_client, DEMO_DEVICE_ID)  # noqa: E731
    else:
        cfg = load_config()
        storage = Storage(data_dir() / "history.db")
        storage.prune(older_than_days=90)
        factory = cloud_service
    if args.poll:
        cfg.poll_seconds = max(3 if args.demo else 10, args.poll)

    window = MainWindow(cfg, storage, factory, demo=args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

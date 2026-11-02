"""Entry point: `smartplug` (real plug) or `smartplug --demo` (simulated)."""

from __future__ import annotations

import argparse
import sys

from .cloud import PlugService, TuyaCloudClient
from .config import AppConfig, data_dir, load_config
from .i18n import LANGUAGES, _, set_language
from .demo import DEMO_DEVICE_ID, DemoClient, seed_history
from .storage import Storage


def cloud_service(cfg: AppConfig) -> PlugService:
    client = TuyaCloudClient(cfg.access_id, cfg.access_secret, cfg.region)
    return PlugService(client, cfg.device_id)


def main(argv: list[str] | None = None) -> int:
    saved = load_config()
    set_language(saved.language)
    parser = argparse.ArgumentParser(description=_("Monitor and control a Tuya / Smart Life smart plug"))
    parser.add_argument("--demo", action="store_true", help=_("simulated plug, no keys needed"))
    parser.add_argument("--poll", type=int, help=_("poll interval in seconds (this run only)"))
    parser.add_argument("--lang", choices=sorted(LANGUAGES), help=_("interface language"))
    args = parser.parse_args(argv)
    if args.lang:
        set_language(args.lang)

    from PyQt6.QtWidgets import QApplication

    from .gui.mainwindow import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("SmartPlug")
    app.setDesktopFileName("smartplug")
    app.setQuitOnLastWindowClosed(False)

    if args.demo:
        cfg = AppConfig(device_id=DEMO_DEVICE_ID, device_name="Demo plug", poll_seconds=3,
                        language=saved.language)
        storage = Storage(data_dir() / "demo.db")
        seed_history(storage)
        demo_client = DemoClient()
        factory = lambda _cfg: PlugService(demo_client, DEMO_DEVICE_ID)  # noqa: E731
    else:
        cfg = saved
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

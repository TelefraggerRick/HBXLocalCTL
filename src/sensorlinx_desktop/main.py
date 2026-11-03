"""Entry point for the Cross-Platform (Windows & Linux) SensorLinx Desktop App."""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import List, Optional

from PySide6.QtWidgets import QApplication
import qasync

from .config import AppConfig
from .coordinator import SensorlinxCoordinator
from .main_window import DARK_STYLESHEET, MainWindow


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sensorlinx-desktop",
        description="Cross-platform desktop application for HBX Controls / SensorLinx HVAC systems.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Start directly in Offline Local LAN Mode (TCP port 2000, no cloud required).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Start directly in interactive Demo / Simulation Mode.",
    )
    parser.add_argument(
        "--unit",
        choices=["F", "C", "f", "c"],
        default=None,
        help="Override display temperature unit (°F or °C).",
    )
    parser.add_argument(
        "--no-local",
        action="store_true",
        help="Do not automatically connect to local LAN port 2000 devices on startup.",
    )
    return parser.parse_args(argv)


async def async_main(window: MainWindow, args: argparse.Namespace) -> None:
    """Initialize connection mode once the event loop starts."""
    if not args.no_local:
        await window.local_manager.start()

    if args.local:
        window.config.connection_mode = "local"
        await window.coordinator.start_local_mode(window.local_manager)
        return

    if args.demo:
        window.config.connection_mode = "demo"
        await window.coordinator.start_demo_mode()
        return

    pref_mode = window.config.connection_mode
    if pref_mode == "demo":
        await window.coordinator.start_demo_mode()
        return

    if pref_mode == "cloud":
        email, password, remember = window.config.load_credentials()
        if remember and email and password:
            ok = await window.coordinator.start_live_mode(email, password)
            if ok:
                return

    # Default to Local LAN Mode (no cloud needed!)
    await window.coordinator.start_local_mode(window.local_manager)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SensorLinx Desktop")
    app.setOrganizationName("HBXControlsCommunity")
    app.setStyleSheet(DARK_STYLESHEET)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    config = AppConfig()
    if args.unit:
        config.temperature_unit = args.unit.upper()

    coordinator = SensorlinxCoordinator(scan_interval_sec=config.scan_interval)
    window = MainWindow(coordinator, config)
    window.show()

    with loop:
        loop.create_task(async_main(window, args))
        return loop.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())

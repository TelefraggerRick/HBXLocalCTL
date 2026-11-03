"""Main Desktop Application Window for SensorLinx / HBX Controls."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig
from .coordinator import SensorlinxCoordinator
from .local_probe import LocalLanManager
from .widgets.eco_panel import EcoDevicePanel
from .widgets.local_lan_panel import LocalLanPanel
from .widgets.login_dialog import LoginDialog
from .widgets.thm_panel import ThmDevicePanel
from .widgets.weather_panel import SystemOverviewPanel
from .widgets.zon_panel import ZonDevicePanel


DARK_STYLESHEET = """
QMainWindow, QDialog, QWidget {
    background-color: #0B0F17;
    color: #E2E8F0;
    font-family: "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}
QFrame#TopBar {
    background-color: #111827;
    border-bottom: 1px solid #1F2937;
}
QFrame#SidebarFrame {
    background-color: #111827;
    border-right: 1px solid #1F2937;
}
QFrame#CardFrame {
    background-color: #151D2C;
    border: 1px solid #263248;
    border-radius: 10px;
}
QGroupBox {
    background-color: #131B29;
    border: 1px solid #243044;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: 600;
    color: #93C5FD;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLabel#SectionHeader {
    font-size: 17px;
    font-weight: 700;
    color: #F8FAFC;
    background: transparent;
}
QLabel#CardTitle {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    color: #94A3B8;
    background: transparent;
}
QLabel#HeroMetric {
    font-size: 24px;
    font-weight: 700;
    color: #F97316;
    background: transparent;
}
QLabel#HeroMetricSmall {
    font-size: 18px;
    font-weight: 700;
    color: #38BDF8;
    background: transparent;
}
QLabel#StatusText {
    font-size: 14px;
    font-weight: 600;
    color: #34D399;
    background: transparent;
}
QLabel#MutedText {
    font-size: 12px;
    color: #94A3B8;
    background: transparent;
}
QLabel {
    background: transparent;
}
QListWidget#NavList {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 6px;
}
QListWidget#NavList::item {
    padding: 10px 12px;
    border-radius: 7px;
    margin-bottom: 4px;
    color: #CBD5E1;
    font-weight: 500;
}
QListWidget#NavList::item:hover {
    background-color: #1E293B;
}
QListWidget#NavList::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton {
    background-color: #1E293B;
    color: #E2E8F0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #334155;
}
QPushButton#PrimaryButton {
    background-color: #EA580C;
    color: #FFFFFF;
    border: 1px solid #F97316;
}
QPushButton#PrimaryButton:hover {
    background-color: #F97316;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #0F172A;
    color: #F1F5F9;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 8px;
}
QTabWidget::pane {
    border: 1px solid #243044;
    border-radius: 8px;
    background-color: #0E1522;
}
QTabBar::tab {
    background-color: #151D2C;
    color: #94A3B8;
    border: 1px solid #243044;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #2563EB;
    color: #FFFFFF;
}
QTableWidget {
    background-color: #0F172A;
    alternate-background-color: #151D2C;
    gridline-color: #1E293B;
    border: 1px solid #243044;
    border-radius: 6px;
}
QHeaderView::section {
    background-color: #1E293B;
    color: #CBD5E1;
    padding: 6px;
    border: none;
    font-weight: 600;
}
QStatusBar {
    background-color: #111827;
    color: #94A3B8;
    border-top: 1px solid #1F2937;
}
"""


class MainWindow(QMainWindow):
    """Primary desktop window hosting sidebar navigation and device panels."""

    def __init__(self, coordinator: SensorlinxCoordinator, config: AppConfig, local_manager: Optional[LocalLanManager] = None) -> None:
        super().__init__()
        self.coordinator = coordinator
        self.config = config
        self.local_manager = local_manager or LocalLanManager()
        self.unit: str = self.config.temperature_unit
        self.device_panels: Dict[str, QWidget] = {}

        self.setWindowTitle("HBX Controls • SensorLinx Home Heating & Cooling")
        self.resize(1360, 860)

        icon_path = Path(__file__).parent / "assets" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._setup_tray(icon_path)

        # Connect coordinator signals
        self.coordinator.data_updated.connect(self._on_data_updated)
        self.coordinator.data_updated.connect(self.local_manager.on_cloud_data_updated)
        self.coordinator.status_changed.connect(self._on_status_changed)
        self.coordinator.error_occurred.connect(self._on_error_occurred)
        self.coordinator.auth_failed.connect(self._on_auth_failed)
        self.local_manager.state_updated.connect(self._on_local_lan_state_updated)

    def _on_local_lan_state_updated(self) -> None:
        self.coordinator.on_local_lan_updated(self.local_manager)

    def _build_ui(self) -> None:
        central = QWidget()
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Top Bar
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_lay = QHBoxLayout(top_bar)
        top_lay.setContentsMargins(18, 10, 18, 10)
        top_lay.setSpacing(12)

        app_title = QLabel("HBX Controls  •  SensorLinx Desktop")
        app_title.setObjectName("SectionHeader")
        top_lay.addWidget(app_title)

        self.mode_badge = QLabel("CONNECTING")
        self.mode_badge.setStyleSheet(
            "background-color: #1E3A8A; color: #93C5FD; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;"
        )
        top_lay.addWidget(self.mode_badge)
        top_lay.addStretch()

        top_lay.addWidget(QLabel("Display Units:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["°F (Fahrenheit)", "°C (Celsius)"])
        self.unit_combo.setCurrentIndex(1 if self.unit == "C" else 0)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        top_lay.addWidget(self.unit_combo)

        self.refresh_btn = QPushButton("↻ Refresh Now")
        self.refresh_btn.clicked.connect(self._on_manual_refresh)
        top_lay.addWidget(self.refresh_btn)

        self.account_btn = QPushButton("Connection Mode (Local / Cloud / Demo)")
        self.account_btn.clicked.connect(self.prompt_connection_dialog)
        top_lay.addWidget(self.account_btn)

        root_lay.addWidget(top_bar)

        # Splitter: Left Sidebar + Right Stacked Content
        splitter = QSplitter(Qt.Orientation.Horizontal)

        sidebar = QFrame()
        sidebar.setObjectName("SidebarFrame")
        sidebar.setMinimumWidth(260)
        sidebar.setMaximumWidth(320)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(10, 14, 10, 14)

        nav_hdr = QLabel("BUILDINGS & DEVICES")
        nav_hdr.setObjectName("CardTitle")
        sb_lay.addWidget(nav_hdr)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("NavList")
        self.nav_list.currentItemChanged.connect(self._on_nav_item_changed)
        sb_lay.addWidget(self.nav_list, 1)

        splitter.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.overview_panel = SystemOverviewPanel(self.coordinator, unit=self.unit)
        self.overview_panel.navigate_to_device.connect(self.select_device_in_sidebar)
        self.stack.addWidget(self.overview_panel)

        self.local_lan_panel = LocalLanPanel(self.local_manager)
        self.stack.addWidget(self.local_lan_panel)

        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_lay.addWidget(splitter, 1)

        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")

    def _setup_tray(self, icon_path: Path) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return
        self.tray_icon = QSystemTrayIcon(self)
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        menu = QMenu()
        show_act = QAction("Show SensorLinx Window", self)
        show_act.triggered.connect(self.showNormal)
        refresh_act = QAction("Refresh Now", self)
        refresh_act.triggered.connect(self._on_manual_refresh)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        menu.addAction(show_act)
        menu.addAction(refresh_act)
        menu.addSeparator()
        menu.addAction(quit_act)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _on_unit_changed(self, index: int) -> None:
        new_unit = "C" if index == 1 else "F"
        self.unit = new_unit
        self.config.temperature_unit = new_unit
        self.overview_panel.set_unit(new_unit)
        for panel in self.device_panels.values():
            if hasattr(panel, "set_unit"):
                panel.set_unit(new_unit)

    def _on_manual_refresh(self) -> None:
        self.status_bar.showMessage("Refreshing devices from SensorLinx...")
        asyncio.ensure_future(self.coordinator.async_refresh())

    def _on_status_changed(self, msg: str) -> None:
        self.status_bar.setStyleSheet("color: #94A3B8;")
        self.status_bar.showMessage(msg)

    def _on_error_occurred(self, err: str) -> None:
        self.status_bar.setStyleSheet("color: #F87171; font-weight: 600;")
        self.status_bar.showMessage(f"⚠ {err}")

    def _on_auth_failed(self, err: str) -> None:
        self._on_error_occurred(err)
        self.prompt_connection_dialog(error_text=err)

    def _on_data_updated(self, data: dict) -> None:
        is_local = bool(data.get("is_local"))
        is_demo = bool(data.get("is_demo"))
        if is_local:
            self.mode_badge.setText("LOCAL LAN MODE (NO CLOUD)")
            self.mode_badge.setStyleSheet(
                "background-color: #0E7490; color: #CFFAFE; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;"
            )
        elif is_demo:
            self.mode_badge.setText("DEMO / SIMULATION MODE")
            self.mode_badge.setStyleSheet(
                "background-color: #065F46; color: #A7F3D0; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;"
            )
        else:
            self.mode_badge.setText("LIVE CLOUD CONNECTED")
            self.mode_badge.setStyleSheet(
                "background-color: #1E40AF; color: #BFDBFE; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 11px;"
            )

        devices = data.get("devices") or {}

        # Remove stale device panels when switching modes (e.g. Demo -> Local LAN)
        for stale_id in [did for did in self.device_panels if did not in devices]:
            old_panel = self.device_panels.pop(stale_id)
            self.stack.removeWidget(old_panel)
            old_panel.deleteLater()

        # Remember current selection
        current_key = "overview"
        cur_item = self.nav_list.currentItem()
        if cur_item and cur_item.data(Qt.ItemDataRole.UserRole):
            current_key = cur_item.data(Qt.ItemDataRole.UserRole)

        # Create any missing device panels
        for dev_id, dev in devices.items():
            dtype = (dev.get("parameters", {}).get("device_type") or dev.get("deviceType") or "ECO").upper()
            if dev_id not in self.device_panels:
                if dtype == "THM":
                    panel = ThmDevicePanel(self.coordinator, dev_id, unit=self.unit)
                elif dtype == "ZON":
                    panel = ZonDevicePanel(self.coordinator, dev_id, unit=self.unit)
                    panel.navigate_to_device.connect(self.select_device_in_sidebar)
                    panel.request_cloud_snapshot_sync.connect(self.prompt_cloud_snapshot_sync)
                else:
                    panel = EcoDevicePanel(self.coordinator, dev_id, unit=self.unit)
                self.device_panels[dev_id] = panel
                self.stack.addWidget(panel)

        # Rebuild navigation sidebar if set of devices changed or empty
        existing_keys = [
            self.nav_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.nav_list.count())
        ]
        expected_keys = ["overview", "local_lan"] + list(devices.keys())
        if existing_keys != expected_keys:
            self.nav_list.blockSignals(True)
            self.nav_list.clear()

            ov_item = QListWidgetItem("🏠  System Overview & Weather")
            ov_item.setData(Qt.ItemDataRole.UserRole, "overview")
            self.nav_list.addItem(ov_item)

            lan_item = QListWidgetItem("📡  Local LAN Stream (:2000)")
            lan_item.setData(Qt.ItemDataRole.UserRole, "local_lan")
            self.nav_list.addItem(lan_item)

            icon_map = {"ECO": "🔥", "ZON": "🔀", "THM": "🌡️"}
            for dev_id, dev in devices.items():
                dtype = (dev.get("parameters", {}).get("device_type") or dev.get("deviceType") or "ECO").upper()
                icon_ch = icon_map.get(dtype, "⚙️")
                label = f"{icon_ch}  {dev.get('name', dev_id)} ({dtype})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, dev_id)
                self.nav_list.addItem(item)

            self.nav_list.blockSignals(False)
            self.select_device_in_sidebar(current_key if current_key in expected_keys else "overview")

        # Refresh all panels
        self.overview_panel.refresh_from_coordinator()
        for dev_id, panel in list(self.device_panels.items()):
            if dev_id in devices and hasattr(panel, "refresh_from_coordinator"):
                panel.refresh_from_coordinator()

    def _on_nav_item_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key == "overview":
            self.stack.setCurrentWidget(self.overview_panel)
        elif key == "local_lan":
            self.stack.setCurrentWidget(self.local_lan_panel)
        elif key in self.device_panels:
            self.stack.setCurrentWidget(self.device_panels[key])

    def select_device_in_sidebar(self, target_key: str) -> None:
        for i in range(self.nav_list.count()):
            item = self.nav_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == target_key:
                self.nav_list.setCurrentItem(item)
                return

    def prompt_connection_dialog(self, error_text: str = "") -> None:
        email, password, remember = self.config.load_credentials()
        dlg = LoginDialog(
            initial_email=email,
            initial_password=password,
            remember=remember,
            error_text=error_text,
            parent=self,
        )
        if dlg.exec() == LoginDialog.DialogCode.Accepted:
            if dlg.use_local_mode:
                self.config.connection_mode = "local"
                asyncio.ensure_future(self._switch_to_local_mode())
            elif dlg.use_demo_mode:
                self.config.connection_mode = "demo"
                asyncio.ensure_future(self.coordinator.start_demo_mode())
            else:
                if not dlg.email or not dlg.password:
                    self.prompt_connection_dialog(
                        error_text="Please enter both email and password, or choose Local LAN / Demo Mode."
                    )
                    return
                self.config.connection_mode = "cloud"
                self.config.save_credentials(dlg.email, dlg.password, dlg.remember)
                asyncio.ensure_future(self.coordinator.start_live_mode(dlg.email, dlg.password))

    async def _switch_to_local_mode(self) -> None:
        if not self.local_manager.is_running:
            await self.local_manager.start()
        await self.coordinator.start_local_mode(self.local_manager)

    def prompt_cloud_snapshot_sync(self) -> None:
        """Fetch official Cloud API device list & THM-0600 thermostats into the Local LAN Mode snapshot."""
        email, password, remember = self.config.load_credentials()
        if email and password:
            asyncio.ensure_future(
                self.coordinator.sync_cloud_snapshot_into_local_mode(email, password, self.local_manager)
            )
            return

        dlg = LoginDialog(
            initial_email=email,
            initial_password=password,
            remember=remember,
            error_text="Sign in once to import your linked THM-0600 thermostats & ZON-0600 config into Local LAN Mode:",
            parent=self,
        )
        if dlg.exec() == LoginDialog.DialogCode.Accepted and dlg.email and dlg.password:
            self.config.save_credentials(dlg.email, dlg.password, dlg.remember)
            asyncio.ensure_future(
                self.coordinator.sync_cloud_snapshot_into_local_mode(dlg.email, dlg.password, self.local_manager)
            )

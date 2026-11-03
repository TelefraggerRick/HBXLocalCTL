"""ECO-0600 Hydronic Heat Pump, Buffer Tank, Outdoor Reset, Staging, Backup & DHW Panel."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from pysensorlinx import SensorlinxDevice, Temperature, TemperatureDelta

from ..coordinator import SensorlinxCoordinator
from ..demo_client import DemoSensorlinxClient
from ..models import OutdoorResetCurveConfig, UnitHelper
from .outdoor_reset_chart import OutdoorResetChartWidget


def _scalar_f(val: Any, default: float) -> float:
    if val is None or val == "off":
        return default
    if hasattr(val, "to_fahrenheit"):
        return float(val.to_fahrenheit())
    if hasattr(val, "value"):
        return float(val.value)
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class EcoDevicePanel(QWidget):
    """Full monitoring and configuration view for an HBX ECO-0600 controller."""

    def __init__(
        self,
        coordinator: SensorlinxCoordinator,
        device_id: str,
        unit: str = "F",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.device_id = device_id
        self.unit = unit.upper()
        self._updating_ui = False

        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        # Header bar
        header_frame = QFrame()
        header_frame.setObjectName("CardFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title_col = QVBoxLayout()
        self.title_label = QLabel("ECO-0600 Hydronic Controller")
        self.title_label.setObjectName("SectionHeader")
        self.subtitle_label = QLabel("Sync Code: — | Firmware: —")
        self.subtitle_label.setObjectName("MutedText")
        title_col.addWidget(self.title_label)
        title_col.addWidget(self.subtitle_label)
        header_layout.addLayout(title_col)
        header_layout.addStretch()

        # Quick HVAC Mode Priority selector in header
        header_layout.addWidget(QLabel("HVAC Mode Priority:"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["auto", "heat", "cool"])
        self.priority_combo.currentTextChanged.connect(self._on_priority_changed)
        header_layout.addWidget(self.priority_combo)

        self.perm_hd_chk = QCheckBox("Permanent Heat Demand")
        self.perm_hd_chk.toggled.connect(self._on_perm_hd_toggled)
        header_layout.addWidget(self.perm_hd_chk)

        self.perm_cd_chk = QCheckBox("Permanent Cool Demand")
        self.perm_cd_chk.toggled.connect(self._on_perm_cd_toggled)
        header_layout.addWidget(self.perm_cd_chk)

        root_layout.addWidget(header_frame)

        # Top telemetry cards (Buffer Tank, Outdoor, DHW Tank, Stages & Backup, Pumps & Demands)
        cards_layout = QGridLayout()
        cards_layout.setSpacing(10)

        self.tank_card_val = QLabel("—")
        self.tank_card_val.setObjectName("HeroMetric")
        self.tank_card_sub = QLabel("Target: —")
        self.tank_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Buffer Tank", self.tank_card_val, self.tank_card_sub), 0, 0
        )

        self.outdoor_card_val = QLabel("—")
        self.outdoor_card_val.setObjectName("HeroMetric")
        self.outdoor_card_sub = QLabel("Shutdown Status: Normal")
        self.outdoor_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Outdoor Sensor", self.outdoor_card_val, self.outdoor_card_sub), 0, 1
        )

        self.dhw_card_val = QLabel("—")
        self.dhw_card_val.setObjectName("HeroMetric")
        self.dhw_card_sub = QLabel("Target: — | Status: —")
        self.dhw_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Domestic Hot Water (DHW)", self.dhw_card_val, self.dhw_card_sub), 0, 2
        )

        self.stages_card_val = QLabel("—")
        self.stages_card_val.setObjectName("StatusText")
        self.stages_card_sub = QLabel("Runtimes: —")
        self.stages_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Heat Pump Stages & Backup", self.stages_card_val, self.stages_card_sub), 0, 3
        )

        self.pumps_card_val = QLabel("—")
        self.pumps_card_val.setObjectName("StatusText")
        self.pumps_card_sub = QLabel("Demands: —")
        self.pumps_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Pumps, Valve & Demands", self.pumps_card_val, self.pumps_card_sub), 0, 4
        )

        root_layout.addLayout(cards_layout)

        # Tab widget for detailed configuration
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_outdoor_reset_tab(), "Outdoor Reset Curve & Tank Settings")
        self.tabs.addTab(self._build_staging_tab(), "Heat Pump Staging & Rotation")
        self.tabs.addTab(self._build_backup_dhw_tab(), "Backup Boiler & DHW Controls")
        root_layout.addWidget(self.tabs, 1)

    def _make_metric_card(self, title: str, primary_lbl: QLabel, sub_lbl: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CardFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)
        hdr = QLabel(title.upper())
        hdr.setObjectName("CardTitle")
        primary_lbl.setWordWrap(True)
        sub_lbl.setWordWrap(True)
        lay.addWidget(hdr)
        lay.addWidget(primary_lbl)
        lay.addWidget(sub_lbl)
        return frame

    def _build_outdoor_reset_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        # Left column: Interactive chart + Demo outdoor temp simulator
        left_col = QVBoxLayout()
        self.chart_widget = OutdoorResetChartWidget()
        self.chart_widget.curve_edited.connect(self._on_chart_curve_dragged)
        left_col.addWidget(self.chart_widget, 1)

        # Legend & Demo Simulator bar
        sim_frame = QFrame()
        sim_frame.setObjectName("CardFrame")
        sim_layout = QHBoxLayout(sim_frame)
        sim_layout.setContentsMargins(12, 8, 12, 8)

        self.show_cool_chk = QCheckBox("Show Cooling Curve")
        self.show_cool_chk.setChecked(True)
        self.show_cool_chk.toggled.connect(self._on_toggle_cooling_curve)
        sim_layout.addWidget(self.show_cool_chk)

        sim_layout.addSpacing(16)
        self.sim_label = QLabel("Demo Outdoor Temp Simulator:")
        sim_layout.addWidget(self.sim_label)
        self.sim_outdoor_slider = QSlider(Qt.Orientation.Horizontal)
        self.sim_outdoor_slider.setRange(-30, 105)
        self.sim_outdoor_slider.setValue(36)
        self.sim_outdoor_slider.valueChanged.connect(self._on_demo_outdoor_slider)
        sim_layout.addWidget(self.sim_outdoor_slider, 1)
        self.sim_outdoor_val_lbl = QLabel("36.5°F")
        sim_layout.addWidget(self.sim_outdoor_val_lbl)

        left_col.addWidget(sim_frame)
        layout.addLayout(left_col, 3)

        # Right column: Scrollable Hot Tank & Cold Tank Parameter Editor
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(4, 0, 4, 0)
        right_layout.setSpacing(12)

        # Hot Tank Group
        hot_group = QGroupBox("Hot Tank (Heating) & Warm Weather Shutdown")
        hot_form = QFormLayout(hot_group)
        hot_form.setSpacing(8)

        self.hot_or_chk = QCheckBox("Enable Hot Tank Outdoor Reset")
        self.hot_or_chk.toggled.connect(self._sync_spinboxes_to_chart)
        hot_form.addRow(self.hot_or_chk)

        self.hot_design_spin = self._make_temp_spin(-40, 127)
        self.hot_design_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        hot_form.addRow("Design Outdoor Temp (dot):", self.hot_design_spin)

        self.hot_min_spin = self._make_temp_spin(35, 180)
        self.hot_min_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        self.hot_min_label = QLabel("Hot Tank Min / Target Temp (mbt):")
        hot_form.addRow(self.hot_min_label, self.hot_min_spin)

        self.hot_max_spin = self._make_temp_spin(35, 180)
        self.hot_max_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        hot_form.addRow("Hot Tank Max Temp (dbt):", self.hot_max_spin)

        self.hot_diff_spin = self._make_delta_spin(2, 100)
        self.hot_diff_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        hot_form.addRow("Hot Tank Differential (htDif):", self.hot_diff_spin)

        self.wwsd_chk = QCheckBox("Enable Warm Weather Shutdown (WWSD)")
        self.wwsd_chk.toggled.connect(self._sync_spinboxes_to_chart)
        hot_form.addRow(self.wwsd_chk)

        self.wwsd_spin = self._make_temp_spin(34, 180)
        self.wwsd_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        hot_form.addRow("WWSD Threshold Temp (wwsd):", self.wwsd_spin)

        right_layout.addWidget(hot_group)

        # Cold Tank Group
        cold_group = QGroupBox("Cold Tank (Cooling) & Cold Weather Shutdown")
        cold_form = QFormLayout(cold_group)
        cold_form.setSpacing(8)

        self.cold_or_chk = QCheckBox("Enable Cold Tank Outdoor Reset")
        self.cold_or_chk.toggled.connect(self._sync_spinboxes_to_chart)
        cold_form.addRow(self.cold_or_chk)

        self.cold_design_spin = self._make_temp_spin(0, 119)
        self.cold_design_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        cold_form.addRow("Cold Design Outdoor Temp (cdot):", self.cold_design_spin)

        self.cold_min_spin = self._make_temp_spin(35, 180)
        self.cold_min_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        cold_form.addRow("Cold Tank Min / Target Temp (mst):", self.cold_min_spin)

        self.cold_max_spin = self._make_temp_spin(35, 180)
        self.cold_max_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        cold_form.addRow("Cold Tank Max Temp (dst):", self.cold_max_spin)

        self.cold_diff_spin = self._make_delta_spin(2, 100)
        self.cold_diff_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        cold_form.addRow("Cold Tank Differential (clDif):", self.cold_diff_spin)

        self.cwsd_chk = QCheckBox("Enable Cold Weather Shutdown (CWSD)")
        self.cwsd_chk.toggled.connect(self._sync_spinboxes_to_chart)
        cold_form.addRow(self.cwsd_chk)

        self.cwsd_spin = self._make_temp_spin(33, 119)
        self.cwsd_spin.valueChanged.connect(self._sync_spinboxes_to_chart)
        cold_form.addRow("CWSD Threshold Temp (cwsd):", self.cwsd_spin)

        right_layout.addWidget(cold_group)

        self.apply_curve_btn = QPushButton("Apply Tank & Outdoor Reset Curve Settings")
        self.apply_curve_btn.setObjectName("PrimaryButton")
        self.apply_curve_btn.clicked.connect(self._on_apply_tank_and_curve)
        right_layout.addWidget(self.apply_curve_btn)
        right_layout.addStretch()

        scroll.setWidget(right_container)
        layout.addWidget(scroll, 2)
        return tab

    def _build_staging_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        stg_group = QGroupBox("Heat Pump Staging Configuration")
        stg_form = QFormLayout(stg_group)
        stg_form.setSpacing(10)

        self.num_stages_spin = QSpinBox()
        self.num_stages_spin.setRange(1, 4)
        self.num_stages_spin.valueChanged.connect(self._on_num_stages_changed)
        stg_form.addRow("Number of Heat Pump Stages (1–4):", self.num_stages_spin)

        self.two_stage_chk = QCheckBox("Two-Stage Heat Pump (even stage counts only)")
        stg_form.addRow(self.two_stage_chk)

        self.stage_on_lag_spin = QSpinBox()
        self.stage_on_lag_spin.setRange(1, 240)
        self.stage_on_lag_spin.setSuffix(" min")
        stg_form.addRow("Stage ON Lag Time (1–240 min):", self.stage_on_lag_spin)

        self.stage_off_lag_spin = QSpinBox()
        self.stage_off_lag_spin.setRange(1, 240)
        self.stage_off_lag_spin.setSuffix(" sec")
        stg_form.addRow("Stage OFF Lag Time (1–240 sec):", self.stage_off_lag_spin)

        self.off_staging_chk = QCheckBox("Synchronized Stage Off (all stages turn off together)")
        stg_form.addRow(self.off_staging_chk)

        layout.addWidget(stg_group)

        rot_group = QGroupBox("Rotation, Delays & System Differential")
        rot_form = QFormLayout(rot_group)
        rot_form.setSpacing(10)

        self.rot_cycles_chk = QCheckBox("Enable Rotate by Cycles")
        rot_form.addRow(self.rot_cycles_chk)

        self.rot_cycles_spin = QSpinBox()
        self.rot_cycles_spin.setRange(1, 240)
        self.rot_cycles_spin.setSuffix(" cycles")
        rot_form.addRow("Rotate Cycles (1–240):", self.rot_cycles_spin)

        self.rot_time_chk = QCheckBox("Enable Rotate by Run Time")
        rot_form.addRow(self.rot_time_chk)

        self.rot_time_spin = QSpinBox()
        self.rot_time_spin.setRange(1, 240)
        self.rot_time_spin.setSuffix(" hrs")
        rot_form.addRow("Rotate Time (1–240 hrs):", self.rot_time_spin)

        self.ww_lag_spin = QSpinBox()
        self.ww_lag_spin.setRange(0, 240)
        self.ww_lag_spin.setSuffix(" hrs")
        rot_form.addRow("Weather Shutdown Lag Time (0–240 hrs):", self.ww_lag_spin)

        self.hc_delay_spin = QSpinBox()
        self.hc_delay_spin.setRange(30, 600)
        self.hc_delay_spin.setSuffix(" sec")
        rot_form.addRow("Heat/Cool Switch Delay (30–600 sec):", self.hc_delay_spin)

        self.wide_diff_chk = QCheckBox("Wide Priority Differential (dual-tank systems)")
        rot_form.addRow(self.wide_diff_chk)

        apply_stg_btn = QPushButton("Apply Staging & Rotation Settings")
        apply_stg_btn.setObjectName("PrimaryButton")
        apply_stg_btn.clicked.connect(self._on_apply_staging)
        rot_form.addRow(apply_stg_btn)

        layout.addWidget(rot_group)
        return tab

    def _build_backup_dhw_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        bk_group = QGroupBox("Backup Boiler Configuration")
        bk_form = QFormLayout(bk_group)
        bk_form.setSpacing(10)

        self.bk_lag_chk = QCheckBox("Enable Backup Lag Time")
        bk_form.addRow(self.bk_lag_chk)
        self.bk_lag_spin = QSpinBox()
        self.bk_lag_spin.setRange(1, 240)
        self.bk_lag_spin.setSuffix(" min")
        bk_form.addRow("Backup Lag Time (1–240 min):", self.bk_lag_spin)

        self.bk_temp_chk = QCheckBox("Enable Backup Outdoor Temperature Threshold")
        bk_form.addRow(self.bk_temp_chk)
        self.bk_temp_spin = self._make_temp_spin(2, 100)
        bk_form.addRow("Backup Outdoor Temp (bkTemp):", self.bk_temp_spin)

        self.bk_diff_chk = QCheckBox("Enable Instant Backup on Tank Temp Drop")
        bk_form.addRow(self.bk_diff_chk)
        self.bk_diff_spin = self._make_delta_spin(2, 100)
        bk_form.addRow("Backup Differential (bkDif):", self.bk_diff_spin)

        self.bk_od_only_chk = QCheckBox("Enable Backup-Only Below Outdoor Temp")
        bk_form.addRow(self.bk_od_only_chk)
        self.bk_od_only_spin = self._make_temp_spin(2, 100)
        bk_form.addRow("Backup-Only Outdoor Temp (bkOd):", self.bk_od_only_spin)

        self.bk_tk_only_chk = QCheckBox("Enable Backup-Only Above Tank Temp")
        bk_form.addRow(self.bk_tk_only_chk)
        self.bk_tk_only_spin = self._make_temp_spin(33, 200)
        bk_form.addRow("Backup-Only Tank Temp (bkTk):", self.bk_tk_only_spin)

        apply_bk_btn = QPushButton("Apply Backup Boiler Settings")
        apply_bk_btn.setObjectName("PrimaryButton")
        apply_bk_btn.clicked.connect(self._on_apply_backup)
        bk_form.addRow(apply_bk_btn)

        layout.addWidget(bk_group)

        dhw_group = QGroupBox("Domestic Hot Water (DHW) Channel")
        dhw_form = QFormLayout(dhw_group)
        dhw_form.setSpacing(10)

        self.dhw_enable_chk = QCheckBox("Enable DHW Demand Channel (dhwOn)")
        dhw_form.addRow(self.dhw_enable_chk)

        self.dhw_target_spin = self._make_temp_spin(33, 180)
        dhw_form.addRow("DHW Target Temperature (dhwT):", self.dhw_target_spin)

        self.dhw_diff_spin = self._make_delta_spin(2, 100)
        dhw_form.addRow("DHW Tank Differential (auxDif):", self.dhw_diff_spin)

        apply_dhw_btn = QPushButton("Apply DHW Settings")
        apply_dhw_btn.setObjectName("PrimaryButton")
        apply_dhw_btn.clicked.connect(self._on_apply_dhw)
        dhw_form.addRow(apply_dhw_btn)

        layout.addWidget(dhw_group)
        return tab

    def _make_temp_spin(self, min_f: float, max_f: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(-100.0, 300.0)
        spin.setProperty("min_f", min_f)
        spin.setProperty("max_f", max_f)
        self._configure_temp_spin_unit(spin)
        return spin

    def _make_delta_spin(self, min_df: float, max_df: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(0.5, 200.0)
        spin.setProperty("min_df", min_df)
        spin.setProperty("max_df", max_df)
        self._configure_delta_spin_unit(spin)
        return spin

    def _configure_temp_spin_unit(self, spin: QDoubleSpinBox) -> None:
        min_f = float(spin.property("min_f") or -40.0)
        max_f = float(spin.property("max_f") or 200.0)
        low = UnitHelper.f_to_display(min_f, self.unit)
        high = UnitHelper.f_to_display(max_f, self.unit)
        spin.setRange(low, high)
        spin.setSingleStep(0.5 if self.unit == "C" else 1.0)
        spin.setSuffix(" °C" if self.unit == "C" else " °F")

    def _configure_delta_spin_unit(self, spin: QDoubleSpinBox) -> None:
        min_df = float(spin.property("min_df") or 2.0)
        max_df = float(spin.property("max_df") or 100.0)
        low = UnitHelper.delta_f_to_display(min_df, self.unit)
        high = UnitHelper.delta_f_to_display(max_df, self.unit)
        spin.setRange(low, high)
        spin.setSingleStep(0.5 if self.unit == "C" else 1.0)
        spin.setSuffix(" Δ°C" if self.unit == "C" else " Δ°F")

    def set_unit(self, unit: str) -> None:
        if unit.upper() == self.unit:
            return
        self.unit = unit.upper()
        for spin in [
            self.hot_design_spin,
            self.hot_min_spin,
            self.hot_max_spin,
            self.wwsd_spin,
            self.cold_design_spin,
            self.cold_min_spin,
            self.cold_max_spin,
            self.cwsd_spin,
            self.bk_temp_spin,
            self.bk_od_only_spin,
            self.bk_tk_only_spin,
            self.dhw_target_spin,
        ]:
            self._configure_temp_spin_unit(spin)
        for dspin in [self.hot_diff_spin, self.cold_diff_spin, self.bk_diff_spin, self.dhw_diff_spin]:
            self._configure_delta_spin_unit(dspin)
        self.chart_widget.set_unit(self.unit)
        self.refresh_from_coordinator()

    def refresh_from_coordinator(self) -> None:
        if not self.coordinator.data or "devices" not in self.coordinator.data:
            return
        dev = self.coordinator.data["devices"].get(self.device_id)
        if not dev:
            return
        params = dev.get("parameters", {})

        self._updating_ui = True
        try:
            self.title_label.setText(f"{dev.get('name', self.device_id)}  (HBX ECO-0600)")
            self.subtitle_label.setText(
                f"Sync Code: {dev.get('syncCode', self.device_id)}  •  "
                f"Firmware: {params.get('firmware_version', '—')}  •  "
                f"Building: {dev.get('building_name', '—')}"
            )

            mode = str(params.get("hvac_mode", "auto")).lower()
            idx = self.priority_combo.findText(mode)
            if idx >= 0:
                self.priority_combo.setCurrentIndex(idx)

            self.perm_hd_chk.setChecked(bool(params.get("permanent_heat_demand", False)))
            self.perm_cd_chk.setChecked(bool(params.get("permanent_cool_demand", False)))

            # Telemetry cards
            is_local = bool(self.coordinator.is_local)
            lt = params.get("local_telemetry") or {}
            out_f = params.get("temperature_outdoor")
            sys_state = params.get("system_state") or {}

            if is_local:
                conn_txt = "ONLINE" if lt.get("connected") else "CONNECTING"
                self.tank_card_val.setText(f"{lt.get('priCPU', self.device_id)} ({conn_txt})")
                self.tank_card_sub.setText(
                    f"IP: {lt.get('host', '192.168.1.50')}:2000  |  SSID: {lt.get('SSID', '—')}\n"
                    f"RTC: {lt.get('rtc_str', '—')}"
                )
                self.outdoor_card_val.setText(UnitHelper.format_temp(out_f, self.unit, 1))
                self.outdoor_card_sub.setText(
                    f"Live Port 2000 Probe (out={lt.get('out', '—')}°F)  |  Frames: {lt.get('frames_received', 0)}"
                )
                rev_v = lt.get("revV")
                rev_mode = "Cooling (revV=1)" if rev_v else "Heating (revV=0)"
                self.dhw_card_val.setText(rev_mode)
                self.dhw_card_sub.setText(
                    f"Stages Configured (numStg): {lt.get('numStg', 1)}  |  FW: v{params.get('firmware_version', '—')}"
                )
                stg_s = lt.get("stgS")
                stg_str = "ON (CALLING)" if stg_s else ("OFF (IDLE)" if stg_s is not None else "—")
                bk_str = "FIRING (priBUp=1)" if lt.get("priBUp") else (
                    "Armed (useBkUp=1)" if lt.get("useBkUp") else "Disabled"
                )
                self.stages_card_val.setText(f"Stage 1: {stg_str}  •  Backup: {bk_str}")
                self.stages_card_sub.setText(
                    f"Raw Bits: stgS={lt.get('stgS', '—')}  |  useBkUp={lt.get('useBkUp', '—')}  |  priBUp={lt.get('priBUp', '—')}"
                )
                self.pumps_card_val.setText(f"secPmp Word: {lt.get('secPmp', '—')}")
                self.pumps_card_sub.setText(
                    f"Latest Frame: {lt.get('last_decrypted_text', 'Waiting for frame...')[:72]}"
                )
            else:
                tank_f = params.get("temperature_tank")
                tank_target_f = params.get("target_temperature_tank")
                self.tank_card_val.setText(UnitHelper.format_temp(tank_f, self.unit, 1))
                self.tank_card_sub.setText(
                    f"Target: {UnitHelper.format_temp(tank_target_f, self.unit, 1)}  |  "
                    f"Diff: {UnitHelper.format_delta(params.get('hot_tank_differential'), self.unit, 1)}"
                )

                self.outdoor_card_val.setText(UnitHelper.format_temp(out_f, self.unit, 1))
                wsd = sys_state.get("weatherShutdown") or {}
                wwsd_active = bool((wsd.get("wwsd") or {}).get("activated"))
                cwsd_active = bool((wsd.get("cwsd") or {}).get("activated"))
                if wwsd_active:
                    wsd_str = "WARM WEATHER SHUTDOWN (WWSD)"
                elif cwsd_active:
                    wsd_str = "COLD WEATHER SHUTDOWN (CWSD)"
                else:
                    wsd_str = "Active (No Weather Shutdown)"
                self.outdoor_card_sub.setText(wsd_str)

                dhw_f = params.get("temperature_dhw_tank")
                dhw_t_f = params.get("dhw_target_temp")
                dhw_state = params.get("dhw_state") or {}
                dhw_status = "Heating" if dhw_state.get("activated") else ("Idle" if params.get("dhw_enabled") else "Disabled")
                self.dhw_card_val.setText(UnitHelper.format_temp(dhw_f, self.unit, 1))
                self.dhw_card_sub.setText(
                    f"Target: {UnitHelper.format_temp(dhw_t_f, self.unit, 1)}  |  {dhw_status}"
                )

                stages = params.get("heatpump_stages") or []
                stg_lines = []
                run_lines = []
                for stg in stages:
                    st_name = stg.get("title", "Stage")
                    st_act = "ON" if stg.get("activated") else "Idle"
                    stg_lines.append(f"{st_name}: {st_act}")
                    run_lines.append(f"{st_name}: {stg.get('runTime', '0:00')}h")
                bk = params.get("backup_state") or {}
                if bk:
                    bk_act = "FIRING" if bk.get("activated") else "Standby"
                    stg_lines.append(f"Backup: {bk_act}")
                    run_lines.append(f"Backup: {bk.get('runTime', '0:00')}h")
                self.stages_card_val.setText("  •  ".join(stg_lines) if stg_lines else "—")
                self.stages_card_sub.setText("  |  ".join(run_lines) if run_lines else "—")

                pumps = sys_state.get("pumps") or []
                pump_strs = [f"{p.get('title', 'Pump')}: {'ON' if p.get('activated') else 'OFF'} ({p.get('mode', '—')})" for p in pumps]
                rv = sys_state.get("reversingValve")
                if rv:
                    pump_strs.append(f"Rev Valve: {'ON' if rv.get('activated') else 'OFF'}")
                demands = sys_state.get("demands") or []
                dmd_strs = [f"{d.get('title', d.get('name'))}: {'CALLING' if d.get('activated') else 'Idle'}" for d in demands]
                self.pumps_card_val.setText("  •  ".join(pump_strs) if pump_strs else "—")
                self.pumps_card_sub.setText("  |  ".join(dmd_strs) if dmd_strs else "—")

            # Outdoor Reset Curve & Tank spinboxes
            curve = OutdoorResetCurveConfig.from_eco_parameters(params)
            self.chart_widget.set_config(curve, self.unit)

            self.hot_or_chk.setChecked(curve.hot_reset_enabled)
            self.hot_design_spin.setEnabled(curve.hot_reset_enabled)
            self.hot_max_spin.setEnabled(curve.hot_reset_enabled)
            self.hot_min_label.setText(
                "Hot Tank Min Temp (mbt):" if curve.hot_reset_enabled else "Hot Tank Target Temp (mbt):"
            )
            self.hot_design_spin.setValue(UnitHelper.f_to_display(curve.hot_design_outdoor_f, self.unit))
            self.hot_min_spin.setValue(UnitHelper.f_to_display(curve.hot_min_tank_f, self.unit))
            self.hot_max_spin.setValue(UnitHelper.f_to_display(curve.hot_max_tank_f, self.unit))
            self.hot_diff_spin.setValue(UnitHelper.delta_f_to_display(curve.hot_differential_f, self.unit))
            self.wwsd_chk.setChecked(curve.hot_wwsd_enabled)
            self.wwsd_spin.setEnabled(curve.hot_wwsd_enabled)
            self.wwsd_spin.setValue(UnitHelper.f_to_display(curve.hot_wwsd_f, self.unit))

            self.cold_or_chk.setChecked(curve.cold_reset_enabled)
            self.cold_design_spin.setEnabled(curve.cold_reset_enabled)
            self.cold_max_spin.setEnabled(curve.cold_reset_enabled)
            self.cold_design_spin.setValue(UnitHelper.f_to_display(curve.cold_design_outdoor_f, self.unit))
            self.cold_min_spin.setValue(UnitHelper.f_to_display(curve.cold_min_tank_f, self.unit))
            self.cold_max_spin.setValue(UnitHelper.f_to_display(curve.cold_max_tank_f, self.unit))
            self.cold_diff_spin.setValue(UnitHelper.delta_f_to_display(curve.cold_differential_f, self.unit))
            self.cwsd_chk.setChecked(curve.cold_cwsd_enabled)
            self.cwsd_spin.setEnabled(curve.cold_cwsd_enabled)
            self.cwsd_spin.setValue(UnitHelper.f_to_display(curve.cold_cwsd_f, self.unit))

            # Demo outdoor simulator visibility
            is_demo = bool(self.coordinator.is_demo)
            self.sim_label.setVisible(is_demo)
            self.sim_outdoor_slider.setVisible(is_demo)
            self.sim_outdoor_val_lbl.setVisible(is_demo)
            if is_demo and out_f is not None:
                self.sim_outdoor_slider.setValue(int(round(out_f)))
                self.sim_outdoor_val_lbl.setText(UnitHelper.format_temp(out_f, self.unit, 1))

            # Staging & Rotation tab
            num_stg = int(params.get("number_of_stages") or 2)
            self.num_stages_spin.setValue(num_stg)
            self.two_stage_chk.setEnabled(num_stg % 2 == 0)
            self.two_stage_chk.setChecked(bool(params.get("two_stage_heat_pump", False)))
            self.stage_on_lag_spin.setValue(int(params.get("stage_on_lag_time") or 10))
            self.stage_off_lag_spin.setValue(int(params.get("stage_off_lag_time") or 15))
            self.off_staging_chk.setChecked(bool(params.get("off_staging", False)))

            rot_cy = params.get("rotate_cycles")
            self.rot_cycles_chk.setChecked(rot_cy != "off" and rot_cy is not None)
            if isinstance(rot_cy, int):
                self.rot_cycles_spin.setValue(rot_cy)

            rot_ti = params.get("rotate_time")
            self.rot_time_chk.setChecked(rot_ti != "off" and rot_ti is not None)
            if isinstance(rot_ti, int):
                self.rot_time_spin.setValue(rot_ti)

            self.ww_lag_spin.setValue(int(params.get("weather_shutdown_lag_time") or 0))
            self.hc_delay_spin.setValue(int(params.get("heat_cool_switch_delay") or 60))
            self.wide_diff_chk.setChecked(bool(params.get("wide_priority_differential", False)))

            # Backup & DHW tab
            bk_lag = params.get("backup_lag_time")
            self.bk_lag_chk.setChecked(bk_lag != "off" and bk_lag is not None)
            if isinstance(bk_lag, int):
                self.bk_lag_spin.setValue(bk_lag)

            bk_t = params.get("backup_temp")
            self.bk_temp_chk.setChecked(bk_t != "off" and bk_t is not None)
            self.bk_temp_spin.setValue(UnitHelper.f_to_display(_scalar_f(bk_t, 25.0), self.unit))

            bk_d = params.get("backup_differential")
            self.bk_diff_chk.setChecked(bk_d != "off" and bk_d is not None)
            self.bk_diff_spin.setValue(UnitHelper.delta_f_to_display(_scalar_f(bk_d, 10.0), self.unit))

            bk_od = params.get("backup_only_outdoor_temp")
            self.bk_od_only_chk.setChecked(bk_od != "off" and bk_od is not None)
            self.bk_od_only_spin.setValue(UnitHelper.f_to_display(_scalar_f(bk_od, 10.0), self.unit))

            bk_tk = params.get("backup_only_tank_temp")
            self.bk_tk_only_chk.setChecked(bk_tk != "off" and bk_tk is not None)
            self.bk_tk_only_spin.setValue(UnitHelper.f_to_display(_scalar_f(bk_tk, 120.0), self.unit))

            self.dhw_enable_chk.setChecked(bool(params.get("dhw_enabled", False)))
            self.dhw_target_spin.setValue(
                UnitHelper.f_to_display(_scalar_f(params.get("dhw_target_temp"), 120.0), self.unit)
            )
            self.dhw_diff_spin.setValue(
                UnitHelper.delta_f_to_display(_scalar_f(params.get("dhw_differential"), 5.0), self.unit)
            )
        finally:
            self._updating_ui = False

    def _on_chart_curve_dragged(self, c: OutdoorResetCurveConfig) -> None:
        """Update spinboxes when user drags handles on the Outdoor Reset Chart."""
        self._updating_ui = True
        try:
            self.hot_design_spin.setValue(UnitHelper.f_to_display(c.hot_design_outdoor_f, self.unit))
            self.hot_min_spin.setValue(UnitHelper.f_to_display(c.hot_min_tank_f, self.unit))
            self.hot_max_spin.setValue(UnitHelper.f_to_display(c.hot_max_tank_f, self.unit))
            self.wwsd_spin.setValue(UnitHelper.f_to_display(c.hot_wwsd_f, self.unit))
            self.cold_design_spin.setValue(UnitHelper.f_to_display(c.cold_design_outdoor_f, self.unit))
            self.cold_min_spin.setValue(UnitHelper.f_to_display(c.cold_min_tank_f, self.unit))
            self.cold_max_spin.setValue(UnitHelper.f_to_display(c.cold_max_tank_f, self.unit))
            self.cwsd_spin.setValue(UnitHelper.f_to_display(c.cold_cwsd_f, self.unit))
        finally:
            self._updating_ui = False

    def _sync_spinboxes_to_chart(self) -> None:
        if self._updating_ui:
            return
        c = self.chart_widget.config
        c.hot_reset_enabled = self.hot_or_chk.isChecked()
        c.hot_design_outdoor_f = UnitHelper.display_to_f(self.hot_design_spin.value(), self.unit)
        c.hot_min_tank_f = UnitHelper.display_to_f(self.hot_min_spin.value(), self.unit)
        c.hot_max_tank_f = (
            UnitHelper.display_to_f(self.hot_max_spin.value(), self.unit)
            if c.hot_reset_enabled
            else c.hot_min_tank_f
        )
        c.hot_differential_f = UnitHelper.display_to_delta_f(self.hot_diff_spin.value(), self.unit)
        c.hot_wwsd_enabled = self.wwsd_chk.isChecked()
        c.hot_wwsd_f = UnitHelper.display_to_f(self.wwsd_spin.value(), self.unit)

        c.cold_reset_enabled = self.cold_or_chk.isChecked()
        c.cold_design_outdoor_f = UnitHelper.display_to_f(self.cold_design_spin.value(), self.unit)
        c.cold_min_tank_f = UnitHelper.display_to_f(self.cold_min_spin.value(), self.unit)
        c.cold_max_tank_f = (
            UnitHelper.display_to_f(self.cold_max_spin.value(), self.unit)
            if c.cold_reset_enabled
            else c.cold_min_tank_f
        )
        c.cold_differential_f = UnitHelper.display_to_delta_f(self.cold_diff_spin.value(), self.unit)
        c.cold_cwsd_enabled = self.cwsd_chk.isChecked()
        c.cold_cwsd_f = UnitHelper.display_to_f(self.cwsd_spin.value(), self.unit)

        self.hot_design_spin.setEnabled(c.hot_reset_enabled)
        self.hot_max_spin.setEnabled(c.hot_reset_enabled)
        self.hot_min_label.setText(
            "Hot Tank Min Temp (mbt):" if c.hot_reset_enabled else "Hot Tank Target Temp (mbt):"
        )
        self.wwsd_spin.setEnabled(c.hot_wwsd_enabled)
        self.cold_design_spin.setEnabled(c.cold_reset_enabled)
        self.cold_max_spin.setEnabled(c.cold_reset_enabled)
        self.cwsd_spin.setEnabled(c.cold_cwsd_enabled)
        self.chart_widget.update()

    def _on_toggle_cooling_curve(self, checked: bool) -> None:
        self.chart_widget.show_cooling_curve = checked
        self.chart_widget.update()

    def _on_demo_outdoor_slider(self, val_f: int) -> None:
        if self._updating_ui:
            return
        if isinstance(self.coordinator.sensorlinx, DemoSensorlinxClient):
            self.coordinator.sensorlinx.set_simulated_outdoor_temp(float(val_f))
            self.sim_outdoor_val_lbl.setText(UnitHelper.format_temp(val_f, self.unit, 1))
            asyncio.ensure_future(self.coordinator.async_refresh())

    def _on_num_stages_changed(self, val: int) -> None:
        self.two_stage_chk.setEnabled(val % 2 == 0)

    def _on_priority_changed(self, mode: str) -> None:
        if self._updating_ui or not mode:
            return
        asyncio.ensure_future(self._async_set_priority(mode))

    async def _async_set_priority(self, mode: str) -> None:
        helper = self.coordinator.get_device_helper(self.device_id)
        if not helper:
            return
        try:
            await helper.set_hvac_mode_priority(mode)
            self.coordinator.set_parameter_override(self.device_id, {"hvac_mode": mode})
            await self.coordinator.async_refresh()
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to set HVAC mode priority: {exc}")

    def _on_perm_hd_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        asyncio.ensure_future(self._async_set_perm_hd(checked))

    async def _async_set_perm_hd(self, checked: bool) -> None:
        helper = self.coordinator.get_device_helper(self.device_id)
        if not helper:
            return
        try:
            await helper.set_permanent_hd(checked)
            self.coordinator.set_parameter_override(self.device_id, {"permanent_heat_demand": checked})
            await self.coordinator.async_refresh()
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to set Permanent Heat Demand: {exc}")

    def _on_perm_cd_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        asyncio.ensure_future(self._async_set_perm_cd(checked))

    async def _async_set_perm_cd(self, checked: bool) -> None:
        helper = self.coordinator.get_device_helper(self.device_id)
        if not helper:
            return
        try:
            await helper.set_permanent_cd(checked)
            self.coordinator.set_parameter_override(self.device_id, {"permanent_cool_demand": checked})
            await self.coordinator.async_refresh()
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to set Permanent Cool Demand: {exc}")

    def _on_apply_tank_and_curve(self) -> None:
        asyncio.ensure_future(self._async_apply_tank_and_curve())

    async def _async_apply_tank_and_curve(self) -> None:
        helper = self.coordinator.get_device_helper(self.device_id)
        if not helper:
            return
        try:
            hot_min_f = round(UnitHelper.display_to_f(self.hot_min_spin.value(), self.unit))
            hot_max_f = (
                round(UnitHelper.display_to_f(self.hot_max_spin.value(), self.unit))
                if self.hot_or_chk.isChecked()
                else hot_min_f
            )
            hot_or = (
                Temperature(round(UnitHelper.display_to_f(self.hot_design_spin.value(), self.unit)), "F")
                if self.hot_or_chk.isChecked()
                else "off"
            )
            hot_diff = TemperatureDelta(
                max(2, round(UnitHelper.display_to_delta_f(self.hot_diff_spin.value(), self.unit))), "F"
            )
            wwsd = (
                Temperature(round(UnitHelper.display_to_f(self.wwsd_spin.value(), self.unit)), "F")
                if self.wwsd_chk.isChecked()
                else "off"
            )

            cold_min_f = round(UnitHelper.display_to_f(self.cold_min_spin.value(), self.unit))
            cold_max_f = (
                round(UnitHelper.display_to_f(self.cold_max_spin.value(), self.unit))
                if self.cold_or_chk.isChecked()
                else cold_min_f
            )
            cold_or = (
                Temperature(round(UnitHelper.display_to_f(self.cold_design_spin.value(), self.unit)), "F")
                if self.cold_or_chk.isChecked()
                else "off"
            )
            cold_diff = TemperatureDelta(
                max(2, round(UnitHelper.display_to_delta_f(self.cold_diff_spin.value(), self.unit))), "F"
            )
            cwsd = (
                Temperature(round(UnitHelper.display_to_f(self.cwsd_spin.value(), self.unit)), "F")
                if self.cwsd_chk.isChecked()
                else "off"
            )

            await self.coordinator.sensorlinx.set_device_parameter(
                helper.building_id,
                helper.device_id,
                hot_tank_outdoor_reset=hot_or,
                hot_tank_min_temp=Temperature(hot_min_f, "F"),
                hot_tank_max_temp=Temperature(hot_max_f, "F"),
                hot_tank_differential=hot_diff,
                warm_weather_shutdown=wwsd,
                cold_tank_outdoor_reset=cold_or,
                cold_tank_min_temp=Temperature(cold_min_f, "F"),
                cold_tank_max_temp=Temperature(cold_max_f, "F"),
                cold_tank_differential=cold_diff,
                cold_weather_shutdown=cwsd,
            )
            self.coordinator.set_parameter_override(
                self.device_id,
                {
                    "hot_tank_outdoor_reset": hot_or,
                    "hot_tank_min_temp": Temperature(hot_min_f, "F"),
                    "hot_tank_max_temp": Temperature(hot_max_f, "F"),
                    "hot_tank_differential": hot_diff,
                    "warm_weather_shutdown": wwsd,
                    "cold_tank_outdoor_reset": cold_or,
                    "cold_tank_min_temp": Temperature(cold_min_f, "F"),
                    "cold_tank_max_temp": Temperature(cold_max_f, "F"),
                    "cold_tank_differential": cold_diff,
                    "cold_weather_shutdown": cwsd,
                },
            )
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit("Saved Tank & Outdoor Reset Curve parameters.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to save tank/curve settings: {exc}")

    def _on_apply_staging(self) -> None:
        asyncio.ensure_future(self._async_apply_staging())

    async def _async_apply_staging(self) -> None:
        helper = self.coordinator.get_device_helper(self.device_id)
        if not helper:
            return
        try:
            num_stg = self.num_stages_spin.value()
            two_s = self.two_stage_chk.isChecked() if (num_stg % 2 == 0) else False
            on_lag = self.stage_on_lag_spin.value()
            off_lag = self.stage_off_lag_spin.value()
            off_stg = self.off_staging_chk.isChecked()
            rot_cy = self.rot_cycles_spin.value() if self.rot_cycles_chk.isChecked() else "off"
            rot_ti = self.rot_time_spin.value() if self.rot_time_chk.isChecked() else "off"
            ww_lag = self.ww_lag_spin.value()
            hc_delay = self.hc_delay_spin.value()
            wide_dif = self.wide_diff_chk.isChecked()

            await self.coordinator.sensorlinx.set_device_parameter(
                helper.building_id,
                helper.device_id,
                number_of_stages=num_stg,
                two_stage_heat_pump=two_s,
                stage_on_lag_time=on_lag,
                stage_off_lag_time=off_lag,
                off_staging=off_stg,
                rotate_cycles=rot_cy,
                rotate_time=rot_ti,
                weather_shutdown_lag_time=ww_lag,
                heat_cool_switch_delay=hc_delay,
                wide_priority_differential=wide_dif,
            )
            self.coordinator.set_parameter_override(
                self.device_id,
                {
                    "number_of_stages": num_stg,
                    "two_stage_heat_pump": two_s,
                    "stage_on_lag_time": on_lag,
                    "stage_off_lag_time": off_lag,
                    "off_staging": off_stg,
                    "rotate_cycles": rot_cy,
                    "rotate_time": rot_ti,
                    "weather_shutdown_lag_time": ww_lag,
                    "heat_cool_switch_delay": hc_delay,
                    "wide_priority_differential": wide_dif,
                },
            )
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit("Saved Heat Pump Staging & Rotation settings.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to save staging settings: {exc}")

    def _on_apply_backup(self) -> None:
        asyncio.ensure_future(self._async_apply_backup())

    async def _async_apply_backup(self) -> None:
        helper = self.coordinator.get_device_helper(self.device_id)
        if not helper:
            return
        try:
            bk_lag = self.bk_lag_spin.value() if self.bk_lag_chk.isChecked() else "off"
            bk_temp = (
                Temperature(round(UnitHelper.display_to_f(self.bk_temp_spin.value(), self.unit)), "F")
                if self.bk_temp_chk.isChecked()
                else "off"
            )
            bk_diff = (
                TemperatureDelta(
                    max(2, round(UnitHelper.display_to_delta_f(self.bk_diff_spin.value(), self.unit))), "F"
                )
                if self.bk_diff_chk.isChecked()
                else "off"
            )
            bk_od = (
                Temperature(round(UnitHelper.display_to_f(self.bk_od_only_spin.value(), self.unit)), "F")
                if self.bk_od_only_chk.isChecked()
                else "off"
            )
            bk_tk = (
                Temperature(round(UnitHelper.display_to_f(self.bk_tk_only_spin.value(), self.unit)), "F")
                if self.bk_tk_only_chk.isChecked()
                else "off"
            )

            await self.coordinator.sensorlinx.set_device_parameter(
                helper.building_id,
                helper.device_id,
                backup_lag_time=bk_lag,
                backup_temp=bk_temp,
                backup_differential=bk_diff,
                backup_only_outdoor_temp=bk_od,
                backup_only_tank_temp=bk_tk,
            )
            self.coordinator.set_parameter_override(
                self.device_id,
                {
                    "backup_lag_time": bk_lag,
                    "backup_temp": bk_temp,
                    "backup_differential": bk_diff,
                    "backup_only_outdoor_temp": bk_od,
                    "backup_only_tank_temp": bk_tk,
                },
            )
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit("Saved Backup Boiler settings.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to save backup settings: {exc}")

    def _on_apply_dhw(self) -> None:
        asyncio.ensure_future(self._async_apply_dhw())

    async def _async_apply_dhw(self) -> None:
        helper = self.coordinator.get_device_helper(self.device_id)
        if not helper:
            return
        try:
            dhw_on = self.dhw_enable_chk.isChecked()
            dhw_target = Temperature(
                round(UnitHelper.display_to_f(self.dhw_target_spin.value(), self.unit)), "F"
            )
            dhw_diff = TemperatureDelta(
                max(2, round(UnitHelper.display_to_delta_f(self.dhw_diff_spin.value(), self.unit))), "F"
            )
            await self.coordinator.sensorlinx.set_device_parameter(
                helper.building_id,
                helper.device_id,
                dhw_enabled=dhw_on,
                dhw_target_temp=dhw_target,
                dhw_differential=dhw_diff,
            )
            self.coordinator.set_parameter_override(
                self.device_id,
                {
                    "dhw_enabled": dhw_on,
                    "dhw_target_temp": dhw_target,
                    "dhw_differential": dhw_diff,
                },
            )
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit("Saved Domestic Hot Water (DHW) settings.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to save DHW settings: {exc}")

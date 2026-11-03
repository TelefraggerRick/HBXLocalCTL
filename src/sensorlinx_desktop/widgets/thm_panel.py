"""THM-0600 Thermostat monitoring and control panel."""
from __future__ import annotations

import asyncio
from typing import Optional

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
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from pysensorlinx import Temperature, ThmDevice

from ..coordinator import SensorlinxCoordinator
from ..demo_client import DemoSensorlinxClient
from ..models import UnitHelper


class ThmDevicePanel(QWidget):
    """Full thermostat control and schedule/humidity view for an HBX THM-0600 device."""

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
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Header
        hdr = QFrame()
        hdr.setObjectName("CardFrame")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 12, 16, 12)

        title_col = QVBoxLayout()
        self.title_lbl = QLabel("THM-0600 Thermostat")
        self.title_lbl.setObjectName("SectionHeader")
        self.subtitle_lbl = QLabel("Sync Code: — | Zone: —")
        self.subtitle_lbl.setObjectName("MutedText")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.subtitle_lbl)
        hdr_lay.addLayout(title_col)
        hdr_lay.addStretch()

        # Quick Mode & Away selectors in header
        hdr_lay.addWidget(QLabel("HVAC Mode:"))
        self.hvac_mode_combo = QComboBox()
        self.hvac_mode_combo.addItems(["auto", "heat", "cool", "off"])
        self.hvac_mode_combo.currentTextChanged.connect(self._on_hvac_mode_changed)
        hdr_lay.addWidget(self.hvac_mode_combo)

        hdr_lay.addSpacing(12)
        hdr_lay.addWidget(QLabel("Fan Mode:"))
        self.fan_mode_combo = QComboBox()
        self.fan_mode_combo.addItems(["off", "on", "intermittent"])
        self.fan_mode_combo.currentTextChanged.connect(self._on_fan_mode_changed)
        hdr_lay.addWidget(self.fan_mode_combo)

        hdr_lay.addSpacing(12)
        self.away_chk = QCheckBox("Away Mode Active")
        self.away_chk.toggled.connect(self._on_away_toggled)
        hdr_lay.addWidget(self.away_chk)

        root.addWidget(hdr)

        # Telemetry Strip
        cards = QGridLayout()
        cards.setSpacing(10)

        self.room_val = QLabel("—")
        self.room_val.setObjectName("HeroMetric")
        self.room_sub = QLabel("Sensor Mode: —")
        self.room_sub.setObjectName("MutedText")
        cards.addWidget(self._make_card("Room Temperature", self.room_val, self.room_sub), 0, 0)

        self.floor_val = QLabel("—")
        self.floor_val.setObjectName("HeroMetric")
        self.floor_sub = QLabel("Radiant / Slab Sensor")
        self.floor_sub.setObjectName("MutedText")
        cards.addWidget(self._make_card("Floor Temperature", self.floor_val, self.floor_sub), 0, 1)

        self.hum_val = QLabel("—")
        self.hum_val.setObjectName("HeroMetric")
        self.hum_sub = QLabel("Target: —")
        self.hum_sub.setObjectName("MutedText")
        cards.addWidget(self._make_card("Relative Humidity", self.hum_val, self.hum_sub), 0, 2)

        self.action_val = QLabel("—")
        self.action_val.setObjectName("StatusText")
        self.action_sub = QLabel("Active Setpoint: —")
        self.action_sub.setObjectName("MutedText")
        cards.addWidget(self._make_card("Active Demand & State", self.action_val, self.action_sub), 0, 3)

        root.addLayout(cards)

        # Demo Room Temperature Simulator
        self.sim_frame = QFrame()
        self.sim_frame.setObjectName("CardFrame")
        sim_lay = QHBoxLayout(self.sim_frame)
        sim_lay.setContentsMargins(14, 8, 14, 8)
        sim_lay.addWidget(QLabel("Demo Room Temp Simulator:"))
        self.sim_room_slider = QSlider(Qt.Orientation.Horizontal)
        self.sim_room_slider.setRange(45, 90)
        self.sim_room_slider.setValue(68)
        self.sim_room_slider.valueChanged.connect(self._on_demo_room_slider)
        sim_lay.addWidget(self.sim_room_slider, 1)
        self.sim_room_lbl = QLabel("68.0°F")
        sim_lay.addWidget(self.sim_room_lbl)
        root.addWidget(self.sim_frame)

        # Main Controls Row: Home Setpoints | Away Setpoints | Humidity & Schedule
        mid_row = QHBoxLayout()
        mid_row.setSpacing(14)

        # 1. Home Setpoints
        home_grp = QGroupBox("Home Setpoints (rmT / rmCT)")
        home_form = QFormLayout(home_grp)
        home_form.setSpacing(10)

        self.heat_sp_spin = self._make_setpoint_spin()
        home_form.addRow("Heat Setpoint (rmT):", self.heat_sp_spin)

        self.cool_sp_spin = self._make_setpoint_spin()
        home_form.addRow("Cool Setpoint (rmCT):", self.cool_sp_spin)

        apply_home_btn = QPushButton("Apply Home Setpoints")
        apply_home_btn.setObjectName("PrimaryButton")
        apply_home_btn.clicked.connect(self._on_apply_home_setpoints)
        home_form.addRow(apply_home_btn)
        mid_row.addWidget(home_grp, 1)

        # 2. Away Setpoints
        away_grp = QGroupBox("Away Mode Setpoints (hRmT / hRmCT)")
        away_form = QFormLayout(away_grp)
        away_form.setSpacing(10)

        self.away_heat_spin = self._make_setpoint_spin()
        away_form.addRow("Away Heat Setpoint (hRmT):", self.away_heat_spin)

        self.away_cool_spin = self._make_setpoint_spin()
        away_form.addRow("Away Cool Setpoint (hRmCT):", self.away_cool_spin)

        apply_away_btn = QPushButton("Apply Away Setpoints")
        apply_away_btn.setObjectName("PrimaryButton")
        apply_away_btn.clicked.connect(self._on_apply_away_setpoints)
        away_form.addRow(apply_away_btn)
        mid_row.addWidget(away_grp, 1)

        # 3. Humidity & Program Schedule Enable
        hum_grp = QGroupBox("Humidity Control & On-Device Schedule")
        hum_form = QFormLayout(hum_grp)
        hum_form.setSpacing(10)

        self.sched_chk = QCheckBox("Enable On-Device Schedule (pgmble)")
        self.sched_chk.toggled.connect(self._on_schedule_toggled)
        hum_form.addRow(self.sched_chk)

        self.hum_mode_combo = QComboBox()
        self.hum_mode_combo.addItems(["off", "on", "auto"])
        hum_form.addRow("Humidity Control Mode (useHum):", self.hum_mode_combo)

        self.hum_target_spin = QSpinBox()
        self.hum_target_spin.setRange(0, 100)
        self.hum_target_spin.setSuffix(" %")
        hum_form.addRow("Humidity Target (hmT):", self.hum_target_spin)

        apply_hum_btn = QPushButton("Apply Humidity Settings")
        apply_hum_btn.setObjectName("PrimaryButton")
        apply_hum_btn.clicked.connect(self._on_apply_humidity)
        hum_form.addRow(apply_hum_btn)
        mid_row.addWidget(hum_grp, 1)

        root.addLayout(mid_row)

        # Schedule Table
        sched_grp = QGroupBox("Thermostat Program Schedule (Weekday & Weekend Periods)")
        sched_lay = QVBoxLayout(sched_grp)
        self.sched_table = QTableWidget(0, 5)
        self.sched_table.setHorizontalHeaderLabels(["Day Group", "Period", "Start Time", "Heat Target", "Cool Target"])
        self.sched_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sched_table.verticalHeader().setVisible(False)
        self.sched_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sched_table.setAlternatingRowColors(True)
        sched_lay.addWidget(self.sched_table)
        root.addWidget(sched_grp, 1)

    def _make_card(self, title: str, val_lbl: QLabel, sub_lbl: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CardFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)
        hdr = QLabel(title.upper())
        hdr.setObjectName("CardTitle")
        lay.addWidget(hdr)
        lay.addWidget(val_lbl)
        lay.addWidget(sub_lbl)
        return frame

    def _make_setpoint_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        self._configure_setpoint_spin(spin)
        return spin

    def _configure_setpoint_spin(self, spin: QDoubleSpinBox) -> None:
        low = UnitHelper.f_to_display(35.0, self.unit)
        high = UnitHelper.f_to_display(99.0, self.unit)
        spin.setRange(low, high)
        spin.setSingleStep(0.5 if self.unit == "C" else 1.0)
        spin.setSuffix(" °C" if self.unit == "C" else " °F")

    def set_unit(self, unit: str) -> None:
        if unit.upper() == self.unit:
            return
        self.unit = unit.upper()
        for spin in [self.heat_sp_spin, self.cool_sp_spin, self.away_heat_spin, self.away_cool_spin]:
            self._configure_setpoint_spin(spin)
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
            zone_num = dev.get("zone_number")
            parent_zon = dev.get("parent_zone_name")
            zone_tag = f"Zone {zone_num} via {parent_zon}" if zone_num and parent_zon else "Standalone THM"
            self.title_lbl.setText(f"{dev.get('name', self.device_id)}  (HBX THM-0600)")
            self.subtitle_lbl.setText(
                f"Sync Code: {dev.get('syncCode', self.device_id)}  •  "
                f"Firmware: {params.get('firmware_version', '—')}  •  {zone_tag}"
            )

            mode = str(params.get("hvac_mode") or "auto").lower()
            m_idx = self.hvac_mode_combo.findText(mode)
            if m_idx >= 0:
                self.hvac_mode_combo.setCurrentIndex(m_idx)

            fan = str(params.get("fan_mode") or "off").lower()
            f_idx = self.fan_mode_combo.findText(fan)
            if f_idx >= 0:
                self.fan_mode_combo.setCurrentIndex(f_idx)

            away_on = bool(params.get("away_mode_activated", False))
            self.away_chk.setChecked(away_on)

            room_f = params.get("temperature_room")
            floor_f = params.get("temperature_floor")
            hum = params.get("humidity")
            self.room_val.setText(UnitHelper.format_temp(room_f, self.unit, 1))
            self.room_sub.setText(f"Sensor Mode: {params.get('thm_mode') or 'Air'}")

            self.floor_val.setText(UnitHelper.format_temp(floor_f, self.unit, 1))
            self.hum_val.setText(f"{hum:.1f}%" if isinstance(hum, (int, float)) else "—")
            self.hum_sub.setText(
                f"Mode: {str(params.get('humidity_mode', 'off')).upper()}  |  Target: {params.get('humidity_target', '—')}%"
            )

            active_demands = params.get("active_demands") or []
            if mode == "off" or params.get("is_off"):
                state_str = "OFF"
            elif active_demands:
                state_str = " + ".join(d.upper() for d in active_demands)
            else:
                state_str = "IDLE (Satisfied)"
            self.action_val.setText(state_str)
            preset_str = "AWAY PRESET" if away_on else "HOME"
            self.action_sub.setText(
                f"Preset: {preset_str}  |  Display Target: {UnitHelper.format_temp(params.get('target_temperature_room'), self.unit, 0)}"
            )

            # Demo slider
            is_demo = bool(self.coordinator.is_demo)
            self.sim_frame.setVisible(is_demo)
            if is_demo and room_f is not None:
                self.sim_room_slider.setValue(int(round(room_f)))
                self.sim_room_lbl.setText(UnitHelper.format_temp(room_f, self.unit, 1))

            # Setpoints
            heat_sp = params.get("heat_setpoint", 68.0)
            cool_sp = params.get("cool_setpoint", 75.0)
            self.heat_sp_spin.setValue(UnitHelper.f_to_display(heat_sp, self.unit))
            self.cool_sp_spin.setValue(UnitHelper.f_to_display(cool_sp, self.unit))

            away_h = params.get("away_heat_setpoint", 60.0)
            away_c = params.get("away_cool_setpoint", 80.0)
            self.away_heat_spin.setValue(UnitHelper.f_to_display(away_h, self.unit))
            self.away_cool_spin.setValue(UnitHelper.f_to_display(away_c, self.unit))

            self.sched_chk.setChecked(bool(params.get("schedule_enabled", False)))
            hm_mode = str(params.get("humidity_mode") or "off").lower()
            hm_idx = self.hum_mode_combo.findText(hm_mode)
            if hm_idx >= 0:
                self.hum_mode_combo.setCurrentIndex(hm_idx)
            if params.get("humidity_target") is not None:
                self.hum_target_spin.setValue(int(params["humidity_target"]))

            # Schedule table
            schedules = params.get("schedules") or []
            self.sched_table.setRowCount(len(schedules))
            for row, item in enumerate(schedules):
                self.sched_table.setItem(row, 0, QTableWidgetItem(str(item.get("type", "—"))))
                self.sched_table.setItem(row, 1, QTableWidgetItem(str(item.get("title", "—"))))
                self.sched_table.setItem(row, 2, QTableWidgetItem(str(item.get("timeFormatted", "—"))))
                self.sched_table.setItem(row, 3, QTableWidgetItem(UnitHelper.format_temp(item.get("heat"), self.unit, 0)))
                self.sched_table.setItem(row, 4, QTableWidgetItem(UnitHelper.format_temp(item.get("cool"), self.unit, 0)))
        finally:
            self._updating_ui = False

    def _get_thm_helper(self) -> Optional[ThmDevice]:
        helper = self.coordinator.get_device_helper(self.device_id)
        return helper if isinstance(helper, ThmDevice) else None

    def _on_demo_room_slider(self, val_f: int) -> None:
        if self._updating_ui:
            return
        if isinstance(self.coordinator.sensorlinx, DemoSensorlinxClient):
            self.coordinator.sensorlinx.set_simulated_room_temp(self.device_id, float(val_f))
            self.sim_room_lbl.setText(UnitHelper.format_temp(val_f, self.unit, 1))
            asyncio.ensure_future(self.coordinator.async_refresh())

    def _on_hvac_mode_changed(self, mode: str) -> None:
        if self._updating_ui or not mode:
            return
        asyncio.ensure_future(self._async_set_hvac_mode(mode))

    async def _async_set_hvac_mode(self, mode: str) -> None:
        helper = self._get_thm_helper()
        if not helper:
            return
        try:
            await helper.set_hvac_mode(mode)
            self.coordinator.set_parameter_override(self.device_id, {"hvac_mode": mode})
            await self.coordinator.async_refresh()
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to set THM HVAC mode: {exc}")

    def _on_fan_mode_changed(self, mode: str) -> None:
        if self._updating_ui or not mode:
            return
        asyncio.ensure_future(self._async_set_fan_mode(mode))

    async def _async_set_fan_mode(self, mode: str) -> None:
        helper = self._get_thm_helper()
        if not helper:
            return
        try:
            await helper.set_fan_mode(mode)
            self.coordinator.set_parameter_override(self.device_id, {"fan_mode": mode})
            await self.coordinator.async_refresh()
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to set THM fan mode: {exc}")

    def _on_away_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        asyncio.ensure_future(self._async_set_away(checked))

    async def _async_set_away(self, checked: bool) -> None:
        helper = self._get_thm_helper()
        if not helper:
            return
        try:
            await helper.set_away_mode(checked)
            self.coordinator.set_parameter_override(self.device_id, {"away_mode_activated": checked})
            await self.coordinator.async_refresh()
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to toggle Away mode: {exc}")

    def _on_schedule_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        asyncio.ensure_future(self._async_set_schedule(checked))

    async def _async_set_schedule(self, checked: bool) -> None:
        helper = self._get_thm_helper()
        if not helper:
            return
        try:
            await helper.set_schedule_enabled(checked)
            self.coordinator.set_parameter_override(self.device_id, {"schedule_enabled": checked})
            await self.coordinator.async_refresh()
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to toggle THM schedule: {exc}")

    def _on_apply_home_setpoints(self) -> None:
        asyncio.ensure_future(self._async_apply_home_setpoints())

    async def _async_apply_home_setpoints(self) -> None:
        helper = self._get_thm_helper()
        if not helper:
            return
        try:
            heat_f = round(UnitHelper.display_to_f(self.heat_sp_spin.value(), self.unit))
            cool_f = round(UnitHelper.display_to_f(self.cool_sp_spin.value(), self.unit))
            await helper.set_heat_cool_setpoints(Temperature(heat_f, "F"), Temperature(cool_f, "F"))
            self.coordinator.set_parameter_override(
                self.device_id, {"heat_setpoint": float(heat_f), "cool_setpoint": float(cool_f)}
            )
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit(f"Updated {self.device_id} Home setpoints.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Invalid Home Setpoints: {exc}")

    def _on_apply_away_setpoints(self) -> None:
        asyncio.ensure_future(self._async_apply_away_setpoints())

    async def _async_apply_away_setpoints(self) -> None:
        helper = self._get_thm_helper()
        if not helper:
            return
        try:
            heat_f = round(UnitHelper.display_to_f(self.away_heat_spin.value(), self.unit))
            cool_f = round(UnitHelper.display_to_f(self.away_cool_spin.value(), self.unit))
            await helper.set_away_heat_cool_setpoints(Temperature(heat_f, "F"), Temperature(cool_f, "F"))
            self.coordinator.set_parameter_override(
                self.device_id, {"away_heat_setpoint": float(heat_f), "away_cool_setpoint": float(cool_f)}
            )
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit(f"Updated {self.device_id} Away setpoints.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Invalid Away Setpoints: {exc}")

    def _on_apply_humidity(self) -> None:
        asyncio.ensure_future(self._async_apply_humidity())

    async def _async_apply_humidity(self) -> None:
        helper = self._get_thm_helper()
        if not helper:
            return
        try:
            mode = self.hum_mode_combo.currentText()
            target = self.hum_target_spin.value()
            await helper.set_humidity_mode(mode)
            await helper.set_humidity_target(target)
            self.coordinator.set_parameter_override(
                self.device_id, {"humidity_mode": mode, "humidity_target": target}
            )
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit(f"Updated {self.device_id} Humidity settings.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to set THM humidity: {exc}")

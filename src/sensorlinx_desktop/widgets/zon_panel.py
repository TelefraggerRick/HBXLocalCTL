"""ZON-0600 Zone Controller monitoring and control panel."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from pysensorlinx import Temperature, ZonDevice

from ..coordinator import SensorlinxCoordinator
from ..models import UnitHelper

RELAY_TYPE_LABELS = {
    0: "Unwired / Disabled",
    1: "Single-Stage N/O",
    2: "Single-Stage N/C",
    3: "Two-Stage N/O",
    4: "Two-Stage N/C",
}


class ZonDevicePanel(QWidget):
    """Monitoring and control view for an HBX ZON-0600 Zone Controller."""

    navigate_to_device = Signal(str)
    request_cloud_snapshot_sync = Signal()

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

        # Header bar
        hdr = QFrame()
        hdr.setObjectName("CardFrame")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 12, 16, 12)

        title_col = QVBoxLayout()
        self.title_lbl = QLabel("ZON-0600 Zone Controller")
        self.title_lbl.setObjectName("SectionHeader")
        self.subtitle_lbl = QLabel("Sync Code: — | Sequence: —")
        self.subtitle_lbl.setObjectName("MutedText")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.subtitle_lbl)
        hdr_lay.addLayout(title_col)
        hdr_lay.addStretch()

        self.sync_cloud_btn = QPushButton("☁️ Sync Linked Thermostats & Config from Cloud")
        self.sync_cloud_btn.setToolTip(
            "One-time fetch of your linked THM-0600 thermostats and ZON-0600 settings from the official SensorLinx Cloud API for offline Local LAN use."
        )
        self.sync_cloud_btn.clicked.connect(self.request_cloud_snapshot_sync.emit)
        hdr_lay.addWidget(self.sync_cloud_btn)

        self.app_btn_chk = QCheckBox("App Button (Relay 12)")
        self.app_btn_chk.toggled.connect(self._on_app_button_toggled)
        hdr_lay.addWidget(self.app_btn_chk)

        root.addWidget(hdr)

        # Top 5 Summary Metric Cards (matching EcoDevicePanel layout)
        cards_layout = QGridLayout()
        cards_layout.setSpacing(10)

        self.demand_card_val = QLabel("—")
        self.demand_card_val.setObjectName("HeroMetric")
        self.demand_card_sub = QLabel("Priority: —")
        self.demand_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Zone Demand & Priority", self.demand_card_val, self.demand_card_sub), 0, 0
        )

        self.outdoor_card_val = QLabel("—")
        self.outdoor_card_val.setObjectName("HeroMetric")
        self.outdoor_card_sub = QLabel("Controller: —")
        self.outdoor_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Outdoor Sensor & RTC", self.outdoor_card_val, self.outdoor_card_sub), 0, 1
        )

        self.pumps_card_val = QLabel("—")
        self.pumps_card_val.setObjectName("StatusText")
        self.pumps_card_sub = QLabel("Post-Purge: —")
        self.pumps_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Zone Pumps (Pump 1 & 2)", self.pumps_card_val, self.pumps_card_sub), 0, 2
        )

        self.demands_card_val = QLabel("—")
        self.demands_card_val.setObjectName("StatusText")
        self.demands_card_sub = QLabel("Fancoil: —")
        self.demands_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Demands (1–3) & Fancoil", self.demands_card_val, self.demands_card_sub), 0, 3
        )

        self.aux_card_val = QLabel("—")
        self.aux_card_val.setObjectName("HeroMetricSmall")
        self.aux_card_sub = QLabel("Relay 12: —")
        self.aux_card_sub.setObjectName("MutedText")
        cards_layout.addWidget(
            self._make_metric_card("Aux Setpoint & Relay 12", self.aux_card_val, self.aux_card_sub), 0, 4
        )

        root.addLayout(cards_layout)

        # Wired Zone Relays & Linked Thermostats Grid (Zones 1–4)
        self.zones_grp = QGroupBox("Wired Zone Relays, Valve Types & Demand Status (Zones 1–4)")
        self.zones_grid = QGridLayout(self.zones_grp)
        self.zones_grid.setSpacing(12)
        root.addWidget(self.zones_grp)

        # Bottom Row: Auxiliary Setpoint & Controller Settings | Zone Outputs & Local Port 2000 Stream
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        self.ctrl_grp = QGroupBox("Auxiliary Heat Setpoint, App Button & Controller Parameters")
        ctrl_form = QFormLayout(self.ctrl_grp)
        ctrl_form.setSpacing(10)

        self.aux_mode_lbl = QLabel("—")
        ctrl_form.addRow("Auxiliary Mode:", self.aux_mode_lbl)

        self.aux_spin = QDoubleSpinBox()
        self.aux_spin.setDecimals(1)
        self._configure_aux_spin()
        ctrl_form.addRow("Auxiliary Setpoint (dhwT):", self.aux_spin)

        self.aux_diff_lbl = QLabel("—")
        ctrl_form.addRow("Aux Differential & Priority:", self.aux_diff_lbl)

        self.hw_config_lbl = QLabel("—")
        self.hw_config_lbl.setWordWrap(True)
        ctrl_form.addRow("Controller Configuration:", self.hw_config_lbl)

        apply_aux_btn = QPushButton("Apply Auxiliary Setpoint")
        apply_aux_btn.setObjectName("PrimaryButton")
        apply_aux_btn.clicked.connect(self._on_apply_aux_setpoint)
        ctrl_form.addRow(apply_aux_btn)

        bottom_row.addWidget(self.ctrl_grp, 1)

        diag_grp = QGroupBox("Zone Controller Outputs (Pumps, Demands, Fancoil & Relays 1–16)")
        diag_form = QFormLayout(diag_grp)
        diag_form.setSpacing(10)

        self.pumps_lbl = QLabel("—")
        self.pumps_lbl.setWordWrap(True)
        diag_form.addRow("Zone Pumps (Pump 1 & 2):", self.pumps_lbl)

        self.demands_lbl = QLabel("—")
        self.demands_lbl.setWordWrap(True)
        diag_form.addRow("Demand Channels (1–3):", self.demands_lbl)

        self.fancoil_lbl = QLabel("—")
        self.fancoil_lbl.setWordWrap(True)
        diag_form.addRow("Fancoil Outputs:", self.fancoil_lbl)

        self.relay12_lbl = QLabel("—")
        self.relay12_lbl.setWordWrap(True)
        diag_form.addRow("Relay Bank Status (1–16):", self.relay12_lbl)

        self.local_stream_lbl = QLabel("—")
        self.local_stream_lbl.setObjectName("MutedText")
        self.local_stream_lbl.setWordWrap(True)
        diag_form.addRow("Local TCP :2000 Stream:", self.local_stream_lbl)

        bottom_row.addWidget(diag_grp, 1)
        root.addLayout(bottom_row)
        root.addStretch()

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

    def _configure_aux_spin(self) -> None:
        low = UnitHelper.f_to_display(33.0, self.unit)
        high = UnitHelper.f_to_display(180.0, self.unit)
        self.aux_spin.setRange(low, high)
        self.aux_spin.setSingleStep(0.5 if self.unit == "C" else 1.0)
        self.aux_spin.setSuffix(" °C" if self.unit == "C" else " °F")

    def set_unit(self, unit: str) -> None:
        if unit.upper() == self.unit:
            return
        self.unit = unit.upper()
        self._configure_aux_spin()
        self.refresh_from_coordinator()

    @staticmethod
    def _scalar_f(val: Any) -> Optional[float]:
        if val is None or val == "off":
            return None
        if hasattr(val, "to_fahrenheit"):
            return float(val.to_fahrenheit())
        if hasattr(val, "value"):
            return float(val.value)
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def refresh_from_coordinator(self) -> None:
        if not self.coordinator.data or "devices" not in self.coordinator.data:
            return
        devices = self.coordinator.data["devices"]
        dev = devices.get(self.device_id)
        if not dev:
            return
        params = dev.get("parameters", {})
        is_local = bool(self.coordinator.is_local)
        lt = params.get("local_telemetry") or {}

        self._updating_ui = True
        try:
            seq = int(params.get("zone_sequence", 0) or 0)
            seq_name = params.get("sequence_name") or ("Primary" if seq == 0 else f"Secondary #{seq}")
            seq_range = params.get("sequence_range") or f"{seq * 4 + 1}-{seq * 4 + 4}"
            thm_bver = params.get("thm_board_ver", lt.get("thmBVer", "0.00"))

            self.title_lbl.setText(f"{dev.get('name', self.device_id)}  (HBX ZON-0600)")
            self.subtitle_lbl.setText(
                f"Sync Code: {dev.get('syncCode', self.device_id)}  •  "
                f"Firmware: v{params.get('firmware_version', '—')} (thmBVer {thm_bver})  •  "
                f"Zone ID: {params.get('zone_id', 1)}  •  {seq_name} (Zones {seq_range})"
            )

            self.sync_cloud_btn.setVisible(is_local)

            # App Button (Relay 12) stays visible and functional in both Cloud & Local modes
            btn_text = params.get("app_button_text") or "App Button"
            self.app_btn_chk.setVisible(True)
            self.app_btn_chk.setText(f"{btn_text} (Relay 12)")
            self.app_btn_chk.setEnabled(bool(params.get("app_button_enabled", True)))
            self.app_btn_chk.setChecked(bool(params.get("app_button_activated", False)))

            relays = list(params.get("relays") or [False] * 16)
            if len(relays) < 16:
                relays.extend([False] * (16 - len(relays)))
            relay_types = list(params.get("relay_types") or [1, 1, 1, 1])

            # 1:1 slot-aligned thermostat sync codes (`thm_slots` preserves None slots)
            thm_slots = list(params.get("thm_slots") or [])
            if not thm_slots:
                thm_slots = list(params.get("thermostat_sync_codes") or [])
            while len(thm_slots) < 4:
                thm_slots.append(None)

            # Card 1: Zone Demand & Priority
            active_zones = [seq * 4 + i + 1 for i in range(4) if relays[i]]
            dem_mask = int(params.get("demand_on", lt.get("znInDem", 0)) or 0)
            zn_pri = params.get("zone_priority", lt.get("znInPri", 9))
            pri_str = "None (znInPri=9)" if str(zn_pri) == "9" else f"Zone {zn_pri}"
            if active_zones:
                self.demand_card_val.setText(f"{len(active_zones)} / 4 Calling (Z{', Z'.join(map(str, active_zones))})")
            else:
                self.demand_card_val.setText("0 / 4 Calling (Idle)")
            self.demand_card_sub.setText(f"Demand Mask (znInDem): {dem_mask}  •  Priority: {pri_str}")

            # Card 2: Outdoor Sensor & Controller RTC
            out_f = self._scalar_f(params.get("temperature_outdoor", lt.get("out")))
            self.outdoor_card_val.setText(UnitHelper.format_temp(out_f, self.unit, 1))
            if is_local:
                conn_txt = "ONLINE" if lt.get("connected") else "CONNECTING"
                self.outdoor_card_sub.setText(
                    f"{lt.get('host', '192.168.1.51')}:2000 ({conn_txt})  •  SSID: {lt.get('SSID', '—')}\n"
                    f"RTC: {lt.get('rtc_str', '—')}"
                )
            else:
                tz = params.get("timezone", -3.5)
                self.outdoor_card_sub.setText(
                    f"FW: v{params.get('firmware_version', '—')}  •  thmBVer: {thm_bver}  •  TZ: UTC{tz:+g}"
                )

            # Card 3: Zone Pumps (Pump 1 & Pump 2)
            pumps = params.get("pumps") or []
            pump_parts = [
                f"{p.get('title', 'Pump')}: {'ON' if p.get('activated') else 'OFF'} ({p.get('mode', '—')})"
                for p in pumps
            ]
            self.pumps_card_val.setText("  •  ".join(pump_parts) if pump_parts else "Idle")
            p1_pp = params.get("p1_post_purge", 60)
            p2_pp = params.get("p2_post_purge", 60)
            zn_pp = params.get("zn_post_purge", 60)
            self.pumps_card_sub.setText(f"Post-Purge: P1={p1_pp}s  |  P2={p2_pp}s  |  Zone={zn_pp}s")

            # Card 4: Demands (1-3) & Fancoil
            demands = params.get("demands") or []
            dmd_parts = [
                f"{d.get('abbr', d.get('title', 'Dmd'))}: {'CALLING' if d.get('activated') else 'Idle'}"
                for d in demands
            ]
            self.demands_card_val.setText("  •  ".join(dmd_parts) if dmd_parts else "Idle")
            fancoil = params.get("fancoil") or []
            fc_active = [f.get("title", "FC") for f in fancoil if f.get("activated")]
            self.demands_card_sub.setText(
                f"Fancoil Active: {', '.join(fc_active)}" if fc_active else "Fancoil (Heat/Cool/Fan/Hum): All Idle"
            )

            # Card 5: Aux Setpoint & Relay 12
            aux_t_f = self._scalar_f(params.get("aux_setpoint_target"))
            aux_cur_f = self._scalar_f(params.get("aux_setpoint_temp"))
            aux_diff_f = self._scalar_f(params.get("aux_differential")) or 8.0
            r12 = bool(relays[11]) or bool(params.get("app_button_activated", False))
            self.aux_card_val.setText(
                f"Target: {UnitHelper.format_temp(aux_t_f, self.unit, 1)}"
                + (f" (Actual: {UnitHelper.format_temp(aux_cur_f, self.unit, 1)})" if aux_cur_f is not None else "")
            )
            self.aux_card_sub.setText(
                f"Diff: {UnitHelper.format_delta(aux_diff_f, self.unit, 1)}  •  Relay 12 ({btn_text}): {'ON' if r12 else 'OFF'}"
            )

            # Rebuild 4 Zone Relay Cards
            self.zones_grp.setTitle(f"Wired Zone Relays, Valve Types & Demand Status (Zones {seq_range})")
            while self.zones_grid.count():
                item = self.zones_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            zone_count = max(4, len(relay_types))
            for idx in range(zone_count):
                rtype_code = int(relay_types[idx]) if idx < len(relay_types) else 1
                wired = rtype_code != 0
                rtype_label = RELAY_TYPE_LABELS.get(rtype_code, f"Type {rtype_code}")
                zone_num = seq * 4 + idx + 1
                energized = bool(relays[idx]) if idx < len(relays) else False
                thm_code = thm_slots[idx] if idx < len(thm_slots) else None
                thm_dev = devices.get(thm_code) if thm_code else None

                card = QFrame()
                card.setObjectName("CardFrame")
                c_lay = QVBoxLayout(card)
                c_lay.setContentsMargins(14, 12, 14, 12)
                c_lay.setSpacing(6)

                z_hdr = QLabel(f"ZONE {zone_num}  •  {rtype_label.upper()}")
                z_hdr.setObjectName("CardTitle")
                c_lay.addWidget(z_hdr)

                status_txt = (
                    "🔥 RELAY ENERGIZED (CALLING)"
                    if energized
                    else ("IDLE (SATISFIED)" if wired else "Disabled / Unwired Slot")
                )
                z_state = QLabel(status_txt)
                z_state.setObjectName("StatusText" if energized else "MutedText")
                c_lay.addWidget(z_state)

                bit_lbl = QLabel(
                    f"Relay {idx + 1}: {'ON (1)' if energized else 'OFF (0)'}   •   "
                    f"znInDem Bit {idx}: {'1' if (dem_mask & (1 << idx)) else '0'}"
                )
                bit_lbl.setObjectName("MutedText")
                c_lay.addWidget(bit_lbl)

                if thm_dev:
                    t_params = thm_dev.get("parameters", {})
                    rm_str = UnitHelper.format_temp(t_params.get("temperature_room"), self.unit, 1)
                    flr_val = t_params.get("temperature_floor")
                    flr_str = f"  •  Floor: {UnitHelper.format_temp(flr_val, self.unit, 1)}" if flr_val is not None else ""
                    sp_str = UnitHelper.format_temp(t_params.get("target_temperature_room"), self.unit, 1)
                    thm_info = QLabel(
                        f"Thermostat: {thm_dev.get('name', thm_code)} ({thm_code})\n"
                        f"Room: {rm_str}{flr_str}  •  Target: {sp_str}"
                    )
                    thm_info.setObjectName("MutedText")
                    thm_info.setWordWrap(True)
                    c_lay.addWidget(thm_info)

                    jump_btn = QPushButton(f"Open {thm_dev.get('name', thm_code)}")
                    jump_btn.clicked.connect(lambda _=False, cid=thm_code: self.navigate_to_device.emit(cid))
                    c_lay.addWidget(jump_btn)
                elif thm_code:
                    thm_lbl = QLabel(f"Assigned Thermostat: {thm_code}")
                    thm_lbl.setObjectName("MutedText")
                    c_lay.addWidget(thm_lbl)
                else:
                    hint_txt = (
                        "No THM-0600 cached yet (click '☁️ Sync' above to import)"
                        if is_local
                        else "No linked THM-0600 thermostat in slot"
                    )
                    unlinked_lbl = QLabel(hint_txt)
                    unlinked_lbl.setObjectName("MutedText")
                    unlinked_lbl.setWordWrap(True)
                    c_lay.addWidget(unlinked_lbl)

                self.zones_grid.addWidget(card, 0, idx)

            # Bottom Left: Aux setpoint & controller parameters
            self.ctrl_grp.setVisible(True)
            self.aux_mode_lbl.setText(str(params.get("aux_setpoint_mode") or "Auxiliary Setpoint (Mode 0)"))
            if aux_t_f is not None:
                self.aux_spin.setValue(UnitHelper.f_to_display(aux_t_f, self.unit))

            aux_pri = params.get("aux_priority", 9)
            aux_pri_str = "None (9)" if str(aux_pri) == "9" else f"Priority {aux_pri}"
            self.aux_diff_lbl.setText(
                f"{UnitHelper.format_delta(aux_diff_f, self.unit, 1)} (auxDif)   •   Aux Priority: {aux_pri_str}"
            )

            wwsd_raw = params.get("wwsd", 150)
            wwsd_str = "Off (150)" if wwsd_raw == 150 else UnitHelper.format_temp(self._scalar_f(wwsd_raw), self.unit, 0)
            pipe_str = "4-Pipe Hydronic" if params.get("four_pipe") else "2-Pipe Hydronic"
            ex_tm = params.get("exercise_time", 24)
            self.hw_config_lbl.setText(
                f"System: {pipe_str}   •   WWSD: {wwsd_str}   •   "
                f"Valve Exercise: Every {ex_tm}h   •   Backlight: {'On' if params.get('backlight', True) else 'Off'}"
            )

            # Bottom Right: Detailed Pumps, Demands, Fancoil, Relays 1-16 & Local TCP :2000 Stream
            self.pumps_lbl.setText(
                "   •   ".join(
                    f"{p.get('title', 'Pump')}: {'ON' if p.get('activated') else 'OFF'} (Mode: {p.get('mode', '—')})"
                    for p in pumps
                )
                or "—"
            )
            self.demands_lbl.setText(
                "   •   ".join(
                    f"{d.get('title', 'Demand')} ({d.get('abbr', '—')}): {'ACTIVE' if d.get('activated') else 'Idle'}"
                    for d in demands
                )
                or "—"
            )
            self.fancoil_lbl.setText(
                "   •   ".join(
                    f"{f.get('title', 'FC')}: {'ON' if f.get('activated') else 'Idle'}" for f in fancoil
                )
                or "—"
            )

            z_relays_str = ", ".join(f"R{i+1}:{'ON' if relays[i] else 'OFF'}" for i in range(4))
            other_active = [f"R{i+1}" for i in range(4, 16) if relays[i] and i != 11]
            other_str = f"  |  Other Active: {', '.join(other_active)}" if other_active else ""
            self.relay12_lbl.setText(
                f"{z_relays_str}   |   Relay 12 ({btn_text}): {'ENERGIZED (ON)' if r12 else 'OFF'}{other_str}"
            )

            if is_local or lt:
                self.local_stream_lbl.setText(
                    f"Host {lt.get('host', '192.168.1.51')}:2000 ({lt.get('frames_received', 0)} frames)  •  "
                    f"Latest: {lt.get('last_decrypted_text', 'Waiting for frame...')}"
                )
            else:
                self.local_stream_lbl.setText("Connected via SensorLinx Cloud API (Local Snapshot Cached)")
        finally:
            self._updating_ui = False

    def _get_zon_helper(self) -> Optional[ZonDevice]:
        helper = self.coordinator.get_device_helper(self.device_id)
        return helper if isinstance(helper, ZonDevice) else None

    def _on_app_button_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        asyncio.ensure_future(self._async_set_app_button(checked))

    async def _async_set_app_button(self, checked: bool) -> None:
        helper = self._get_zon_helper()
        if not helper:
            return
        try:
            await helper.set_app_button(checked)
            self.coordinator.set_parameter_override(self.device_id, {"app_button_activated": checked})
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit(
                f"Toggled {self.device_id} App Button (Relay 12) -> {'ON' if checked else 'OFF'}."
            )
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to toggle ZON App Button: {exc}")

    def _on_apply_aux_setpoint(self) -> None:
        asyncio.ensure_future(self._async_apply_aux_setpoint())

    async def _async_apply_aux_setpoint(self) -> None:
        helper = self._get_zon_helper()
        if not helper:
            return
        try:
            temp_f = round(UnitHelper.display_to_f(self.aux_spin.value(), self.unit))
            await helper.set_aux_setpoint(Temperature(temp_f, "F"))
            self.coordinator.set_parameter_override(self.device_id, {"aux_setpoint_target": temp_f})
            await self.coordinator.async_refresh()
            self.coordinator.status_changed.emit(f"Updated {self.device_id} Auxiliary Setpoint to {temp_f}°F.")
        except Exception as exc:
            self.coordinator.error_occurred.emit(f"Failed to set ZON Auxiliary Setpoint: {exc}")

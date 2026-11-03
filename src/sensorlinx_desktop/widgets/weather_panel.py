"""Whole-Home System Overview and Building Weather / Local LAN Hardware Summary Panel."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..coordinator import SensorlinxCoordinator
from ..models import UnitHelper


class SystemOverviewPanel(QWidget):
    """Whole-building dashboard showing all HBX devices and outdoor weather or local LAN telemetry."""

    navigate_to_device = Signal(str)

    def __init__(
        self,
        coordinator: SensorlinxCoordinator,
        unit: str = "F",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.coordinator = coordinator
        self.unit = unit.upper()

        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self.root_layout = QVBoxLayout(container)
        self.root_layout.setContentsMargins(14, 14, 14, 14)
        self.root_layout.setSpacing(16)

        # Top Banner
        hdr = QFrame()
        hdr.setObjectName("CardFrame")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(18, 14, 18, 14)

        col = QVBoxLayout()
        self.bldg_title = QLabel("HBX Controls Home Heating & Cooling Overview")
        self.bldg_title.setObjectName("SectionHeader")
        self.bldg_sub = QLabel("Select any controller, zone module, or thermostat below to view or configure parameters.")
        self.bldg_sub.setObjectName("MutedText")
        col.addWidget(self.bldg_title)
        col.addWidget(self.bldg_sub)
        hdr_lay.addLayout(col)
        hdr_lay.addStretch()
        self.root_layout.addWidget(hdr)

        # Weather / Local LAN Outdoor Probe section
        self.weather_group = QGroupBox("Building Outdoor Weather & Multi-Period Forecast")
        w_lay = QVBoxLayout(self.weather_group)
        w_lay.setSpacing(12)

        self.current_weather_lbl = QLabel("Loading weather...")
        self.current_weather_lbl.setObjectName("StatusText")
        self.current_weather_details = QLabel("")
        self.current_weather_details.setObjectName("MutedText")
        self.current_weather_details.setWordWrap(True)
        w_lay.addWidget(self.current_weather_lbl)
        w_lay.addWidget(self.current_weather_details)

        self.forecast_grid = QGridLayout()
        self.forecast_grid.setSpacing(10)
        w_lay.addLayout(self.forecast_grid)
        self.root_layout.addWidget(self.weather_group)

        # Devices Grid section
        self.devices_group = QGroupBox("Discovered HBX Devices (ECO-0600, ZON-0600, THM-0600)")
        self.devices_grid = QGridLayout(self.devices_group)
        self.devices_grid.setSpacing(12)
        self.root_layout.addWidget(self.devices_group)
        self.root_layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def set_unit(self, unit: str) -> None:
        if unit.upper() == self.unit:
            return
        self.unit = unit.upper()
        self.refresh_from_coordinator()

    def refresh_from_coordinator(self) -> None:
        data = self.coordinator.data
        if not data:
            return

        is_local = bool(data.get("is_local"))
        buildings = data.get("buildings") or []
        devices = data.get("devices") or {}
        weather_map = data.get("weather") or {}

        if buildings:
            b_names = ", ".join(b.get("name", b.get("id", "Building")) for b in buildings)
            self.bldg_title.setText(f"System Overview — {b_names}")
            mode_note = "Direct Local LAN TCP :2000 XTEA Stream (No Cloud)" if is_local else "Cloud / Demo Poll"
            self.bldg_sub.setText(
                f"{len(devices)} HBX device(s) configured  •  {mode_note}  •  Last update: {data.get('last_updated', '—')}"
            )

        # Clear forecast / local host cards grid
        while self.forecast_grid.count():
            item = self.forecast_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        first_b_id = (buildings[0].get("id") or buildings[0].get("_id")) if buildings else None
        b_weather = weather_map.get(first_b_id) if first_b_id else None

        if is_local:
            self.weather_group.setTitle("Local LAN Hardware Outdoor Sensor & Stream Status (TCP Port 2000 XTEA)")
            cur = (b_weather or {}).get("current") or {}
            temp_val = cur.get("temp")
            temp_s = UnitHelper.format_temp(temp_val, self.unit, 1) if temp_val is not None else "Waiting for stream..."

            total_frames = 0
            online_hosts = 0
            ssids = set()
            for dev in devices.values():
                lt = (dev.get("parameters") or {}).get("local_telemetry") or {}
                total_frames += int(lt.get("frames_received", 0))
                if lt.get("connected"):
                    online_hosts += 1
                if lt.get("SSID") and lt.get("SSID") != "—":
                    ssids.add(str(lt.get("SSID")))

            ssid_str = ", ".join(sorted(ssids)) if ssids else "Local-IoT-LAN"
            self.current_weather_lbl.setText(
                f"Live Outdoor Sensor Probe: {temp_s}   •   Local Controllers Online: {online_hosts}/{len(devices)}   •   "
                f"XTEA Frames Decoded: {total_frames}"
            )
            self.current_weather_details.setText(
                f"Wi-Fi Network (SSID): {ssid_str}   |   Encryption: 128-bit XTEA ECB (32 rounds, little-endian)   |   "
                f"No cloud connection required — all telemetry below comes directly from your local LAN controllers."
            )
        elif b_weather and "current" in b_weather:
            self.weather_group.setTitle("Building Outdoor Weather & Multi-Period Forecast")
            cur = b_weather["current"]
            desc = str(cur.get("description") or "Clear").title()
            temp_s = UnitHelper.format_temp(cur.get("temp"), self.unit, 1)
            feels_s = UnitHelper.format_temp(cur.get("feelsLike"), self.unit, 1)
            min_s = UnitHelper.format_temp(cur.get("min"), self.unit, 1)
            max_s = UnitHelper.format_temp(cur.get("max"), self.unit, 1)
            self.current_weather_lbl.setText(
                f"Outdoor Now: {temp_s}  ({desc})   •   Feels Like: {feels_s}   •   Low/High: {min_s} / {max_s}"
            )
            self.current_weather_details.setText(
                f"Humidity: {cur.get('humidity', '—')}%   |   Pressure: {cur.get('pressure', '—')} hPa   |   "
                f"Wind: {cur.get('wind', '—')} mph ({cur.get('windDir', '—')}°)   |   Clouds: {cur.get('clouds', '—')}%"
            )

            forecast = b_weather.get("forecast") or []
            for idx, period in enumerate(forecast[:6]):
                f_card = QFrame()
                f_card.setObjectName("CardFrame")
                fl = QVBoxLayout(f_card)
                fl.setContentsMargins(10, 8, 10, 8)
                dt = period.get("time")
                time_str = dt.strftime("%a %H:%M") if hasattr(dt, "strftime") else str(dt)
                t_lbl = QLabel(time_str)
                t_lbl.setObjectName("CardTitle")
                v_lbl = QLabel(UnitHelper.format_temp(period.get("temp"), self.unit, 1))
                v_lbl.setObjectName("StatusText")
                d_lbl = QLabel(
                    f"{str(period.get('description', '')).title()}\n"
                    f"PoP: {period.get('pop', 0)}%"
                )
                d_lbl.setObjectName("MutedText")
                fl.addWidget(t_lbl)
                fl.addWidget(v_lbl)
                fl.addWidget(d_lbl)
                self.forecast_grid.addWidget(f_card, 0, idx)
        else:
            self.current_weather_lbl.setText("No building weather data reported.")
            self.current_weather_details.setText("")

        # Populate Device Cards
        while self.devices_grid.count():
            item = self.devices_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, (dev_id, dev) in enumerate(devices.items()):
            params = dev.get("parameters", {})
            lt = params.get("local_telemetry") or {}
            dtype = (params.get("device_type") or dev.get("deviceType") or "ECO").upper()
            card = QFrame()
            card.setObjectName("CardFrame")
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(16, 14, 16, 14)
            c_lay.setSpacing(6)

            conn_tag = ""
            if is_local:
                conn_tag = f"  •  {'ONLINE' if lt.get('connected') else 'CONNECTING'} ({lt.get('host', '')}:2000)"
            badge = QLabel(f"{dtype}-0600  •  {dev_id}{conn_tag}")
            badge.setObjectName("CardTitle")
            c_lay.addWidget(badge)

            name_lbl = QLabel(dev.get("name", dev_id))
            name_lbl.setObjectName("SectionHeader")
            c_lay.addWidget(name_lbl)

            if dtype == "ECO":
                if is_local:
                    od = UnitHelper.format_temp(params.get("temperature_outdoor"), self.unit, 1)
                    stg_s = lt.get("stgS")
                    stg_txt = "ON (ACTIVE)" if stg_s else ("OFF (IDLE)" if stg_s is not None else "Waiting...")
                    metric = QLabel(f"Outdoor: {od}   •   Stage 1: {stg_txt}")
                    metric.setObjectName("HeroMetricSmall")
                    rev_v = lt.get("revV")
                    rev_txt = "Cooling (revV=1)" if rev_v else "Heating (revV=0)"
                    bk_txt = "FIRING" if lt.get("priBUp") else ("Armed" if lt.get("useBkUp") else "Off")
                    sub = QLabel(
                        f"Firmware: v{params.get('firmware_version', '—')}  •  Stages: {lt.get('numStg', 1)}  •  Mode: {rev_txt}\n"
                        f"Backup: {bk_txt} (useBkUp={lt.get('useBkUp', '—')}, priBUp={lt.get('priBUp', '—')})  •  secPmp: {lt.get('secPmp', '—')}\n"
                        f"Controller RTC: {lt.get('rtc_str', '—')}  •  Frames: {lt.get('frames_received', 0)}"
                    )
                    sub.setObjectName("MutedText")
                    sub.setWordWrap(True)
                    c_lay.addWidget(metric)
                    c_lay.addWidget(sub)
                else:
                    tk = UnitHelper.format_temp(params.get("temperature_tank"), self.unit, 1)
                    tg = UnitHelper.format_temp(params.get("target_temperature_tank"), self.unit, 1)
                    od = UnitHelper.format_temp(params.get("temperature_outdoor"), self.unit, 1)
                    dhw = UnitHelper.format_temp(params.get("temperature_dhw_tank"), self.unit, 1)
                    metric = QLabel(f"Tank: {tk}  (Target {tg})")
                    metric.setObjectName("HeroMetricSmall")
                    sub = QLabel(
                        f"Outdoor: {od}  •  DHW: {dhw}\n"
                        f"Mode Priority: {str(params.get('hvac_mode', 'auto')).upper()}"
                    )
                    sub.setObjectName("MutedText")
                    c_lay.addWidget(metric)
                    c_lay.addWidget(sub)
            elif dtype == "THM":
                rm = UnitHelper.format_temp(params.get("temperature_room"), self.unit, 1)
                flr = UnitHelper.format_temp(params.get("temperature_floor"), self.unit, 1)
                h_sp = UnitHelper.format_temp(params.get("heat_setpoint"), self.unit, 0)
                c_sp = UnitHelper.format_temp(params.get("cool_setpoint"), self.unit, 0)
                demands = params.get("active_demands") or []
                act_str = ", ".join(d.upper() for d in demands) if demands else "IDLE"
                metric = QLabel(f"Room: {rm}")
                metric.setObjectName("HeroMetricSmall")
                sub = QLabel(
                    f"Floor: {flr}  •  Humidity: {params.get('humidity', '—')}%\n"
                    f"Heat/Cool SP: {h_sp} / {c_sp}  •  Action: {act_str}"
                )
                sub.setObjectName("MutedText")
                c_lay.addWidget(metric)
                c_lay.addWidget(sub)
            elif dtype == "ZON":
                relays = params.get("relays") or []
                r_types = params.get("relay_types") or []
                wired_cnt = sum(1 for r in r_types if r != 0) if r_types else 4
                active_cnt = sum(1 for i in range(min(wired_cnt, len(relays))) if relays[i])
                if is_local:
                    od_val = lt.get("out")
                    od_s = UnitHelper.format_temp(float(od_val), self.unit, 1) if od_val is not None else "—"
                    zn_pri = lt.get("znInPri", 9)
                    pri_str = "None (9)" if str(zn_pri) == "9" else f"Zone {zn_pri}"
                    metric = QLabel(f"{active_cnt} / {wired_cnt} Zones Calling  (znInDem={lt.get('znInDem', 0)})")
                    metric.setObjectName("HeroMetricSmall")
                    sub = QLabel(
                        f"Firmware: v{params.get('firmware_version', '—')} (thmBVer {lt.get('thmBVer', '—')})  •  Outdoor: {od_s}\n"
                        f"Priority Zone (znInPri): {pri_str}  •  Wi-Fi SSID: {lt.get('SSID', '—')}\n"
                        f"Controller RTC: {lt.get('rtc_str', '—')}  •  Frames: {lt.get('frames_received', 0)}"
                    )
                    sub.setObjectName("MutedText")
                    sub.setWordWrap(True)
                    c_lay.addWidget(metric)
                    c_lay.addWidget(sub)
                else:
                    metric = QLabel(f"{active_cnt} / {wired_cnt} Zones Calling")
                    metric.setObjectName("HeroMetricSmall")
                    sub = QLabel(
                        f"Aux Setpoint: {UnitHelper.format_temp(params.get('aux_setpoint_target'), self.unit, 0)}\n"
                        f"Linked Thermostats: {', '.join(params.get('thermostat_sync_codes') or []) or 'None'}"
                    )
                    sub.setObjectName("MutedText")
                    c_lay.addWidget(metric)
                    c_lay.addWidget(sub)

            c_lay.addStretch()
            open_btn = QPushButton(f"Open {dev.get('name', dev_id)} →")
            open_btn.setObjectName("PrimaryButton")
            open_btn.clicked.connect(lambda _=False, did=dev_id: self.navigate_to_device.emit(did))
            c_lay.addWidget(open_btn)

            row = idx // 3
            col = idx % 3
            self.devices_grid.addWidget(card, row, col)

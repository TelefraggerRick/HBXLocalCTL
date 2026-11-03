"""Data coordinator managing SensorLinx cloud polling, parameter extraction, and optimistic writes."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QTimer, Signal
from pysensorlinx import (
    DEVICE_TYPE_ECO,
    DEVICE_TYPE_THM,
    DEVICE_TYPE_ZON,
    InvalidCredentialsError,
    LoginError,
    LoginTimeoutError,
    Sensorlinx,
    SensorlinxDevice,
    ThmDevice,
    ZonDevice,
    device_for,
)

from .demo_client import DemoSensorlinxClient
from .local_client import LocalSensorlinxClient, save_cloud_snapshot
from .local_probe import LocalLanManager

_LOGGER = logging.getLogger(__name__)


async def extract_eco_parameters(device_helper: SensorlinxDevice, device: dict) -> dict[str, Any]:
    """Extract all ECO-0600 parameters and runtime system state."""
    parameters: dict[str, Any] = {}

    try:
        temps = await device_helper.get_temperatures(device_info=device)
        if temps:
            for temp_name, temp_data in temps.items():
                slug = temp_name.lower().replace(" ", "_")
                if temp_data.get("actual") is not None:
                    parameters[f"temperature_{slug}"] = temp_data["actual"].value
                if temp_data.get("target") is not None:
                    parameters[f"target_temperature_{slug}"] = temp_data["target"].value
    except Exception:
        pass

    async def _grab(key: str, fn):
        try:
            value = await fn(device_info=device)
            if value is not None:
                parameters[key] = value
        except Exception:
            pass

    await _grab("permanent_heat_demand", device_helper.get_permanent_heat_demand)
    await _grab("permanent_cool_demand", device_helper.get_permanent_cool_demand)
    try:
        raw_prior = await device_helper.get_hvac_mode_priority(device_info=device)
        if isinstance(raw_prior, int):
            mode_map = {0: "heat", 1: "cool", 2: "auto"}
            parameters["hvac_mode"] = mode_map.get(raw_prior, "auto")
        elif isinstance(raw_prior, str):
            parameters["hvac_mode"] = raw_prior.lower()
    except Exception:
        pass

    await _grab("hot_tank_min_temp", device_helper.get_hot_tank_min_temp)
    await _grab("hot_tank_max_temp", device_helper.get_hot_tank_max_temp)
    await _grab("hot_tank_outdoor_reset", device_helper.get_hot_tank_outdoor_reset)
    await _grab("cold_tank_min_temp", device_helper.get_cold_tank_min_temp)
    await _grab("cold_tank_max_temp", device_helper.get_cold_tank_max_temp)
    await _grab("cold_tank_outdoor_reset", device_helper.get_cold_tank_outdoor_reset)
    await _grab("warm_weather_shutdown", device_helper.get_warm_weather_shutdown)
    await _grab("cold_weather_shutdown", device_helper.get_cold_weather_shutdown)

    await _grab("stage_on_lag_time", device_helper.get_stage_on_lag_time)
    await _grab("stage_off_lag_time", device_helper.get_stage_off_lag_time)
    await _grab("rotate_cycles", device_helper.get_rotate_cycles)
    await _grab("rotate_time", device_helper.get_rotate_time)
    await _grab("off_staging", device_helper.get_off_staging)
    await _grab("backup_lag_time", device_helper.get_backup_lag_time)
    await _grab("backup_differential", device_helper.get_backup_differential)
    await _grab("hot_tank_differential", device_helper.get_hot_tank_differential)
    await _grab("cold_tank_differential", device_helper.get_cold_tank_differential)
    await _grab("backup_only_outdoor_temp", device_helper.get_backup_only_outdoor_temp)
    await _grab("number_of_stages", device_helper.get_number_of_stages)
    await _grab("backup_temp", device_helper.get_backup_temp)
    await _grab("wide_priority_differential", device_helper.get_wide_priority_differential)
    await _grab("weather_shutdown_lag_time", device_helper.get_weather_shutdown_lag_time)
    await _grab("two_stage_heat_pump", device_helper.get_two_stage_heat_pump)
    await _grab("heat_cool_switch_delay", device_helper.get_heat_cool_switch_delay)
    await _grab("backup_only_tank_temp", device_helper.get_backup_only_tank_temp)
    await _grab("dhw_enabled", device_helper.get_dhw_enabled)
    await _grab("dhw_target_temp", device_helper.get_dhw_target_temp)
    await _grab("dhw_differential", device_helper.get_dhw_differential)

    try:
        stages = await device_helper.get_heatpump_stages_state(device_info=device)
        if stages is not None:
            parameters["heatpump_stages"] = stages
    except Exception:
        pass

    try:
        backup = await device_helper.get_backup_state(device_info=device)
        if backup is not None:
            parameters["backup_state"] = backup
    except Exception:
        pass

    try:
        dhw_state = await device_helper.get_dhw_state(device_info=device)
        if dhw_state is not None:
            parameters["dhw_state"] = dhw_state
    except Exception:
        pass

    try:
        sys_state = await device_helper.get_system_state(device_info=device)
        if sys_state is not None:
            parameters["system_state"] = sys_state
    except Exception:
        pass

    return parameters


async def extract_thm_parameters(device_helper: ThmDevice, device: dict) -> dict[str, Any]:
    """Extract all THM-0600 thermostat parameters."""
    parameters: dict[str, Any] = {}

    try:
        room = await device_helper.get_room_temperature(device)
        if room is not None:
            parameters["temperature_room"] = room.value
    except Exception:
        pass

    try:
        floor = await device_helper.get_floor_temperature(device)
        if floor is not None:
            parameters["temperature_floor"] = floor.value
    except Exception:
        pass

    try:
        target = await device_helper.get_target_temperature(device)
        if target is not None:
            parameters["target_temperature_room"] = target.value
    except Exception:
        pass

    try:
        heat_sp = await device_helper.get_heat_setpoint(device)
        if heat_sp is not None:
            parameters["heat_setpoint"] = heat_sp.value
    except Exception:
        pass

    try:
        cool_sp = await device_helper.get_cool_setpoint(device)
        if cool_sp is not None:
            parameters["cool_setpoint"] = cool_sp.value
    except Exception:
        pass

    if hasattr(device_helper, "get_active_demands"):
        try:
            demands = await device_helper.get_active_demands(device)
            if demands is not None:
                parameters["active_demands"] = list(demands)
        except Exception:
            pass

    for key, coro in [
        ("humidity", device_helper.get_humidity(device)),
        ("hvac_mode", device_helper.get_hvac_mode(device)),
        ("fan_mode", device_helper.get_fan_mode(device)),
        ("thm_mode", device_helper.get_thm_mode(device)),
        ("target_type", device_helper.get_target_type(device)),
        ("schedules", device_helper.get_schedules(device)),
        ("demands_list", device_helper.get_demands(device)),
    ]:
        try:
            val = await coro
            if val is not None:
                parameters[key] = val
        except Exception:
            pass

    try:
        parameters["is_off"] = bool(await device_helper.is_off(device))
        parameters["is_heating"] = bool(await device_helper.is_heating(device))
        parameters["is_cooling"] = bool(await device_helper.is_cooling(device))
    except Exception:
        pass

    try:
        away = await device_helper.get_away_mode(device)
        if isinstance(away, dict):
            parameters["away_mode_activated"] = bool(away.get("activated"))
    except Exception:
        pass

    if hasattr(device_helper, "get_away_heat_setpoint"):
        try:
            ah = await device_helper.get_away_heat_setpoint(device)
            if ah is not None:
                parameters["away_heat_setpoint"] = ah.value
        except Exception:
            pass

    if hasattr(device_helper, "get_away_cool_setpoint"):
        try:
            ac = await device_helper.get_away_cool_setpoint(device)
            if ac is not None:
                parameters["away_cool_setpoint"] = ac.value
        except Exception:
            pass

    if "pgmble" in device:
        parameters["schedule_enabled"] = bool(device.get("pgmble"))
    if "useHum" in device:
        hm_mode = {0: "off", 1: "on", 2: "auto"}.get(device.get("useHum"))
        if hm_mode is not None:
            parameters["humidity_mode"] = hm_mode
    if "hmT" in device:
        try:
            parameters["humidity_target"] = int(device.get("hmT"))
        except (TypeError, ValueError):
            pass

    return parameters


async def extract_zon_parameters(device_helper: ZonDevice, device: dict) -> dict[str, Any]:
    """Extract all ZON-0600 zone controller parameters (matching official API & hass_hbxcontrols)."""
    parameters: dict[str, Any] = {}

    for key, coro in [
        ("relays", device_helper.get_relays(device)),
        ("relay_types", device_helper.get_relay_types(device)),
        ("zone_id", device_helper.get_zone_id(device)),
        ("pumps", device_helper.get_pumps(device)),
        ("fancoil", device_helper.get_fancoil(device)),
        ("demands", device_helper.get_demands(device)),
    ]:
        try:
            val = await coro
            if val is not None:
                parameters[key] = val
        except Exception:
            pass

    if "relStat" in device and isinstance(device.get("relStat"), list):
        parameters["relay_status"] = list(device["relStat"])

    # Sequence info (`sequence` dict or integer `znSeq`)
    seq_raw = device.get("sequence")
    if isinstance(seq_raw, dict):
        parameters["zone_sequence"] = int(seq_raw.get("value", device.get("znSeq", 0)) or 0)
        parameters["sequence_name"] = str(seq_raw.get("name") or "Primary")
        parameters["sequence_range"] = str(seq_raw.get("range") or "1-4")
    else:
        if hasattr(device_helper, "get_sequence"):
            try:
                seq = await device_helper.get_sequence(device)
                if seq is not None:
                    parameters["zone_sequence"] = int(seq)
            except Exception:
                pass
        if "zone_sequence" not in parameters:
            parameters["zone_sequence"] = int(device.get("znSeq", 0) or 0)
        seq_val = parameters["zone_sequence"]
        parameters["sequence_name"] = "Primary" if seq_val == 0 else f"Secondary #{seq_val}"
        parameters["sequence_range"] = f"{seq_val * 4 + 1}-{seq_val * 4 + 4}"

    # Preserve raw 4-slot `thmInfo` (including None entries) so slot 0..3 maps 1:1 to Zone 1..4
    raw_thm_info = device.get("thmInfo")
    if isinstance(raw_thm_info, list):
        parameters["thm_slots"] = [str(x) if x else None for x in raw_thm_info]
    else:
        parameters["thm_slots"] = []

    try:
        codes = await device_helper.get_thermostat_sync_codes(device)
        parameters["thermostat_sync_codes"] = list(codes or [])
    except Exception:
        parameters["thermostat_sync_codes"] = [x for x in parameters["thm_slots"] if x]

    try:
        btn = await device_helper.get_app_button(device)
        if isinstance(btn, dict):
            parameters["app_button_enabled"] = bool(btn.get("enabled"))
            parameters["app_button_activated"] = bool(btn.get("activated"))
            if btn.get("text"):
                parameters["app_button_text"] = btn["text"]
    except Exception:
        pass
    if "app_button_text" not in parameters and device.get("aButText"):
        parameters["app_button_text"] = str(device["aButText"])

    try:
        aux = await device_helper.get_aux_setpoint(device)
        if isinstance(aux, dict):
            if aux.get("target") is not None:
                parameters["aux_setpoint_target"] = aux["target"]
            if aux.get("temperature") is not None:
                parameters["aux_setpoint_temp"] = aux["temperature"]
            mode = aux.get("mode") or {}
            if isinstance(mode, dict) and mode.get("title"):
                parameters["aux_setpoint_mode"] = mode["title"]
    except Exception:
        pass
    if parameters.get("aux_setpoint_target") is None and device.get("dhwT") is not None:
        parameters["aux_setpoint_target"] = device["dhwT"]

    # Extract extended ZON-0600 hardware configuration & runtime fields from official API / local stream
    lt = device.get("local_telemetry") or {}
    parameters["zone_priority"] = lt.get("znInPri", device.get("znPrior", 9))
    parameters["demand_on"] = lt.get("znInDem", device.get("demOn", 0))
    parameters["aux_differential"] = device.get("auxDif", 8)
    parameters["aux_priority"] = device.get("auxPrior", 9)
    parameters["pmp1_set"] = device.get("pmp1Set", 0)
    parameters["pmp2_set"] = device.get("pmp2Set", 3)
    parameters["p1_post_purge"] = device.get("p1PP", 60)
    parameters["p2_post_purge"] = device.get("p2PP", 60)
    parameters["zn_post_purge"] = device.get("znPP", 60)
    parameters["dmd1_set"] = device.get("dmd1Set", 0)
    parameters["dmd2_set"] = device.get("dmd2Set", 2)
    parameters["dmd3_set"] = device.get("dmd3Set", 4)
    parameters["wwsd"] = device.get("wwsd", 150)
    parameters["four_pipe"] = bool(device.get("fourP", 0))
    parameters["exercise_time"] = device.get("exTm", 24)
    parameters["backlight"] = bool(device.get("bckLit", 1))
    parameters["auto_time"] = bool(device.get("autoTm", 1))
    parameters["timezone"] = lt.get("tz", device.get("tz", -3.5))
    parameters["thm_board_ver"] = str(lt.get("thmBVer", device.get("thmBVer", "0.00")))

    # Outdoor temperature if present on ZON-0600 (`temps.t2.actual` or local `out`)
    t2 = (device.get("temps") or {}).get("t2") or {}
    out_temp = lt.get("out") if lt.get("out") is not None else t2.get("actual")
    if out_temp is not None:
        try:
            parameters["temperature_outdoor"] = float(out_temp)
        except (TypeError, ValueError):
            pass

    return parameters


def wire_via_device_links(devices: dict[str, dict[str, Any]]) -> None:
    """Link child THM thermostats to their parent ZON controller and 1:1 slot-aligned zone number."""
    parent_for_thm: dict[str, tuple[str, str, int]] = {}
    for zon_id, zon_device in devices.items():
        dtype = (zon_device.get("deviceType") or "").upper()
        if dtype != DEVICE_TYPE_ZON:
            continue
        params = zon_device.get("parameters") or {}
        seq = int(params.get("zone_sequence", 0) or 0)
        zon_name = zon_device.get("name", zon_id)
        thm_slots = params.get("thm_slots") or params.get("thermostat_sync_codes") or []
        for idx, thm_sync in enumerate(thm_slots):
            if not thm_sync:
                continue
            zone_num = seq * 4 + idx + 1
            parent_for_thm[str(thm_sync)] = (zon_id, zon_name, zone_num)

    for thm_id, thm_device in devices.items():
        dtype = (thm_device.get("deviceType") or "").upper()
        if dtype != DEVICE_TYPE_THM:
            continue
        link = parent_for_thm.get(str(thm_id))
        if link is not None:
            thm_device["via_device_id"] = link[0]
            thm_device["parent_zone_name"] = link[1]
            thm_device["zone_number"] = link[2]


class SensorlinxCoordinator(QObject):
    """Coordinates authentication, device polling, and optimistic UI updates."""

    data_updated = Signal(dict)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    auth_failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None, scan_interval_sec: int = 30) -> None:
        super().__init__(parent)
        self.sensorlinx: Sensorlinx = Sensorlinx()
        self.is_demo: bool = False
        self.is_local: bool = False
        self.mode: str = "cloud"
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self._scan_interval = scan_interval_sec
        self.data: dict[str, Any] = {}
        self._overrides: dict[str, dict[str, tuple[Any, float]]] = {}
        self._refresh_lock = asyncio.Lock()

        self._timer = QTimer(self)
        self._timer.setInterval(self._scan_interval * 1000)
        self._timer.timeout.connect(self._on_timer_tick)

    def _on_timer_tick(self) -> None:
        asyncio.ensure_future(self.async_refresh())

    @property
    def override_ttl(self) -> float:
        return 5.0 if (self.is_demo or self.is_local) else max(2 * self._scan_interval, 120.0)

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        return getattr(value, "value", value)

    @classmethod
    def _values_match(cls, a: Any, b: Any) -> bool:
        na, nb = cls._normalize_value(a), cls._normalize_value(b)
        if (
            isinstance(na, (int, float))
            and not isinstance(na, bool)
            and isinstance(nb, (int, float))
            and not isinstance(nb, bool)
        ):
            return abs(float(na) - float(nb)) <= 0.1
        return na == nb

    def set_parameter_override(
        self, device_id: str, updates: dict[str, Any], ttl: Optional[float] = None
    ) -> None:
        """Hold just-written parameter values optimistically and emit instant UI update."""
        if ttl is None:
            ttl = self.override_ttl
        expires = time.monotonic() + ttl
        dev_overrides = self._overrides.setdefault(device_id, {})
        for key, value in updates.items():
            dev_overrides[key] = (value, expires)

        if self.data and "devices" in self.data and device_id in self.data["devices"]:
            params = self.data["devices"][device_id].get("parameters")
            if params is not None:
                for key, value in updates.items():
                    params[key] = value
                self.data_updated.emit(self.data)

    def _apply_overrides(self, devices: dict[str, dict[str, Any]]) -> None:
        now = time.monotonic()
        for device_id in list(self._overrides.keys()):
            keys = self._overrides[device_id]
            dev = devices.get(device_id)
            params = dev.get("parameters") if dev else None
            for key in list(keys.keys()):
                value, expires = keys[key]
                if now >= expires:
                    del keys[key]
                    continue
                if params is None:
                    continue
                if self._values_match(value, params.get(key)):
                    del keys[key]
                    continue
                params[key] = value
            if not keys:
                del self._overrides[device_id]

    async def start_local_mode(self, local_manager: Optional[LocalLanManager] = None) -> bool:
        """Switch to Offline Local LAN Mode (`LocalSensorlinxClient`) backed by TCP port 2000 XTEA streams."""
        await self.stop()
        self.is_demo = False
        self.is_local = True
        self.mode = "local"
        local_client = LocalSensorlinxClient()
        if local_manager is not None:
            local_client.sync_from_local_manager(local_manager)
        self.sensorlinx = local_client
        self.username = "local@lan.internal"
        self.password = "local"
        self.status_changed.emit("Starting Local LAN Mode (Direct TCP :2000 XTEA Stream, No Cloud)...")
        await self.sensorlinx.login(self.username, self.password)
        ok = await self.async_refresh()
        self._timer.start()
        return ok

    def on_local_lan_updated(self, local_manager: LocalLanManager) -> None:
        """When in Local LAN Mode, sync decoded hardware telemetry into LocalSensorlinxClient and refresh UI."""
        if not self.is_local or not isinstance(self.sensorlinx, LocalSensorlinxClient):
            return
        if self.sensorlinx.sync_from_local_manager(local_manager):
            asyncio.ensure_future(self.async_refresh())

    async def start_demo_mode(self) -> bool:
        """Switch to Demo / Simulation Mode using `DemoSensorlinxClient`."""
        await self.stop()
        self.is_demo = True
        self.is_local = False
        self.mode = "demo"
        self.sensorlinx = DemoSensorlinxClient()
        self.username = "demo@sensorlinx.local"
        self.password = "demo"
        self.status_changed.emit("Starting Demo / Simulation Mode...")
        await self.sensorlinx.login(self.username, self.password)
        ok = await self.async_refresh()
        self._timer.start()
        return ok

    async def start_live_mode(self, username: str, password: str) -> bool:
        """Authenticate with the live SensorLinx cloud API and begin polling."""
        await self.stop()
        self.is_demo = False
        self.is_local = False
        self.mode = "cloud"
        self.sensorlinx = Sensorlinx()
        self.username = username
        self.password = password
        self.status_changed.emit(f"Signing in to SensorLinx as {username}...")
        try:
            await self.sensorlinx.login(username, password)
        except InvalidCredentialsError as exc:
            self.auth_failed.emit("Invalid email or password. Please check your HBX SensorLinx credentials.")
            return False
        except (LoginTimeoutError, LoginError) as exc:
            self.auth_failed.emit(f"Login failed: {exc}")
            return False
        except Exception as exc:
            self.auth_failed.emit(f"Connection error: {exc}")
            return False

        ok = await self.async_refresh()
        if ok:
            self._timer.start()
        return ok

    async def sync_cloud_snapshot_into_local_mode(
        self, username: str, password: str, local_manager: Optional[LocalLanManager] = None
    ) -> bool:
        """One-shot fetch from official SensorLinx Cloud API to populate Local LAN Mode hardware snapshot."""
        self.status_changed.emit(f"Fetching hardware configuration & THM-0600 thermostats from SensorLinx Cloud as {username}...")
        cloud_client = Sensorlinx()
        try:
            await cloud_client.login(username, password)
            profile = await cloud_client.get_profile() or {}
            buildings = await cloud_client.get_buildings() or []
            raw_by_bldg: dict[str, list[dict[str, Any]]] = {}
            total_devs = 0
            for bldg in buildings:
                bid = bldg.get("id") or bldg.get("_id")
                if not bid:
                    continue
                b_devs = await cloud_client.get_devices(bid) or []
                raw_by_bldg[bid] = list(b_devs)
                total_devs += len(b_devs)
            save_cloud_snapshot(profile, buildings, raw_by_bldg)
            if isinstance(self.sensorlinx, LocalSensorlinxClient):
                self.sensorlinx.reload_state_from_snapshot()
                if local_manager is not None:
                    self.sensorlinx.sync_from_local_manager(local_manager)
            await self.async_refresh()
            self.status_changed.emit(
                f"Synced {total_devs} device(s) from SensorLinx Cloud into Local LAN Mode snapshot!"
            )
            return True
        except InvalidCredentialsError:
            self.auth_failed.emit("Invalid email or password when syncing cloud device configuration.")
            return False
        except Exception as exc:
            self.error_occurred.emit(f"Cloud snapshot sync failed: {exc}")
            return False
        finally:
            try:
                await cloud_client.close()
            except Exception:
                pass

    async def stop(self) -> None:
        """Stop background polling and close any active session."""
        self._timer.stop()
        self._overrides.clear()
        if self.sensorlinx is not None:
            try:
                await self.sensorlinx.close()
            except Exception:
                pass

    async def async_refresh(self) -> bool:
        """Fetch profile, buildings, devices, and weather from SensorLinx."""
        if self._refresh_lock.locked():
            return True

        async with self._refresh_lock:
            try:
                if not self.sensorlinx.is_logged_in:
                    if not (self.username and self.password):
                        return False
                    await self.sensorlinx.login(self.username, self.password)

                profile = await self.sensorlinx.get_profile()
                if not profile:
                    self.error_occurred.emit("Transient error fetching SensorLinx profile (will retry).")
                    return False

                buildings = await self.sensorlinx.get_buildings() or []
                devices: dict[str, dict[str, Any]] = {}
                raw_devices_by_building: dict[str, list[dict[str, Any]]] = {}

                for building in buildings:
                    building_id = building.get("id") or building.get("_id")
                    if not building_id:
                        continue
                    try:
                        building_devices = await self.sensorlinx.get_devices(building_id)
                    except Exception as exc:
                        _LOGGER.warning("Failed to get devices for building %s: %s", building_id, exc)
                        continue
                    if not building_devices:
                        continue
                    raw_devices_by_building[building_id] = list(building_devices)

                    for device in building_devices:
                        device_id = device.get("syncCode") or device.get("id") or device.get("_id")
                        if not device_id:
                            continue

                        dtype = (device.get("deviceType") or "").upper()
                        device_helper = device_for(self.sensorlinx, building_id, device)

                        parameters: dict[str, Any] = {}
                        try:
                            parameters["firmware_version"] = str(
                                await device_helper.get_firmware_version(device_info=device)
                            )
                        except Exception:
                            parameters["firmware_version"] = str(device.get("firmVer", "Unknown"))

                        parameters["device_type"] = dtype or "ECO"
                        if "local_telemetry" in device:
                            parameters["local_telemetry"] = dict(device["local_telemetry"])
                        if "local_ip" in device:
                            parameters["local_ip"] = device["local_ip"]

                        try:
                            if dtype == DEVICE_TYPE_THM and isinstance(device_helper, ThmDevice):
                                parameters.update(await extract_thm_parameters(device_helper, device))
                            elif dtype == DEVICE_TYPE_ZON and isinstance(device_helper, ZonDevice):
                                parameters.update(await extract_zon_parameters(device_helper, device))
                            else:
                                parameters.update(await extract_eco_parameters(device_helper, device))
                        except Exception as exc:
                            _LOGGER.warning("Parameter extract error on %s: %s", device_id, exc)

                        device["parameters"] = parameters
                        device["building_id"] = building_id
                        device["building_name"] = building.get("name", f"Building {building_id}")
                        devices[device_id] = device

                wire_via_device_links(devices)
                self._apply_overrides(devices)

                if not self.is_demo and not self.is_local and raw_devices_by_building:
                    save_cloud_snapshot(profile, buildings, raw_devices_by_building)

                weather: dict[str, Any] = {}
                for building in buildings:
                    building_id = building.get("id") or building.get("_id")
                    if not building_id:
                        continue
                    weather_helper = SensorlinxDevice(self.sensorlinx, building_id, "")
                    b_weather: dict[str, Any] = {}
                    try:
                        current = await weather_helper.get_current_weather(building_info=building)
                        if current:
                            b_weather["current"] = current
                    except Exception:
                        pass
                    try:
                        forecast = await weather_helper.get_forecast(building_info=building)
                        if forecast:
                            b_weather["forecast"] = forecast
                    except Exception:
                        pass
                    if b_weather:
                        weather[building_id] = b_weather

                self.data = {
                    "profile": profile,
                    "buildings": buildings,
                    "devices": devices,
                    "weather": weather,
                    "last_updated": time.strftime("%H:%M:%S"),
                    "is_demo": self.is_demo,
                    "is_local": self.is_local,
                    "mode": self.mode,
                }
                if self.is_local:
                    mode_tag = "LOCAL LAN (NO CLOUD)"
                elif self.is_demo:
                    mode_tag = "DEMO MODE"
                else:
                    mode_tag = "LIVE CLOUD"
                self.status_changed.emit(
                    f"[{mode_tag}] Connected • {len(buildings)} building(s), {len(devices)} device(s) • Updated {self.data['last_updated']}"
                )
                self.data_updated.emit(self.data)
                return True

            except InvalidCredentialsError as exc:
                self.auth_failed.emit(f"Authentication failed: {exc}")
                return False
            except Exception as exc:
                _LOGGER.exception("Error refreshing SensorLinx data: %s", exc)
                self.error_occurred.emit(f"Sync error: {exc}")
                return False

    def get_device_helper(self, device_id: str) -> Optional[SensorlinxDevice]:
        """Return the typed `pysensorlinx` device wrapper (`SensorlinxDevice`, `ThmDevice`, or `ZonDevice`)."""
        if not self.data or "devices" not in self.data:
            return None
        dev = self.data["devices"].get(device_id)
        if not dev:
            return None
        building_id = dev.get("building_id")
        if not building_id:
            return None
        return device_for(self.sensorlinx, building_id, dev)

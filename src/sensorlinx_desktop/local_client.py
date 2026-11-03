"""Offline Local LAN client for SensorLinx & HBX Controls (TCP Port 2000 XTEA Stream).

Builds an authentic local HBX system state backed strictly by the user's local controllers
(e.g., `192.168.1.50` -> `AECO-0001` ECO-0600 and `192.168.1.51` -> `AZON-0001` ZON-0600)
using the complete official API schema from `sslivins/pysensorlinx` and `sslivins/hass_hbxcontrols`
with zero fake demo thermostats or fake weather forecasts.

Also supports an optional Cloud-to-Local Hardware Snapshot (`~/.sensorlinx_local_snapshot.json`):
if the user syncs their device configuration from the official SensorLinx Cloud API once,
`LocalSensorlinxClient` preserves their real wired `THM-0600` thermostats, zone names, and
controller parameters offline while continuously overlaying the live 1.5-second Local LAN
TCP port 2000 XTEA telemetry (`out`, `stgS`, `numStg`, `revV`, `useBkUp`, `priBUp`, `secPmp`,
`znInPri`, `znInDem`, `version`, `thmBVer`, `SSID`, `tz`, and `RTC`).
"""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .demo_client import DemoSensorlinxClient
from .local_probe import LocalHostState, LocalLanManager

_LOGGER = logging.getLogger(__name__)

SNAPSHOT_PATH = Path.home() / ".sensorlinx_local_snapshot.json"

PUMP_MODE_NAMES = {
    0: "System",
    1: "Heating",
    2: "Cooling",
    3: "Aux / DHW",
    4: "App Button",
    5: "Disabled",
}

DEMAND_TYPE_INFO = {
    0: ("HD", "hd", "Heating Demand"),
    1: ("CD1", "cd", "Cooling 1 Demand"),
    2: ("CD2", "cd", "Cooling 2 Demand"),
    3: ("AUX", "aux", "Aux / DHW Demand"),
    4: ("APP", "app", "App Demand"),
    5: ("OFF", "off", "Disabled"),
}


def _format_rtc_from_telemetry(tel: Dict[str, Any]) -> str:
    """Format controller RTC clock & date from `{type:OK}` packet fields if present."""
    if all(k in tel for k in ("hrs", "mins", "secs")):
        try:
            hms = f"{int(tel['hrs']):02d}:{int(tel['mins']):02d}:{int(tel['secs']):02d}"
            if all(k in tel for k in ("year", "month", "days")):
                ymd = f"{int(tel['year']):04d}-{int(tel['month']):02d}-{int(tel['days']):02d}"
                tz = tel.get("tz")
                tz_str = f" (UTC{tz:+g})" if isinstance(tz, (int, float)) else ""
                return f"{ymd} {hms}{tz_str}"
            return hms
        except (TypeError, ValueError):
            pass
    return "Waiting for {type:OK} packet..."


def save_cloud_snapshot(
    profile: Dict[str, Any],
    buildings: List[Dict[str, Any]],
    devices_by_building: Dict[str, List[Dict[str, Any]]],
    path: Path = SNAPSHOT_PATH,
) -> bool:
    """Persist official SensorLinx Cloud API hardware definitions for offline Local LAN Mode."""
    try:
        clean_devs: Dict[str, List[Dict[str, Any]]] = {}
        for b_id, dev_list in devices_by_building.items():
            cleaned_list = []
            for d in dev_list:
                d_copy = copy.deepcopy(d)
                # Strip computed runtime parameters so raw API schema stays intact
                d_copy.pop("parameters", None)
                cleaned_list.append(d_copy)
            clean_devs[b_id] = cleaned_list

        payload = {
            "profile": profile,
            "buildings": buildings,
            "devices_by_building": clean_devs,
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return True
    except Exception as exc:
        _LOGGER.warning("Could not save cloud hardware snapshot to %s: %s", path, exc)
        return False


def load_cloud_snapshot(path: Path = SNAPSHOT_PATH) -> Optional[Dict[str, Any]]:
    """Load cached Cloud API hardware definitions if available."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "devices_by_building" in data:
            return data
    except Exception as exc:
        _LOGGER.warning("Failed to load cloud hardware snapshot from %s: %s", path, exc)
    return None


def _build_initial_local_state(snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a clean initial state with the real local LAN controllers using full official API schema."""
    eco_device: Dict[str, Any] = {
        "_id": "dev-aeco-0001",
        "id": "AECO-0001",
        "syncCode": "AECO-0001",
        "name": "ECO-0600 Hydronic Controller",
        "deviceType": "ECO",
        "firmVer": "2.08",
        "connected": False,
        "local_ip": "192.168.1.50",
        "local_telemetry": {
            "host": "192.168.1.50",
            "connected": False,
            "frames_received": 0,
            "bytes_received": 0,
        },
        # Official ECO-0600 configuration parameters (editable locally)
        "priority": 2,  # 0=Heat, 1=Cool, 2=Auto
        "permHD": False,
        "permCD": False,
        "htOR": False,
        "dot": 5,
        "mbt": 115,
        "dbt": 135,
        "htDif": 5,
        "wwsdOn": True,
        "wwsd": 68,
        "clOR": False,
        "cdot": 95,
        "mst": 55,
        "dst": 45,
        "clDif": 5,
        "cwsdOn": True,
        "cwsd": 50,
        "numStg": 1,
        "twoStg": False,
        "stgOnLag": 10,
        "stgOffLag": 15,
        "offStg": 0,
        "rotCyOn": False,
        "rotCy": 20,
        "rotTiOn": False,
        "rotTi": 48,
        "wwLag": 1,
        "hcSwDly": 60,
        "wideDiff": False,
        "bkLagOn": True,
        "bkLag": 30,
        "bkTempOn": True,
        "bkTemp": 20,
        "bkDifOn": True,
        "bkDif": 10,
        "bkOdOn": False,
        "bkOd": 5,
        "bkTkOn": False,
        "bkTk": 125,
        "dhwOn": False,
        "dhwT": 120,
        "auxDif": 5,
        # Live temperatures: outdoor probe (`t2`) is broadcast in `primaryinfo` (`out`)
        "temps": {
            "t1": {"title": "Tank", "actual": None, "target": 115},
            "t2": {"title": "Outdoor", "actual": None, "target": None},
            "t3": {"title": "DHW Tank", "actual": None, "target": 120},
        },
        "temperatures": [
            {
                "activated": False,
                "activatedColor": None,
                "activatedState": None,
                "current": None,
                "enabled": True,
                "target": None,
                "title": "Outdoor",
                "type": "outdoor",
                "priority": {"enabled": False, "title": "Heating", "type": "hot"},
            }
        ],
        "stages": [
            {"activated": False, "runTime": "OFF (Idle)", "title": "Stage 1"},
        ],
        "backup": {
            "activated": False,
            "enabled": True,
            "runTime": "Armed (Standby)",
            "title": "Backup Boiler",
        },
        "dhw": {"activated": False, "enabled": False, "title": "DHW"},
        "wsd": {
            "wwsd": {"activated": False, "enabled": True, "temperature": 68},
            "cwsd": {"activated": False, "enabled": True, "temperature": 50},
        },
        "demands": [
            {"activated": False, "name": "hd", "title": "Heat Demand"},
            {"activated": False, "name": "cd", "title": "Cool Demand"},
        ],
        "pumps": [
            {"activated": False, "mode": "secPmp=257", "title": "System / Secondary Pump"},
        ],
        "reversingValve": {"activated": False, "title": "Reversing Valve (revV=0: Heating)"},
    }

    # Complete ZON-0600 schema matching `device_zon_0600.json` from `pysensorlinx` / `hass_hbxcontrols`
    zon_device: Dict[str, Any] = {
        "_id": "dev-azon-0001",
        "id": "AZON-0001",
        "syncCode": "AZON-0001",
        "name": "ZON-0600 Zone Controller",
        "deviceType": "ZON",
        "firmVer": "1.45",
        "connected": False,
        "local_ip": "192.168.1.51",
        "local_telemetry": {
            "host": "192.168.1.51",
            "connected": False,
            "frames_received": 0,
            "bytes_received": 0,
        },
        "zoneId": 1,
        "znID": 1,
        "sequence": {"name": "Primary", "range": "1-4", "value": 0},
        "znSeq": 0,
        "znPrior": 9,
        "demOn": 0,
        "relayTypes": [1, 1, 1, 1],
        "relType": [1, 1, 1, 1],
        "relStat": [0] * 16,
        "relays": [False] * 16,
        # 4 zone thermostat slots (populated when synced from Cloud Snapshot)
        "thermostats": {},
        "thmInfo": [None, None, None, None],
        # Pump configuration matching official ZON-0600 schema
        "pmp1Set": 0,  # 0=System
        "pmp2Set": 3,  # 3=Aux / DHW
        "p1PP": 60,
        "p2PP": 60,
        "znPP": 60,
        "pumps": [
            {"activated": False, "mode": "System", "name": "pump1", "title": "Pump 1"},
            {"activated": False, "mode": "Aux / DHW", "name": "pump2", "title": "Pump 2"},
        ],
        # Fancoil outputs matching official ZON-0600 schema
        "fancoil": [
            {"activated": False, "name": "heating", "title": "Heating"},
            {"activated": False, "name": "cooling", "title": "Cooling"},
            {"activated": False, "name": "fan", "title": "Fan"},
            {"activated": False, "name": "humidity", "title": "Humidity"},
        ],
        # Demand channels matching official ZON-0600 schema
        "dmd1Set": 0,  # Heating (HD)
        "dmd2Set": 2,  # Cooling 2 (CD2)
        "dmd3Set": 4,  # App Demand (APP)
        "sDem1": 0,
        "sDem2": 0,
        "sDem3": 0,
        "sDel1": 0,
        "sDel2": 0,
        "dmdCom": 0,
        "dmpCom": 0,
        "demands": [
            {"abbr": "HD", "activated": False, "name": "demand1", "title": "Demand 1", "type": "hd"},
            {"abbr": "CD2", "activated": False, "name": "demand2", "title": "Demand 2", "type": "cd"},
            {"abbr": "APP", "activated": False, "name": "demand3", "title": "Demand 3", "type": "app"},
        ],
        # App Button (Relay 12) matching official ZON-0600 schema
        "aBut": 0,
        "aButText": "App Button",
        "appButton": {
            "activated": False,
            "enabled": True,
            "text": "App Button",
        },
        # Auxiliary Setpoint matching official ZON-0600 schema
        "dhwT": 120,
        "auxDif": 8,
        "auxPrior": 9,
        "auxMode": 0,
        "auxSetpoint": {
            "temperature": None,
            "target": 120,
            "mode": {"mode": 0, "title": "Auxiliary Setpoint"},
        },
        # Controller settings matching official ZON-0600 schema
        "wwsd": 150,
        "fourP": 0,
        "exTm": 24,
        "bckLit": 1,
        "autoTm": 1,
        "cOrF": 0,
        "therm": 1,
        "tz": -3.5,
        "thmBVer": "0.00",
        "temps": {
            "t2": {"title": "Outdoor", "actual": None, "target": None},
        },
    }

    devices_map: Dict[str, Dict[str, Any]] = {
        "AECO-0001": eco_device,
        "AZON-0001": zon_device,
    }

    building_name = "Local LAN Controllers"
    if snapshot and isinstance(snapshot.get("devices_by_building"), dict):
        for _b_id, snap_devs in snapshot["devices_by_building"].items():
            if not isinstance(snap_devs, list):
                continue
            for sdev in snap_devs:
                if not isinstance(sdev, dict):
                    continue
                scode = str(sdev.get("syncCode") or sdev.get("id") or "")
                dtype = str(sdev.get("deviceType") or "").upper()
                if not scode:
                    continue
                if dtype == "ECO" or scode.startswith("AECO"):
                    merged_eco = copy.deepcopy(eco_device)
                    merged_eco.update(copy.deepcopy(sdev))
                    merged_eco["local_ip"] = sdev.get("local_ip", "192.168.1.50")
                    merged_eco["local_telemetry"] = copy.deepcopy(eco_device["local_telemetry"])
                    devices_map.pop("AECO-0001", None)
                    devices_map[scode] = merged_eco
                elif dtype == "ZON" or scode.startswith("AZON"):
                    merged_zon = copy.deepcopy(zon_device)
                    merged_zon.update(copy.deepcopy(sdev))
                    merged_zon["local_ip"] = sdev.get("local_ip", "192.168.1.51")
                    merged_zon["local_telemetry"] = copy.deepcopy(zon_device["local_telemetry"])
                    devices_map.pop("AZON-0001", None)
                    devices_map[scode] = merged_zon
                elif dtype == "THM" or scode.startswith("ATHM"):
                    thm_copy = copy.deepcopy(sdev)
                    thm_copy["id"] = scode
                    thm_copy["syncCode"] = scode
                    devices_map[scode] = thm_copy

        snap_bldgs = snapshot.get("buildings") or []
        if snap_bldgs and isinstance(snap_bldgs[0], dict):
            b_title = snap_bldgs[0].get("name")
            if b_title:
                building_name = f"{b_title} (Local LAN :2000)"

    return {
        "profile": {
            "id": "local-lan-user",
            "email": "local@lan.internal",
            "firstName": "Local",
            "lastName": "LAN Mode",
        },
        "buildings": {
            "bldg-home-01": {
                "id": "bldg-home-01",
                "_id": "bldg-home-01",
                "name": building_name,
                "timezone": "America/St_Johns",
                "weather": {
                    "weather": {
                        "temp": None,
                        "feelsLike": None,
                        "min": None,
                        "max": None,
                        "humidity": None,
                        "pressure": None,
                        "wind": None,
                        "windDir": None,
                        "clouds": None,
                        "description": "Waiting for local XTEA frame on port 2000...",
                        "icon": "01d",
                    },
                    "forecast": [],
                },
            }
        },
        "devices": {
            "bldg-home-01": devices_map,
        },
    }


class LocalSensorlinxClient(DemoSensorlinxClient):
    """Local LAN replacement for `pysensorlinx.Sensorlinx` fed by `LocalLanManager`."""

    def __init__(self, snapshot_path: Path = SNAPSHOT_PATH) -> None:
        super().__init__()
        self._snapshot_path = snapshot_path
        self.has_cloud_snapshot: bool = False
        self._last_frame_counts: Dict[str, int] = {}
        self.reload_state_from_snapshot()
        self._demo_logged_in = True

    def reload_state_from_snapshot(self) -> bool:
        """Load cached Cloud API hardware snapshot if present and rebuild local state."""
        snap = load_cloud_snapshot(self._snapshot_path)
        self.has_cloud_snapshot = snap is not None
        self._state = _build_initial_local_state(snapshot=snap)
        self._last_frame_counts.clear()
        return self.has_cloud_snapshot

    def _extract_last_frame_text(self, st: LocalHostState) -> str:
        latest_ts = -1.0
        latest_txt = ""
        for ft in st.frame_types.values():
            if ft.last_decrypted_text and ft.last_received_ts >= latest_ts:
                latest_ts = ft.last_received_ts
                latest_txt = ft.last_decrypted_text
        return latest_txt

    def sync_from_local_manager(self, local_manager: LocalLanManager) -> bool:
        """Ingest live XTEA-decrypted telemetry from `LocalLanManager` into the local device state.

        Returns True whenever a new frame arrives or any connection/telemetry field changes.
        """
        changed = False
        bldg = self._state["buildings"]["bldg-home-01"]
        b_devs = self._state["devices"]["bldg-home-01"]

        for host, st in local_manager.states.items():
            prev_cnt = self._last_frame_counts.get(host, -1)
            if st.frames_received != prev_cnt:
                self._last_frame_counts[host] = st.frames_received
                changed = True

            tel = dict(st.decoded_telemetry)
            sync_code = str(tel.get("priCPU") or tel.get("syncCode") or "")
            out_val = tel.get("out")
            rtc_str = _format_rtc_from_telemetry(tel)
            last_txt = self._extract_last_frame_text(st)

            # Update outdoor temperature from live hardware probe
            if out_val is not None:
                try:
                    out_f = round(float(out_val), 2)
                    w_cur = bldg["weather"]["weather"]
                    if w_cur.get("temp") != out_f:
                        w_cur["temp"] = out_f
                        w_cur["feelsLike"] = out_f
                        w_cur["min"] = out_f
                        w_cur["max"] = out_f
                        changed = True
                    ssid = tel.get("SSID", "Local-IoT-LAN")
                    w_cur["description"] = (
                        f"Live Outdoor Probe ({sync_code or host}) • Wi-Fi: {ssid} • RTC: {rtc_str}"
                    )
                except (TypeError, ValueError):
                    pass

            # Update ECO-0600 controller
            if "stgS" in tel or sync_code.startswith("AECO") or "ECO" in st.inferred_device_role():
                eco_id = sync_code if sync_code.startswith("AECO") else ("AECO-0001" if "AECO-0001" in b_devs else "AECO-0001")
                if eco_id not in b_devs and "AECO-0001" in b_devs:
                    eco = b_devs.pop("AECO-0001")
                    eco["id"] = eco_id
                    eco["syncCode"] = eco_id
                    b_devs[eco_id] = eco
                eco = b_devs.get(eco_id)
                if eco is not None:
                    eco["connected"] = st.connected
                    eco["name"] = f"ECO-0600 ({eco_id} @ {host})"
                    if "version" in tel:
                        eco["firmVer"] = str(tel["version"])

                    if out_val is not None:
                        try:
                            out_f = round(float(out_val), 2)
                            eco.setdefault("temps", {}).setdefault(
                                "t2", {"title": "Outdoor", "actual": None, "target": None}
                            )["actual"] = out_f
                            if eco.get("temperatures"):
                                for t_entry in eco["temperatures"]:
                                    if t_entry.get("type") == "outdoor" or t_entry.get("title") == "Outdoor":
                                        t_entry["current"] = out_f
                        except (TypeError, ValueError):
                            pass

                    num_stg = max(1, int(tel.get("numStg", eco.get("numStg", 1))))
                    eco["numStg"] = num_stg
                    stg_active = bool(int(tel.get("stgS", 0)))
                    eco["stages"] = [
                        {
                            "activated": stg_active if i == 0 else False,
                            "runTime": "ON (Calling)" if (stg_active and i == 0) else "OFF (Idle)",
                            "title": f"Stage {i + 1}",
                        }
                        for i in range(num_stg)
                    ]

                    rev_val = int(tel.get("revV", 0))
                    rev_active = bool(rev_val)
                    eco["reversingValve"] = {
                        "activated": rev_active,
                        "title": f"Reversing Valve (revV={rev_val}: {'Cooling' if rev_active else 'Heating'})",
                    }

                    bk_en = bool(int(tel.get("useBkUp", 1)))
                    bk_act = bool(int(tel.get("priBUp", 0)))
                    eco["backup"] = {
                        "activated": bk_act,
                        "enabled": bk_en,
                        "runTime": "FIRING" if bk_act else ("Armed (Standby)" if bk_en else "Disabled"),
                        "title": "Backup Boiler",
                    }

                    sec_pmp = tel.get("secPmp")
                    if sec_pmp is not None:
                        sec_int = int(sec_pmp)
                        eco["pumps"] = [
                            {
                                "activated": stg_active or (sec_int > 257),
                                "mode": f"secPmp={sec_int}",
                                "title": "System / Secondary Pump",
                            }
                        ]

                    eco["demands"] = [
                        {
                            "activated": (stg_active and not rev_active) or bool(eco.get("permHD")),
                            "name": "hd",
                            "title": "Heat Demand",
                        },
                        {
                            "activated": (stg_active and rev_active) or bool(eco.get("permCD")),
                            "name": "cd",
                            "title": "Cool Demand",
                        },
                    ]

                    eco["local_telemetry"] = {
                        "host": host,
                        "connected": st.connected,
                        "frames_received": st.frames_received,
                        "bytes_received": st.bytes_received,
                        "priCPU": tel.get("priCPU", eco_id),
                        "syncCode": tel.get("syncCode", eco_id),
                        "version": tel.get("version", eco.get("firmVer", "—")),
                        "out": tel.get("out"),
                        "stgS": tel.get("stgS"),
                        "numStg": tel.get("numStg"),
                        "revV": tel.get("revV"),
                        "useBkUp": tel.get("useBkUp"),
                        "priBUp": tel.get("priBUp"),
                        "secPmp": tel.get("secPmp"),
                        "SSID": tel.get("SSID", "—"),
                        "tz": tel.get("tz"),
                        "rtc_str": rtc_str,
                        "last_decrypted_text": last_txt,
                    }

            # Update ZON-0600 controller
            if "znInPri" in tel or sync_code.startswith("AZON") or "ZON" in st.inferred_device_role():
                zon_id = sync_code if sync_code.startswith("AZON") else ("AZON-0001" if "AZON-0001" in b_devs else "AZON-0001")
                if zon_id not in b_devs and "AZON-0001" in b_devs:
                    zon = b_devs.pop("AZON-0001")
                    zon["id"] = zon_id
                    zon["syncCode"] = zon_id
                    b_devs[zon_id] = zon
                zon = b_devs.get(zon_id)
                if zon is not None:
                    zon["connected"] = st.connected
                    zon["name"] = f"ZON-0600 ({zon_id} @ {host})"
                    if "version" in tel:
                        zon["firmVer"] = str(tel["version"])
                    if "thmBVer" in tel:
                        zon["thmBVer"] = str(tel["thmBVer"])
                    if "tz" in tel:
                        zon["tz"] = tel["tz"]

                    if out_val is not None:
                        try:
                            out_f = round(float(out_val), 2)
                            zon.setdefault("temps", {}).setdefault(
                                "t2", {"title": "Outdoor", "actual": None, "target": None}
                            )["actual"] = out_f
                        except (TypeError, ValueError):
                            pass

                    dem_mask = int(tel.get("znInDem", zon.get("demOn", 0)) or 0)
                    zn_pri = int(tel.get("znInPri", zon.get("znPrior", 9)) or 9)
                    zon["demOn"] = dem_mask
                    zon["znPrior"] = zn_pri

                    # Preserve Relay 12 (App Button) while updating Zone 1..4 relays from znInDem
                    existing_relays = list(zon.get("relays") or [False] * 16)
                    if len(existing_relays) < 16:
                        existing_relays.extend([False] * (16 - len(existing_relays)))
                    app_btn_active = bool((zon.get("appButton") or {}).get("activated", existing_relays[11]))
                    for z_idx in range(4):
                        existing_relays[z_idx] = bool(dem_mask & (1 << z_idx))
                    existing_relays[11] = app_btn_active
                    zon["relays"] = existing_relays
                    zon["relStat"] = [1 if r else 0 for r in existing_relays]

                    pmp1_mode = PUMP_MODE_NAMES.get(int(zon.get("pmp1Set", 0) or 0), "System")
                    pmp2_mode = PUMP_MODE_NAMES.get(int(zon.get("pmp2Set", 3) or 3), "Aux / DHW")
                    zon["pumps"] = [
                        {
                            "activated": bool(dem_mask > 0),
                            "mode": pmp1_mode,
                            "name": "pump1",
                            "title": "Pump 1",
                        },
                        {
                            "activated": bool(app_btn_active and int(zon.get("pmp2Set", 3) or 3) == 4),
                            "mode": pmp2_mode,
                            "name": "pump2",
                            "title": "Pump 2",
                        },
                    ]

                    d1_abbr, d1_type, _ = DEMAND_TYPE_INFO.get(int(zon.get("dmd1Set", 0) or 0), ("HD", "hd", "Heating"))
                    d2_abbr, d2_type, _ = DEMAND_TYPE_INFO.get(int(zon.get("dmd2Set", 2) or 2), ("CD2", "cd", "Cooling 2"))
                    d3_abbr, d3_type, _ = DEMAND_TYPE_INFO.get(int(zon.get("dmd3Set", 4) or 4), ("APP", "app", "App"))
                    zon["demands"] = [
                        {
                            "abbr": d1_abbr,
                            "activated": bool(dem_mask > 0),
                            "name": "demand1",
                            "title": "Demand 1",
                            "type": d1_type,
                        },
                        {
                            "abbr": d2_abbr,
                            "activated": False,
                            "name": "demand2",
                            "title": "Demand 2",
                            "type": d2_type,
                        },
                        {
                            "abbr": d3_abbr,
                            "activated": app_btn_active,
                            "name": "demand3",
                            "title": "Demand 3",
                            "type": d3_type,
                        },
                    ]

                    zon["local_telemetry"] = {
                        "host": host,
                        "connected": st.connected,
                        "frames_received": st.frames_received,
                        "bytes_received": st.bytes_received,
                        "syncCode": tel.get("syncCode", zon_id),
                        "version": tel.get("version", zon.get("firmVer", "—")),
                        "thmBVer": tel.get("thmBVer", zon.get("thmBVer", "0.00")),
                        "znInPri": zn_pri,
                        "znInDem": dem_mask,
                        "out": tel.get("out"),
                        "SSID": tel.get("SSID", "—"),
                        "tz": tel.get("tz", zon.get("tz", -3.5)),
                        "rtc_str": rtc_str,
                        "last_decrypted_text": last_txt,
                    }

        return changed

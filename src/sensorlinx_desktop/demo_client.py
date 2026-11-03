"""Realistic in-memory Demo / Simulation client for SensorLinx & HBX Controls.

Subclasses `pysensorlinx.Sensorlinx` and intercepts `_authenticated_request` so that
all `SensorlinxDevice`, `ThmDevice`, and `ZonDevice` getters, setters, and parameter
validations from `pysensorlinx` run natively without touching live hardware.
"""
from __future__ import annotations

import copy
import datetime
from typing import Any, Dict, List, Optional
from pysensorlinx import Sensorlinx
from .models import OutdoorResetCurveConfig


def _build_initial_demo_state() -> Dict[str, Any]:
    """Create a rich, realistic multi-device HBX Controls home heating setup."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    forecast_list = []
    sample_conditions = [
        (38.5, 34.0, 41.2, 20, 0.0, "scattered clouds", "03d", 802),
        (33.2, 29.5, 36.0, 65, 1.2, "light snow", "13n", 600),
        (28.4, 24.0, 31.0, 80, 2.5, "snow", "13d", 601),
        (35.0, 31.0, 39.5, 15, 0.0, "few clouds", "02d", 801),
        (42.8, 38.0, 46.0, 10, 0.0, "clear sky", "01d", 800),
        (46.5, 41.2, 50.0, 30, 0.0, "broken clouds", "04d", 803),
    ]
    for i, (temp, tmin, tmax, pop, snow, desc, icon, wid) in enumerate(sample_conditions):
        period_time = (now_utc + datetime.timedelta(hours=3 * (i + 1))).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        forecast_list.append({
            "time": period_time,
            "pop": pop,
            "snow": snow,
            "temp": temp,
            "min": tmin,
            "max": tmax,
            "description": desc,
            "icon": icon,
            "weatherId": wid,
        })

    building = {
        "id": "bldg-home-01",
        "_id": "bldg-home-01",
        "name": "Main Residence (Demo)",
        "weather": {
            "weather": {
                "temp": 36.5,
                "feelsLike": 31.2,
                "min": 29.8,
                "max": 42.1,
                "pressure": 1018,
                "humidity": 68,
                "wind": 8.4,
                "windDir": 290,
                "clouds": 45,
                "snow": 0.0,
                "rain": 0.0,
                "type": "Clouds",
                "description": "scattered clouds",
                "icon": "03d",
                "weatherId": 802,
            },
            "forecast": forecast_list,
        },
    }

    eco_device = {
        "_id": "dev-eco-0982",
        "id": "AECO-0982",
        "syncCode": "AECO-0982",
        "building": "bldg-home-01",
        "name": "ECO-0600 Hydronic Plant",
        "deviceType": "ECO",
        "firmVer": "2.0.4",
        "production": {"pin": "8492"},
        "connected": True,
        # General & Priority
        "permHD": False,
        "permCD": False,
        "prior": 2,          # 0=heat, 1=cool, 2=auto
        "wwTime": 4,         # Weather shutdown lag time (hours)
        "hpSw": 120,         # Heat/cool switch delay (seconds)
        "wPDif": False,      # Wide priority differential
        # Staging & Rotation
        "numStg": 2,
        "twoS": False,
        "lagT": 10,          # Stage ON lag time (minutes)
        "lagOff": 15,        # Stage OFF lag time (seconds)
        "rotCy": 10,         # Rotate cycles (or 0='off')
        "rotTi": 48,         # Rotate time hours (or 0='off')
        "hpStg": False,      # Off staging (synchronized stage off)
        "stgRun": ["142:30", "138:15", "0:00", "0:00"],
        # Hot Tank & Outdoor Reset
        "wwsd": 68,          # Warm Weather Shutdown °F (32='off')
        "dot": -4,           # Hot Tank Outdoor Reset design temp °F (-41='off')
        "htDif": 6,          # Hot tank differential Δ°F
        "mbt": 85,           # Hot tank min temp °F (or target when reset off)
        "dbt": 135,          # Hot tank max temp °F
        # Cold Tank & Outdoor Reset
        "cwsd": 52,          # Cold Weather Shutdown °F (32='off')
        "cdot": 95,          # Cold Tank Outdoor Reset design temp °F (-41='off')
        "clDif": 8,          # Cold tank differential Δ°F
        "mst": 45,           # Cold tank min temp °F
        "dst": 58,           # Cold tank max temp °F
        # Backup Boiler
        "bkLag": 30,         # Backup lag time minutes (0='off')
        "bkTemp": 20,        # Backup outdoor temp threshold °F (0='off')
        "bkDif": 12,         # Backup differential Δ°F (0='off')
        "bkOd": 5,           # Backup only outdoor temp °F (-41='off')
        "bkTk": 125,         # Backup only tank temp °F (32='off')
        "bkRun": "18:45",
        # DHW
        "dhwOn": True,
        "dhwT": 122,
        "auxDif": 5,
        # Pumps & Runtime state
        "pmp1Set": 1,        # heating
        "pmp2Set": 3,        # dhw
        "pumps": [
            {"activated": True, "title": "Pump 1"},
            {"activated": False, "title": "Pump 2"},
        ],
        "reversingValve": {"activated": False, "title": "Reversing Valve"},
        "wsd": {
            "wwsd": {"activated": False, "title": "WWSD"},
            "cwsd": {"activated": False, "title": "CWSD"},
        },
        "demands": [
            {"name": "hd", "title": "Heat", "enabled": True, "activated": True},
            {"name": "cd", "title": "Cool", "enabled": True, "activated": False},
            {"name": "dhw", "title": "DHW", "enabled": True, "activated": False},
        ],
        "stages": [
            {"activated": True, "device": "AECO-0982", "enabled": True, "index": 1, "runTime": "142:30", "title": "Stage 1"},
            {"activated": False, "device": "AECO-0982", "enabled": True, "index": 2, "runTime": "138:15", "title": "Stage 2"},
        ],
        "backup": {"activated": False, "enabled": True, "runTime": "18:45", "title": "Backup Boiler"},
        "temps": {
            "t1": {"title": "Tank", "actual": 108.4, "target": 111.4},
            "t2": {"title": "Outdoor", "actual": 36.5, "target": None},
            "t3": {"title": "DHW Tank", "actual": 120.8, "target": 122.0},
        },
        "temperatures": [
            {
                "activated": True,
                "activatedColor": "orange",
                "activatedState": "heating",
                "current": 108.4,
                "enabled": True,
                "target": 111.4,
                "title": "Tank",
                "type": "single",
                "priority": {"enabled": True, "title": "Heating", "type": "hot"},
            },
            {
                "activated": False,
                "activatedColor": None,
                "activatedState": None,
                "current": 36.5,
                "enabled": True,
                "target": None,
                "title": "Outdoor",
                "type": "outdoor",
                "priority": {"enabled": False, "title": "Heating", "type": "hot"},
            },
            {
                "activated": False,
                "activatedColor": "green",
                "activatedState": "satisfied",
                "current": 120.8,
                "enabled": True,
                "target": 122.0,
                "title": "DHW Tank",
                "type": "dhw",
                "priority": {"enabled": False, "title": "Heating", "type": "hot"},
            },
        ],
    }

    zon_device = {
        "_id": "dev-zon-0224",
        "id": "AZON-0224",
        "syncCode": "AZON-0224",
        "building": "bldg-home-01",
        "name": "Main Floor Zone Controller",
        "deviceType": "ZON",
        "firmVer": "1.32",
        "production": {"pin": "3104"},
        "connected": True,
        "znID": 24,
        "znSeq": 0,
        "sequence": {"value": 0, "name": "Primary", "range": "1-4"},
        "relType": [1, 1, 1, 0],
        "relays": [True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
        "thmInfo": ["ATHM-4304", "ATHM-2625", "ATHM-4316", None],
        "aBut": 0,
        "aButText": "Snow Melt / Aux Loop",
        "appButton": {
            "enabled": True,
            "activated": False,
            "text": "Snow Melt / Aux Loop",
        },
        "dhwT": 115,
        "auxSetpoint": {
            "temperature": 112.5,
            "target": 115,
            "mode": {"title": "Auxiliary Setpoint", "value": 0},
            "hasTarget": True,
        },
        "fancoil": [
            {"enabled": True, "activated": True, "title": "Heating", "key": "heating"},
            {"enabled": True, "activated": False, "title": "Cooling", "key": "cooling"},
            {"enabled": True, "activated": False, "title": "Fan", "key": "fan"},
            {"enabled": True, "activated": False, "title": "Humidity", "key": "humidity"},
        ],
        "pumps": [
            {"enabled": True, "activated": True, "title": "Zone Pump 1 (Heat)", "value": 1, "key": "pump1"},
            {"enabled": True, "activated": False, "title": "Zone Pump 2 (Aux)", "value": 3, "key": "pump2"},
        ],
        "demands": [
            {"enabled": True, "activated": True, "type": "hd", "abbr": "HD", "title": "Low Temp Heat", "key": "demand1"},
            {"enabled": True, "activated": False, "type": "cd2", "abbr": "CD2", "title": "Cool Stage 2", "key": "demand2"},
            {"enabled": True, "activated": False, "type": "app", "abbr": "APP", "title": "App Button", "key": "demand3"},
        ],
    }

    def _make_thm(
        sync_code: str,
        name: str,
        room_f: float,
        floor_f: Optional[float],
        humidity: float,
        cng_ovr: int,
        heat_sp: int,
        cool_sp: int,
        away: int = 0,
        away_heat: int = 60,
        away_cool: int = 80,
        fan_mode: int = 0,
        pgmble: int = 1,
        use_hum: int = 2,
        hum_target: int = 42,
        dmd_bits: int = 0,
        thm_mode_title: str = "Air + Floor",
    ) -> Dict[str, Any]:
        thm = {
            "_id": f"dev-{sync_code.lower()}",
            "id": sync_code,
            "syncCode": sync_code,
            "building": "bldg-home-01",
            "name": name,
            "deviceType": "THM",
            "firmVer": "1.22",
            "production": {"pin": "5510"},
            "connected": True,
            "rm": room_f,
            "flr": floor_f,
            "hm": humidity,
            "cngOvr": cng_ovr,  # 0=auto, 1=heat, 2=cool, 3=off
            "rmT": heat_sp,
            "rmCT": cool_sp,
            "away": away,
            "hRmT": away_heat,
            "hRmCT": away_cool,
            "fnMode": fan_mode,  # 0=off, 1=on, 2=intermittent
            "pgmble": pgmble,
            "useHum": use_hum,   # 0=off, 1=on, 2=auto
            "hmT": hum_target,
            "dmd": dmd_bits,     # 0x02=heat, 0x40=cool, 0x80=fan
            "thmMode": {"title": thm_mode_title, "value": 0},
            "schedules": [
                {"key": "wkd1", "type": "Weekday", "title": "Morning", "cool": 75, "heat": 70, "time": 24, "timeFormatted": "06:00 AM"},
                {"key": "wkd2", "type": "Weekday", "title": "Daytime", "cool": 77, "heat": 68, "time": 32, "timeFormatted": "08:00 AM"},
                {"key": "wkd3", "type": "Weekday", "title": "Evening", "cool": 74, "heat": 71, "time": 72, "timeFormatted": "06:00 PM"},
                {"key": "wkd4", "type": "Weekday", "title": "Night", "cool": 73, "heat": 66, "time": 88, "timeFormatted": "10:00 PM"},
                {"key": "wke1", "type": "Weekend", "title": "Morning", "cool": 75, "heat": 71, "time": 28, "timeFormatted": "07:00 AM"},
                {"key": "wke2", "type": "Weekend", "title": "Night", "cool": 73, "heat": 66, "time": 92, "timeFormatted": "11:00 PM"},
            ],
        }
        _sync_thm_derived_fields(thm)
        return thm

    thm_living = _make_thm(
        sync_code="ATHM-4304",
        name="Living Room (Zone 1)",
        room_f=69.2,
        floor_f=72.8,
        humidity=41.5,
        cng_ovr=0,     # Auto
        heat_sp=71,
        cool_sp=76,
        away=0,
        away_heat=62,
        away_cool=80,
        fan_mode=0,
        pgmble=1,
        use_hum=2,
        hum_target=45,
        dmd_bits=0x02,  # Heating active
        thm_mode_title="Air + Floor",
    )

    thm_master = _make_thm(
        sync_code="ATHM-2625",
        name="Master Suite (Zone 2)",
        room_f=68.5,
        floor_f=70.1,
        humidity=39.0,
        cng_ovr=1,     # Heat
        heat_sp=68,
        cool_sp=74,
        away=0,
        away_heat=60,
        away_cool=78,
        fan_mode=0,
        pgmble=1,
        use_hum=0,
        hum_target=40,
        dmd_bits=0,
        thm_mode_title="Air + Floor",
    )

    thm_garage = _make_thm(
        sync_code="ATHM-4316",
        name="Garage / Workshop (Zone 3)",
        room_f=56.2,
        floor_f=50.5,
        humidity=33.2,
        cng_ovr=1,     # Heat
        heat_sp=55,
        cool_sp=80,
        away=0,
        away_heat=50,
        away_cool=90,
        fan_mode=0,
        pgmble=0,
        use_hum=0,
        hum_target=40,
        dmd_bits=0,
        thm_mode_title="Floor",
    )

    return {
        "profile": {
            "id": "demo-user-01",
            "email": "demo@sensorlinx.local",
            "firstName": "Demo",
            "lastName": "Homeowner",
        },
        "buildings": {
            "bldg-home-01": building,
        },
        "devices": {
            "bldg-home-01": {
                "AECO-0982": eco_device,
                "AZON-0224": zon_device,
                "ATHM-4304": thm_living,
                "ATHM-2625": thm_master,
                "ATHM-4316": thm_garage,
            }
        },
    }


def _sync_eco_derived_fields(eco: Dict[str, Any], outdoor_temp_f: float) -> None:
    """Recompute ECO derived blocks (`temps`, `temperatures`, `stages`, `wsd`, `demands`) after any parameter write."""
    dot = eco.get("dot", -41)
    wwsd = eco.get("wwsd", 32)
    cwsd = eco.get("cwsd", 32)
    mbt = float(eco.get("mbt", 85))
    dbt = float(eco.get("dbt", 135))
    ht_dif = float(eco.get("htDif", 6))

    curve = OutdoorResetCurveConfig(
        hot_reset_enabled=(dot != -41),
        hot_design_outdoor_f=float(dot if dot != -41 else 0),
        hot_wwsd_enabled=(wwsd != 32),
        hot_wwsd_f=float(wwsd if wwsd != 32 else 70),
        hot_min_tank_f=mbt,
        hot_max_tank_f=dbt,
        hot_differential_f=ht_dif,
        cold_reset_enabled=(eco.get("cdot", -41) != -41),
        cold_design_outdoor_f=float(eco.get("cdot", 95) if eco.get("cdot", -41) != -41 else 95),
        cold_cwsd_enabled=(cwsd != 32),
        cold_cwsd_f=float(cwsd if cwsd != 32 else 55),
        cold_min_tank_f=float(eco.get("mst", 45)),
        cold_max_tank_f=float(eco.get("dst", 58)),
        cold_differential_f=float(eco.get("clDif", 8)),
    )

    prior = eco.get("prior", 2)  # 0=heat, 1=cool, 2=auto
    if prior == 1:
        target_f = round(curve.compute_cold_target_f(outdoor_temp_f) or float(eco.get("mst", 45)), 1)
    else:
        target_f = round(curve.compute_hot_target_f(outdoor_temp_f) or mbt, 1)

    wwsd_active = (wwsd != 32) and (outdoor_temp_f >= float(wwsd))
    cwsd_active = (cwsd != 32) and (outdoor_temp_f <= float(cwsd))
    eco["wsd"] = {
        "wwsd": {"activated": wwsd_active, "title": "WWSD"},
        "cwsd": {"activated": cwsd_active, "title": "CWSD"},
    }

    tank_actual = eco["temps"]["t1"]["actual"]
    eco["temps"]["t1"]["target"] = target_f
    eco["temps"]["t2"]["actual"] = round(outdoor_temp_f, 1)
    eco["temps"]["t3"]["target"] = float(eco.get("dhwT", 122))

    for t_entry in eco.get("temperatures", []):
        if t_entry.get("title") == "Tank":
            t_entry["target"] = target_f
            t_entry["current"] = tank_actual
        elif t_entry.get("title") == "Outdoor":
            t_entry["current"] = round(outdoor_temp_f, 1)
        elif t_entry.get("title") == "DHW Tank":
            t_entry["target"] = float(eco.get("dhwT", 122))

    # Update stages list length to match numStg
    num_stg = int(eco.get("numStg", 2))
    stg_runs = eco.get("stgRun", ["142:30", "138:15", "12:10", "5:00"])
    while len(stg_runs) < 4:
        stg_runs.append("0:00")
    eco["stgRun"] = stg_runs

    heat_calling = (not wwsd_active) and (
        bool(eco.get("permHD")) or (prior in (0, 2) and tank_actual < target_f - ht_dif / 2.0)
    )
    cool_calling = (not cwsd_active) and bool(eco.get("permCD"))

    stages = []
    for i in range(num_stg):
        stages.append({
            "activated": bool(i == 0 and (heat_calling or cool_calling)),
            "device": eco["syncCode"],
            "enabled": True,
            "index": i + 1,
            "runTime": stg_runs[i],
            "title": f"Stage {i + 1}",
        })
    eco["stages"] = stages

    # Backup state
    bk_od = eco.get("bkOd", -41)
    bk_temp = eco.get("bkTemp", 0)
    bk_enabled = (bk_od != -41) or (bk_temp != 0) or (eco.get("bkLag", 0) != 0) or (eco.get("bkDif", 0) != 0)
    bk_active = (not wwsd_active) and (
        (bk_od != -41 and outdoor_temp_f <= float(bk_od))
        or (bk_temp != 0 and outdoor_temp_f <= float(bk_temp) and heat_calling)
    )
    eco["backup"] = {
        "activated": bk_active,
        "enabled": bk_enabled,
        "runTime": eco.get("bkRun", "18:45"),
        "title": "Backup Boiler",
    }

    dhw_on = bool(eco.get("dhwOn", True))
    dhw_actual = eco["temps"]["t3"]["actual"]
    dhw_target = float(eco.get("dhwT", 122))
    dhw_dif = float(eco.get("auxDif", 5))
    dhw_calling = dhw_on and (dhw_actual <= dhw_target - dhw_dif)

    eco["demands"] = [
        {"name": "hd", "title": "Heat", "enabled": True, "activated": heat_calling or bool(eco.get("permHD"))},
        {"name": "cd", "title": "Cool", "enabled": True, "activated": cool_calling or bool(eco.get("permCD"))},
        {"name": "dhw", "title": "DHW", "enabled": dhw_on, "activated": dhw_calling},
    ]


def _sync_thm_derived_fields(thm: Dict[str, Any]) -> None:
    """Synchronize THM nested read-side blocks with raw scalar fields after PATCH."""
    cng = int(thm.get("cngOvr", 0))  # 0=auto, 1=heat, 2=cool, 3=off
    key_map = {0: "auto", 1: "heat", 2: "cool", 3: "off"}
    active_key = key_map.get(cng, "auto")

    thm["changeover"] = [
        {"enabled": True, "activated": (active_key == "auto"), "title": "Auto", "key": "auto", "pgm": 0},
        {"enabled": True, "activated": (active_key == "heat"), "title": "Heat", "key": "heat", "pgm": 0},
        {"enabled": True, "activated": (active_key == "cool"), "title": "Cool", "key": "cool", "pgm": 0},
        {"enabled": True, "activated": (active_key == "off"), "title": "Off", "key": "off", "pgm": 0},
    ]

    fn_mode = int(thm.get("fnMode", 0))
    fn_key_map = {0: "off", 1: "on", 2: "intermittent"}
    active_fn = fn_key_map.get(fn_mode, "off")
    thm["fanModes"] = [
        {"enabled": True, "activated": (active_fn == "off"), "title": "Off", "key": "off"},
        {"enabled": True, "activated": (active_fn == "on"), "title": "On", "key": "on"},
        {"enabled": True, "activated": (active_fn == "intermittent"), "title": "Intermittent", "key": "intermittent"},
    ]

    away_on = bool(thm.get("away", 0))
    away_heat = int(thm.get("hRmT", 55))
    away_cool = int(thm.get("hRmCT", 82))
    thm["awayMode"] = {
        "title": "Away",
        "activated": away_on,
        "pgm": 0,
        "heatTarget": {"enabled": True, "value": away_heat},
        "coolTarget": {"enabled": True, "value": away_cool},
    }

    rm_temp = float(thm.get("rm", 68.0))
    heat_sp = away_heat if away_on else int(thm.get("rmT", 68))
    cool_sp = away_cool if away_on else int(thm.get("rmCT", 75))

    is_off = (active_key == "off")
    target_type = "cooling" if active_key == "cool" else "heat"
    target_val = cool_sp if active_key == "cool" else heat_sp
    thm["target"] = {
        "type": target_type,
        "value": target_val,
        "label": "Target",
        "isOff": is_off,
    }
    thm["temperature"] = {
        "type": "room",
        "value": rm_temp,
        "label": "Room",
    }

    # Demand bitfield calculation
    dmd = 0
    if not is_off:
        if active_key in ("auto", "heat") and rm_temp < heat_sp - 0.3:
            dmd |= 0x02
        elif active_key in ("auto", "cool") and rm_temp > cool_sp + 0.3:
            dmd |= 0x40
    if active_fn == "on":
        dmd |= 0x80
    thm["dmd"] = dmd
    thm["isHeating"] = bool(dmd & 0x02)
    thm["isCooling"] = bool(dmd & 0x40)
    thm["demands"] = [
        {"enabled": True, "activated": bool(dmd & 0x02), "title": "Heating", "key": "heating"},
        {"enabled": True, "activated": bool(dmd & 0x40), "title": "Cooling", "key": "cooling"},
        {"enabled": True, "activated": bool(dmd & 0x80), "title": "Fan", "key": "fan"},
        {"enabled": True, "activated": (thm.get("useHum", 0) > 0), "title": "Humidity", "key": "humidity"},
        {"enabled": True, "activated": (dmd == 0), "title": "Satisfied", "key": "satisfied"},
    ]


def _sync_zon_derived_fields(zon: Dict[str, Any], building_devices: Dict[str, Dict[str, Any]]) -> None:
    """Synchronize ZON relays, appButton, and auxSetpoint with linked THM demands and raw fields."""
    abut = bool(zon.get("aBut", 0))
    zon["appButton"] = {
        "enabled": True,
        "activated": abut,
        "text": zon.get("aButText", "App Button"),
    }
    zon["auxSetpoint"] = {
        "temperature": 112.5,
        "target": int(zon.get("dhwT", 115)),
        "mode": {"title": "Auxiliary Setpoint", "value": 0},
        "hasTarget": True,
    }

    relays = list(zon.get("relays") or [False] * 16)
    while len(relays) < 16:
        relays.append(False)

    thm_codes = zon.get("thmInfo") or []
    any_heat = False
    for idx, code in enumerate(thm_codes):
        if idx < 4 and code and code in building_devices:
            thm = building_devices[code]
            calling = bool(thm.get("dmd", 0) & (0x02 | 0x40))
            relays[idx] = calling
            if calling:
                any_heat = True
    # Relay 11 (12th element) mirrors app button per pysensorlinx ZON-0600 documentation
    relays[11] = abut
    zon["relays"] = relays

    for d in zon.get("demands", []):
        if d.get("type") == "hd":
            d["activated"] = any_heat
        elif d.get("type") == "app":
            d["activated"] = abut


class DemoSensorlinxClient(Sensorlinx):
    """Drop-in Demo / Simulation replacement for `pysensorlinx.Sensorlinx`."""

    def __init__(self) -> None:
        super().__init__()
        self._state = _build_initial_demo_state()
        self._demo_logged_in = True

    @property
    def is_logged_in(self) -> bool:
        return self._demo_logged_in

    async def login(self, username: str = None, password: str = None) -> None:
        self._username = username or "demo@sensorlinx.local"
        self._password = password or "demo"
        self._demo_logged_in = True

    async def close(self) -> None:
        self._demo_logged_in = False

    def set_simulated_outdoor_temp(self, temp_f: float) -> None:
        """Update the simulated outdoor temperature in Demo Mode and recompute curves."""
        bldg = self._state["buildings"]["bldg-home-01"]
        bldg["weather"]["weather"]["temp"] = round(temp_f, 1)
        bldg["weather"]["weather"]["feelsLike"] = round(temp_f - 4.0, 1)
        eco = self._state["devices"]["bldg-home-01"]["AECO-0982"]
        _sync_eco_derived_fields(eco, temp_f)

    def set_simulated_room_temp(self, device_id: str, temp_f: float) -> None:
        """Update a THM thermostat's simulated room temperature in Demo Mode."""
        devs = self._state["devices"]["bldg-home-01"]
        if device_id in devs and devs[device_id].get("deviceType") == "THM":
            devs[device_id]["rm"] = round(temp_f, 1)
            _sync_thm_derived_fields(devs[device_id])
            if "AZON-0224" in devs:
                _sync_zon_derived_fields(devs["AZON-0224"], devs)

    async def _authenticated_request(self, method: str, url: str, *, retry_on_401: bool = True, **kwargs) -> Any:
        """Intercept all Sensorlinx HTTP requests and serve/mutate in-memory demo state."""
        path = url.replace("https://mobile.sensorlinx.co/", "").strip("/")
        parts = path.split("/")

        # GET account/me
        if method.upper() == "GET" and path == "account/me":
            return copy.deepcopy(self._state["profile"])

        # GET buildings or buildings/{building_id}
        if method.upper() == "GET" and parts[0] == "buildings" and len(parts) == 1:
            return copy.deepcopy(list(self._state["buildings"].values()))

        if method.upper() == "GET" and parts[0] == "buildings" and len(parts) == 2:
            b_id = parts[1]
            return copy.deepcopy(self._state["buildings"].get(b_id))

        # GET buildings/{building_id}/devices or buildings/{building_id}/devices/{device_id}
        if method.upper() == "GET" and len(parts) >= 3 and parts[0] == "buildings" and parts[2] == "devices":
            b_id = parts[1]
            b_devs = self._state["devices"].get(b_id, {})
            if len(parts) == 3:
                return copy.deepcopy(list(b_devs.values()))
            dev_id = parts[3]
            return copy.deepcopy(b_devs.get(dev_id))

        # PATCH buildings/{building_id}/devices/{device_id}
        if method.upper() == "PATCH" and len(parts) == 4 and parts[0] == "buildings" and parts[2] == "devices":
            b_id = parts[1]
            dev_id = parts[3]
            payload = kwargs.get("json") or {}
            b_devs = self._state["devices"].get(b_id, {})
            if dev_id not in b_devs:
                raise RuntimeError(f"Demo device {dev_id} not found in building {b_id}")
            target_dev = b_devs[dev_id]
            target_dev.update(payload)

            dtype = (target_dev.get("deviceType") or "").upper()
            if dtype == "ECO":
                outdoor_f = self._state["buildings"][b_id]["weather"]["weather"]["temp"]
                _sync_eco_derived_fields(target_dev, outdoor_f)
            elif dtype == "THM":
                _sync_thm_derived_fields(target_dev)
                if "AZON-0224" in b_devs:
                    _sync_zon_derived_fields(b_devs["AZON-0224"], b_devs)
            elif dtype == "ZON":
                _sync_zon_derived_fields(target_dev, b_devs)

            return copy.deepcopy(target_dev)

        raise RuntimeError(f"Unhandled demo endpoint: {method} {url}")

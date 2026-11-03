"""Comprehensive unit & GUI tests for SensorLinx Desktop Control."""

from __future__ import annotations

import os
import pytest
from pysensorlinx import SensorlinxDevice, Temperature, ThmDevice, ZonDevice

# Force offscreen Qt rendering for automated test execution across Windows/Linux
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from sensorlinx_desktop.config import AppConfig
from sensorlinx_desktop.coordinator import SensorlinxCoordinator
from sensorlinx_desktop.demo_client import DemoSensorlinxClient
from sensorlinx_desktop.local_probe import (
    LocalLanManager,
    parse_delimited_frames,
    parse_hbx_pseudo_json,
    xtea_decrypt,
    xtea_encrypt,
)
from sensorlinx_desktop.main_window import MainWindow
from sensorlinx_desktop.models import OutdoorResetCurveConfig, UnitHelper
from sensorlinx_desktop.widgets.outdoor_reset_chart import OutdoorResetChartWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_unit_helper_conversions():
    assert UnitHelper.f_to_display(68.0, "F") == 68.0
    assert UnitHelper.display_to_f(68.0, "F") == 68.0
    assert UnitHelper.delta_f_to_display(9.0, "F") == 9.0
    assert UnitHelper.display_to_delta_f(9.0, "F") == 9.0

    assert UnitHelper.f_to_display(32.0, "C") == pytest.approx(0.0)
    assert UnitHelper.f_to_display(68.0, "C") == pytest.approx(20.0)
    assert UnitHelper.display_to_f(20.0, "C") == pytest.approx(68.0)
    # TemperatureDelta must scale by 5/9 or 9/5 without +32 offset
    assert UnitHelper.delta_f_to_display(9.0, "C") == pytest.approx(5.0)
    assert UnitHelper.display_to_delta_f(5.0, "C") == pytest.approx(9.0)
    assert UnitHelper.format_temp(68.0, "C", decimals=1) == "20.0°C"
    assert UnitHelper.format_delta(9.0, "C", decimals=1) == "5.0Δ°C"


def test_outdoor_reset_curve_calculations():
    curve = OutdoorResetCurveConfig(
        hot_reset_enabled=True,
        hot_design_outdoor_f=5.0,
        hot_wwsd_enabled=True,
        hot_wwsd_f=60.0,
        hot_min_tank_f=85.0,
        hot_max_tank_f=135.0,
        hot_differential_f=4.0,
        cold_reset_enabled=True,
        cold_design_outdoor_f=95.0,
        cold_cwsd_enabled=True,
        cold_cwsd_f=70.0,
        cold_min_tank_f=45.0,
        cold_max_tank_f=58.0,
        cold_differential_f=4.0,
    )

    # At design outdoor (5°F), hot target should be max temp (135°F)
    assert curve.compute_hot_target_f(5.0) == pytest.approx(135.0)
    # Below design outdoor (-10°F), clamped to max temp (135°F)
    assert curve.compute_hot_target_f(-10.0) == pytest.approx(135.0)
    # At warm anchor (60°F), hot target should be min temp (85°F)
    assert curve.compute_hot_target_f(60.0) == pytest.approx(85.0)
    # Above warm anchor (70°F), clamped to min temp (85°F)
    assert curve.compute_hot_target_f(70.0) == pytest.approx(85.0)
    # Midpoint (32.5°F) -> midpoint of 135 and 85 = 110°F
    assert curve.compute_hot_target_f(32.5) == pytest.approx(110.0)

    # Cooling curve checks
    assert curve.compute_cold_target_f(70.0) == pytest.approx(58.0)
    assert curve.compute_cold_target_f(95.0) == pytest.approx(45.0)
    assert curve.compute_cold_target_f(82.5) == pytest.approx(51.5)


@pytest.mark.asyncio
async def test_demo_coordinator_polling_and_writes():
    coord = SensorlinxCoordinator()
    ok = await coord.start_demo_mode()

    try:
        assert ok is True
        assert coord.is_demo is True
        devices = coord.data["devices"]
        assert "AECO-0982" in devices
        assert "AZON-0224" in devices
        assert "ATHM-4304" in devices
        assert "ATHM-2625" in devices
        assert "ATHM-4316" in devices

        # Verify parent ZON -> child THM link wiring
        assert devices["ATHM-4304"]["via_device_id"] == "AZON-0224"
        assert devices["ATHM-2625"]["via_device_id"] == "AZON-0224"

        # Verify ECO parameter extraction
        eco_params = devices["AECO-0982"]["parameters"]
        assert eco_params["hot_tank_outdoor_reset"].value == -4
        assert eco_params["hot_tank_max_temp"].value == 135
        assert eco_params["hot_tank_min_temp"].value == 85

        # Test ECO write via device helper: update hot tank max temp
        eco_helper = coord.get_device_helper("AECO-0982")
        assert isinstance(eco_helper, SensorlinxDevice)
        await eco_helper.set_hot_tank_max_temp(Temperature(142, "F"))
        await coord.async_refresh()
        assert coord.data["devices"]["AECO-0982"]["parameters"]["hot_tank_max_temp"].value == 142

        # Test THM write via device helper: update room heat & cool setpoints and away mode
        thm_helper = coord.get_device_helper("ATHM-4304")
        assert isinstance(thm_helper, ThmDevice)
        await thm_helper.set_heat_setpoint(Temperature(71.0, "F"))
        await thm_helper.set_cool_setpoint(Temperature(76.0, "F"))
        await thm_helper.set_away_mode(True)
        await coord.async_refresh()
        thm_params = coord.data["devices"]["ATHM-4304"]["parameters"]
        assert thm_params["heat_setpoint"] == pytest.approx(71.0)
        assert thm_params["cool_setpoint"] == pytest.approx(76.0)
        assert thm_params["away_mode_activated"] is True

        # Test ZON write via device helper: toggle App Button (drives relay 12) and update Aux Setpoint
        zon_helper = coord.get_device_helper("AZON-0224")
        assert isinstance(zon_helper, ZonDevice)
        await zon_helper.set_app_button(True)
        await zon_helper.set_aux_setpoint(Temperature(130, "F"))
        await coord.async_refresh()
        zon_params = coord.data["devices"]["AZON-0224"]["parameters"]
        assert zon_params["app_button_activated"] is True
        assert zon_params["relays"][11] is True
        assert zon_params["aux_setpoint_target"] == 130

        # Test Demo outdoor temperature simulation
        assert isinstance(coord.sensorlinx, DemoSensorlinxClient)
        coord.sensorlinx.set_simulated_outdoor_temp(10.0)
        await coord.async_refresh()
        assert coord.data["devices"]["AECO-0982"]["parameters"]["temperature_outdoor"] == pytest.approx(10.0)
    finally:
        await coord.stop()


@pytest.mark.asyncio
async def test_main_window_and_widgets(qapp):
    config = AppConfig()
    coord = SensorlinxCoordinator()

    try:
        win = MainWindow(coord, config)
        await coord.start_demo_mode()
        win.show()

        # Verify sidebar populated Overview + Local LAN + 5 devices
        assert win.nav_list.count() == 7
        assert "AECO-0982" in win.device_panels
        assert "AZON-0224" in win.device_panels
        assert "ATHM-4304" in win.device_panels

        # Test switching unit between °F and °C across all panels
        win._on_unit_changed(1)  # Switch to °C
        assert win.unit == "C"

        win._on_unit_changed(0)  # Switch back to °F
        assert win.unit == "F"

        # Test OutdoorResetChartWidget painting and coordinate helpers
        eco_panel = win.device_panels["AECO-0982"]
        chart: OutdoorResetChartWidget = eco_panel.chart_widget
        rect = chart._plot_rect()
        pt = chart._f_to_screen(5.0, 125.0, rect)
        out_f, tank_f = chart._screen_to_f(pt, rect)
        assert out_f == pytest.approx(5.0, abs=0.5)
        assert tank_f == pytest.approx(125.0, abs=0.5)

        # Test EcoDevicePanel async apply methods
        eco_panel.hot_max_spin.setValue(140.0)
        await eco_panel._async_apply_tank_and_curve()
        assert coord.data["devices"]["AECO-0982"]["parameters"]["hot_tank_max_temp"].value == 140

        eco_panel.stage_on_lag_spin.setValue(12)
        await eco_panel._async_apply_staging()
        assert coord.data["devices"]["AECO-0982"]["parameters"]["stage_on_lag_time"] == 12

        eco_panel.bk_lag_spin.setValue(25)
        await eco_panel._async_apply_backup()
        assert coord.data["devices"]["AECO-0982"]["parameters"]["backup_lag_time"] == 25

        eco_panel.dhw_target_spin.setValue(126.0)
        await eco_panel._async_apply_dhw()
        assert coord.data["devices"]["AECO-0982"]["parameters"]["dhw_target_temp"].value == 126

        # Test ThmDevicePanel async apply methods
        thm_panel = win.device_panels["ATHM-4304"]
        thm_panel.heat_sp_spin.setValue(70.0)
        thm_panel.cool_sp_spin.setValue(76.0)
        await thm_panel._async_apply_home_setpoints()
        assert coord.data["devices"]["ATHM-4304"]["parameters"]["heat_setpoint"] == pytest.approx(70.0)

        # Test ZonDevicePanel async apply methods
        zon_panel = win.device_panels["AZON-0224"]
        zon_panel.aux_spin.setValue(128.0)
        await zon_panel._async_apply_aux_setpoint()
        assert coord.data["devices"]["AZON-0224"]["parameters"]["aux_setpoint_target"] == 128

        win.close()
    finally:
        await coord.stop()


def test_local_lan_frame_parser_and_block_analyzer():
    raw = bytearray(b"\x01" * 16 + b"<<<>>>" + b"\x02" * 16 + b"<<<")
    frames = parse_delimited_frames(raw)
    assert len(frames) == 2
    assert frames[0] == (b"\x01" * 16, "<<<>>>")
    assert frames[1] == (b"\x02" * 16, "<<<")
    assert len(raw) == 0

    mgr = LocalLanManager(hosts=["192.168.1.50", "192.168.1.51"])
    mgr.ingest_frame("192.168.1.50", b"\xaa" * 168, "<<<>>>", now=1000.0)
    mgr.ingest_frame("192.168.1.50", b"\xaa" * 160 + b"\xbb" * 8, "<<<>>>", now=1001.6)

    st = mgr.states["192.168.1.50"]
    assert st.frames_received == 2
    ft = st.frame_types["A_168B"]
    assert len(ft.blocks) == 21
    assert ft.blocks[20].change_count == 1
    assert ft.blocks[20].current_hex == "bb bb bb bb bb bb bb bb"
    assert ft.blocks[20].previous_hex == "aa aa aa aa aa aa aa aa"


def test_local_xtea_decrypt_and_pseudo_json_parser():
    # Synthetic 168-byte XTEA-encrypted frame matching ECO-0600 primaryinfo format (no personal SSID/PASS)
    sample_plain = (
        b"{type:primaryinfo,data:{priCPU:AECO-0001,stgS:0,numStg:1,revV:0,useBkUp:1,"
        b"priBUp:0,secPmp:257,SSID:ExampleHomeIoT,PASS:redacted,out:33.00,version:2.08,crc:54532}}"
    ).ljust(168, b" ")
    fa_202 = xtea_encrypt(sample_plain)
    dec_bytes = xtea_decrypt(fa_202)
    assert xtea_encrypt(dec_bytes) == fa_202

    dec_str = dec_bytes.decode("latin1").strip()
    assert dec_str.startswith("{type:primaryinfo,data:{priCPU:AECO-0001")
    parsed = parse_hbx_pseudo_json(dec_str)
    assert parsed["type"] == "primaryinfo"
    assert parsed["data"]["priCPU"] == "AECO-0001"
    assert parsed["data"]["out"] == pytest.approx(33.0)
    assert parsed["data"]["version"] == "2.08"

    mgr = LocalLanManager(hosts=["192.168.1.50"])
    mgr.ingest_frame("192.168.1.50", fa_202, "<<<>>>", now=2000.0)
    st = mgr.states["192.168.1.50"]
    assert st.decoded_telemetry["priCPU"] == "AECO-0001"
    assert "ECO-0600" in st.inferred_device_role()


@pytest.mark.asyncio
async def test_local_mode_coordinator_and_live_xtea_sync(qapp, monkeypatch, tmp_path):
    from sensorlinx_desktop import local_client

    monkeypatch.setattr(local_client, "SNAPSHOT_PATH", tmp_path / "no_snapshot.json")
    monkeypatch.setattr(
        local_client.LocalSensorlinxClient,
        "__init__",
        lambda self, snapshot_path=tmp_path / "no_snapshot.json": (
            super(local_client.LocalSensorlinxClient, self).__init__(),
            setattr(self, "_snapshot_path", snapshot_path),
            setattr(self, "has_cloud_snapshot", False),
            setattr(self, "_last_frame_counts", {}),
            self.reload_state_from_snapshot(),
            setattr(self, "_demo_logged_in", True),
        )[-1],
    )
    config = AppConfig()
    coord = SensorlinxCoordinator()
    mgr = LocalLanManager(hosts=["192.168.1.50", "192.168.1.51"])

    try:
        win = MainWindow(coord, config, local_manager=mgr)
        ok = await coord.start_local_mode(mgr)
        assert ok is True
        assert coord.is_local is True
        assert coord.mode == "local"
        assert "AECO-0001" in coord.data["devices"]
        assert "AZON-0001" in coord.data["devices"]
        # Ensure zero demo devices leak into Local LAN mode
        assert "ATHM-4304" not in coord.data["devices"]
        assert "ATHM-2625" not in coord.data["devices"]
        assert "ATHM-4316" not in coord.data["devices"]
        assert {"AECO-0001", "AZON-0001"}.issubset(set(coord.data["devices"].keys()))
        assert win.mode_badge.text() == "LOCAL LAN MODE (NO CLOUD)"

        # Feed a live XTEA-encrypted frame with stgS:1 and out:39.50 from 192.168.1.50
        live_frame = xtea_encrypt(
            b"{type:primaryinfo,data:{priCPU:AECO-0001,stgS:1,numStg:1,revV:0,useBkUp:1,priBUp:0,secPmp:451,out:39.50,version:2.08,crc:12345}}"
        )
        mgr.ingest_frame("192.168.1.50", live_frame, "<<<>>>", now=3000.0)
        coord.on_local_lan_updated(mgr)
        await coord.async_refresh()

        eco_params = coord.data["devices"]["AECO-0001"]["parameters"]
        assert eco_params["temperature_outdoor"] == pytest.approx(39.5)
        assert "temperature_tank" not in eco_params
        assert eco_params["heatpump_stages"][0]["activated"] is True
        assert eco_params["local_telemetry"]["secPmp"] == 451
        assert eco_params["local_telemetry"]["stgS"] == 1

        # Feed a live XTEA-encrypted frame from 192.168.1.51 (AZON-0001) with znInDem:5 (Zone 1 & 3 calling)
        zon_frame = xtea_encrypt(
            b"{type:primaryinfo,data:{znInPri:9,znInDem:5,version:1.45,SSID:ExampleHomeIoT,PASS:pw,thmBVer:0.00,out:41,crc:42860}}"
        )
        mgr.ingest_frame("192.168.1.51", zon_frame, "<<<>>>", now=3001.0)
        coord.on_local_lan_updated(mgr)
        await coord.async_refresh()

        zon_params = coord.data["devices"]["AZON-0001"]["parameters"]
        assert zon_params["demand_on"] == 5
        assert zon_params["zone_priority"] == 9
        assert zon_params["relays"][0] is True
        assert zon_params["relays"][1] is False
        assert zon_params["relays"][2] is True
        assert zon_params["relays"][3] is False
        assert len(zon_params["pumps"]) == 2
        assert len(zon_params["demands"]) == 3
        assert len(zon_params["fancoil"]) == 4
        assert zon_params["aux_setpoint_target"] == 120
        assert zon_params["app_button_enabled"] is True

        # Verify ZonDevicePanel displays all cards and controls in Local LAN Mode
        zon_panel = win.device_panels["AZON-0001"]
        assert "2 / 4 Calling" in zon_panel.demand_card_val.text()
        assert zon_panel.ctrl_grp.isHidden() is False
        assert zon_panel.app_btn_chk.isHidden() is False

        win.close()
    finally:
        await coord.stop()




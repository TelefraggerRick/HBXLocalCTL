# HBX Controls • SensorLinx Desktop (Windows & Linux)

A cross-platform native desktop application (**Windows** & **Linux**) built with **Python**, **PySide6 (Qt 6)**, `qasync`, and [`pysensorlinx`](https://github.com/sslivins/pysensorlinx) (with parameter & entity logic aligned to [`hass_hbxcontrols`](https://github.com/sslivins/hass_hbxcontrols)) to monitor and control **HBX Controls** hydronic heating and cooling systems.

---

## Key Features

### 1. Full Multi-Device HBX Controls Support
- **ECO-0600 Hydronic Heat Pump / Boiler Controller (`EcoDevicePanel`)**
  - **Live Telemetry Cards**: Buffer tank actual vs. target temperature, outdoor sensor temperature & shutdown status, Domestic Hot Water (DHW) tank actual vs. target, active heat pump stage badges & runtime hours, backup boiler runtime, pumps 1–3, reversing valve state, and active demands.
  - **Interactive Outdoor Reset Curve Visualizer & Editor (`OutdoorResetChartWidget`)**:
    - Custom `QPainter` chart plotting both the **Hot Tank (Heating)** and **Cold Tank (Cooling)** Outdoor Reset curves, differential bands (`htDif` / `clDif`), Warm Weather Shutdown (`wwsd`) & Cold Weather Shutdown (`cwsd`) cutoffs, and live outdoor/tank operating markers.
    - **Draggable Control Handles**: Drag curve anchor points directly on the chart or fine-tune values in spinboxes (`dot`, `mbt`, `dbt`, `htDif`, `wwsd`, `cdot`, `mst`, `dst`, `clDif`, `cwsd`).
    - Automatically handles HBX's flat-target requirement (`mbt == dbt`) when Outdoor Reset is set to `"off"`.
  - **Heat Pump Staging & Rotation**: Configure number of stages (1–4), 2-stage heat pump mode, Stage ON lag (minutes), Stage OFF lag (seconds), synchronized off-staging, cycle/time rotation, weather shutdown lag time, heat/cool switchover delay, and wide priority differential.
  - **Backup Boiler & DHW Controls**: Configure backup lag time, backup outdoor temperature cutoff, backup differential, backup-only outdoor/tank thresholds, and DHW enable, target temperature, and differential.

- **THM-0600 Zone Thermostats (`ThmDevicePanel`)**
  - Room temperature, floor sensor temperature, relative humidity, and active demand decoding from the `dmd` bitfield (`0x02` heating, `0x40` cooling, `0x80` fan).
  - HVAC changeover mode (`off`, `heat`, `cool`, `auto`), Fan mode (`auto`, `on`, `off`), and Away preset toggle (`away`).
  - Dual Home Heat/Cool setpoints (`rmT` / `rmCT`) and writable Away Heat/Cool setpoints (`hRmT` / `hRmCT`).
  - Humidity control mode (`off`, `on`, `auto`) & target humidity (`10%–80%`).
  - Programmable schedule enable toggle (`pgmble`) and 4-period schedule table viewer.

- **ZON-0600 Zone Controllers (`ZonDevicePanel`)**
  - Wired zone relay status cards filtered by `relType` and numbered using `sequence * 4 + idx + 1`.
  - Automatic parent-child linking (`thmInfo` sync codes) with one-click navigation to each zone's paired `THM-0600` thermostat.
  - **App Button (`aBut`)** toggle driving Relay 12 (`relays[11]`).
  - **Auxiliary Setpoint (`dhwT`)** temperature control (`32°F–212°F`), plus zone pumps, fancoil, and demand status.

- **System Overview & Building Weather (`SystemOverviewPanel`)**
  - Current outdoor weather (temperature, feels-like, min/max, humidity, wind, barometric pressure) and 6-period forecast for each building, plus quick-jump summary cards for every controller and thermostat.

### 2. Offline Local LAN Mode (Direct TCP Port 2000 XTEA Stream — No Cloud Required)
- Connects directly to local HBX controllers on your LAN (e.g. `ECO-0600` and `ZON-0600` on TCP port `2000`) with **zero cloud dependency** (configured via `~/.sensorlinx_hosts.json` or `HBX_LOCAL_HOSTS`).
- Decrypts 8-byte ECB frames (`<<<>>>` telemetry and `<<<` sync frames) in real time using a locally configured 128-bit key (`~/.sensorlinx_xtea.key` or `HBX_XTEA_KEY` env var — omitted from the public repository for device security) and updates live outdoor temperature, heat pump stage state (`stgS`), backup boiler state (`useBkUp`/`priBUp`), system pump state (`secPmp`), reversing valve (`revV`), and active zone demands (`znInPri`/`znInDem`) across all dashboard panels.
- Includes a dedicated **Local LAN Stream (`:2000`)** inspector panel showing live decrypted frames and 8-byte XTEA blocks.

### 3. Interactive Demo / Simulation Mode
- Switchable anytime from **Connection Mode (Local / Cloud / Demo)** (`DemoSensorlinxClient`) with a complete simulated residence (`AECO-0982`, `AZON-0224`, and 3 `THM-0600` thermostats) so you can test every curve, setpoint, stage, and relay offline.
- Includes live **Outdoor Temperature** and **Room Temperature** simulation sliders that dynamically recompute outdoor reset targets, weather shutdowns, thermostat calls, and zone relay states in real time.

### 4. Desktop Polish (Windows & Linux)
- Instant **°F (Fahrenheit) / °C (Celsius)** display unit switching (properly distinguishing absolute `Temperature` vs. `TemperatureDelta` differentials).
- Optimistic parameter hold window after writes so cloud polling lag never snaps controls back to stale values.
- OS Keyring + `QSettings` credential storage and System Tray icon support.

---

## Running the Application

### Windows
Double-click `run_windows.bat` or run from PowerShell:
```powershell
.\.venv\Scripts\python.exe -m sensorlinx_desktop.main
```

### Linux
Run the launcher script (automatically creates `.venv` if needed):
```bash
chmod +x run_linux.sh
./run_linux.sh
```

### Command-Line Options
```bash
sensorlinx-desktop --local      # Start directly in Offline Local LAN Mode (default, no cloud needed)
sensorlinx-desktop --demo       # Start directly in Demo / Simulation Mode
sensorlinx-desktop --unit C     # Start with Celsius (°C) display units
sensorlinx-desktop --unit F     # Start with Fahrenheit (°F) display units
```

---

## Running Automated Tests
```powershell
.\.venv\Scripts\pytest.exe -v
```

---

## Building Standalone Binaries (Windows `.exe` / Linux Binary)
Install `pyinstaller` into the virtual environment and run `build_desktop.py`:
```bash
uv pip install pyinstaller
python build_desktop.py
```
The packaged executable is written to `dist/SensorLinx-Desktop.exe` on Windows or `dist/sensorlinx-desktop` (alongside `dist/sensorlinx-desktop.desktop`) on Linux.

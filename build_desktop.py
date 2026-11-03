"""Cross-platform PyInstaller build script for Windows (.exe) and Linux binaries."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    assets_dir = root / "src" / "sensorlinx_desktop" / "assets"
    entry_script = root / "src" / "sensorlinx_desktop" / "main.py"
    icon_png = assets_dir / "icon.png"

    is_windows = platform.system().lower().startswith("win")
    sep = ";" if is_windows else ":"
    exe_name = "SensorLinx-Desktop" if is_windows else "sensorlinx-desktop"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--name",
        exe_name,
        "--add-data",
        f"{assets_dir}{sep}sensorlinx_desktop/assets",
    ]
    if icon_png.exists():
        cmd.extend(["--icon", str(icon_png)])

    cmd.append(str(entry_script))

    print("Running PyInstaller:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(root))
    if res.returncode != 0:
        return res.returncode

    if not is_windows:
        desktop_file = root / "dist" / "sensorlinx-desktop.desktop"
        desktop_file.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=HBX SensorLinx Desktop\n"
            "Comment=Monitor and control HBX Controls ECO-0600, THM-0600, and ZON-0600 heating/cooling systems\n"
            f"Exec={root / 'dist' / exe_name}\n"
            f"Icon={icon_png}\n"
            "Terminal=false\n"
            "Categories=Utility;HomeAutomation;\n",
            encoding="utf-8",
        )
        os.chmod(desktop_file, 0o755)
        print(f"Created Linux desktop launcher: {desktop_file}")

    print(f"Build complete! Output located in: {root / 'dist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

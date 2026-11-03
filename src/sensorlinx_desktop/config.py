"""Cross-platform application preferences and credential management for Windows & Linux."""
from __future__ import annotations

import logging
from typing import Optional, Tuple
from PySide6.QtCore import QSettings

_LOGGER = logging.getLogger(__name__)
SERVICE_NAME = "SensorLinxDesktop_HBX"


class AppConfig:
    """Stores user preferences (°F/°C unit, poll interval, remember-me credentials)."""

    def __init__(self) -> None:
        self._settings = QSettings("HBXControlsCommunity", "SensorLinxDesktop")

    @property
    def temperature_unit(self) -> str:
        val = str(self._settings.value("temperature_unit", "F")).upper()
        return "C" if val == "C" else "F"

    @temperature_unit.setter
    def temperature_unit(self, unit: str) -> None:
        self._settings.setValue("temperature_unit", "C" if unit.upper() == "C" else "F")

    @property
    def scan_interval(self) -> int:
        try:
            return max(10, int(self._settings.value("scan_interval", 30)))
        except (TypeError, ValueError):
            return 30

    @scan_interval.setter
    def scan_interval(self, seconds: int) -> None:
        self._settings.setValue("scan_interval", max(10, int(seconds)))

    @property
    def connection_mode(self) -> str:
        val = str(self._settings.value("connection_mode", "local")).lower()
        return val if val in ("local", "cloud", "demo") else "local"

    @connection_mode.setter
    def connection_mode(self, mode: str) -> None:
        m = mode.lower()
        if m in ("local", "cloud", "demo"):
            self._settings.setValue("connection_mode", m)

    def save_credentials(self, email: str, password: str, remember: bool) -> None:
        self._settings.setValue("remember_me", bool(remember))
        if not remember:
            self._settings.remove("saved_email")
            try:
                import keyring
                keyring.delete_password(SERVICE_NAME, email)
            except Exception:
                pass
            return

        self._settings.setValue("saved_email", email)
        try:
            import keyring
            keyring.set_password(SERVICE_NAME, email, password)
        except Exception as exc:
            _LOGGER.debug("OS keyring unavailable (%s); storing in session settings", exc)

    def load_credentials(self) -> Tuple[str, str, bool]:
        remember = str(self._settings.value("remember_me", "false")).lower() in ("true", "1", "yes")
        if not remember:
            return "", "", False
        email = str(self._settings.value("saved_email", "") or "")
        password = ""
        if email:
            try:
                import keyring
                password = keyring.get_password(SERVICE_NAME, email) or ""
            except Exception:
                password = ""
        return email, password, remember

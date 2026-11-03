"""Data models, unit conversion helpers, and Outdoor Reset curve calculations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union
from pysensorlinx import Temperature, TemperatureDelta


class UnitHelper:
    """Handles conversion and formatting between Fahrenheit (API native) and Celsius."""

    @staticmethod
    def f_to_display(value_f: Optional[Union[float, int, Temperature]], unit: str = "F") -> Optional[float]:
        """Convert a Fahrenheit value or Temperature object to the selected display unit."""
        if value_f is None or value_f == "off":
            return None
        if isinstance(value_f, Temperature):
            return value_f.to_celsius() if unit.upper() == "C" else value_f.to_fahrenheit()
        try:
            f_val = float(value_f)
        except (TypeError, ValueError):
            return None
        if unit.upper() == "C":
            return (f_val - 32.0) * 5.0 / 9.0
        return f_val

    @staticmethod
    def display_to_f(display_val: float, unit: str = "F") -> float:
        """Convert a user-entered display temperature (°F or °C) back to °F."""
        if unit.upper() == "C":
            return display_val * 9.0 / 5.0 + 32.0
        return float(display_val)

    @staticmethod
    def delta_f_to_display(delta_f: Optional[Union[float, int, TemperatureDelta]], unit: str = "F") -> Optional[float]:
        """Convert a Fahrenheit temperature delta (no +32 offset) to the display unit."""
        if delta_f is None or delta_f == "off":
            return None
        if isinstance(delta_f, TemperatureDelta):
            return delta_f.to_celsius() if unit.upper() == "C" else delta_f.to_fahrenheit()
        try:
            d_val = float(delta_f)
        except (TypeError, ValueError):
            return None
        if unit.upper() == "C":
            return d_val * 5.0 / 9.0
        return d_val

    @staticmethod
    def display_to_delta_f(display_delta: float, unit: str = "F") -> float:
        """Convert a user-entered temperature delta (°F or °C) back to Δ°F."""
        if unit.upper() == "C":
            return display_delta * 9.0 / 5.0
        return float(display_delta)

    @staticmethod
    def format_temp(value_f: Optional[Union[float, int, Temperature, str]], unit: str = "F", decimals: int = 1) -> str:
        """Format an absolute temperature for display."""
        if value_f is None:
            return "—"
        if isinstance(value_f, str) and value_f.lower() == "off":
            return "Off"
        converted = UnitHelper.f_to_display(value_f, unit)
        if converted is None:
            return "—"
        symbol = "°C" if unit.upper() == "C" else "°F"
        return f"{converted:.{decimals}f}{symbol}"

    @staticmethod
    def format_delta(delta_f: Optional[Union[float, int, TemperatureDelta, str]], unit: str = "F", decimals: int = 1) -> str:
        """Format a temperature differential for display."""
        if delta_f is None:
            return "—"
        if isinstance(delta_f, str) and delta_f.lower() == "off":
            return "Off"
        converted = UnitHelper.delta_f_to_display(delta_f, unit)
        if converted is None:
            return "—"
        symbol = "Δ°C" if unit.upper() == "C" else "Δ°F"
        return f"{converted:.{decimals}f}{symbol}"


@dataclass
class OutdoorResetCurveConfig:
    """Parameters defining the Hot Tank (Heating) and Cold Tank (Cooling) outdoor reset curves."""

    # Heating curve (Hot Tank)
    hot_reset_enabled: bool = True
    hot_design_outdoor_f: float = 0.0        # dot: -40 to 127 °F
    hot_wwsd_enabled: bool = True
    hot_wwsd_f: float = 70.0                 # wwsd: 34 to 180 °F (default warm end = 70°F if wwsd off)
    hot_min_tank_f: float = 85.0             # mbt: 2 to 180 °F (bottom of heat curve, or flat target when reset off)
    hot_max_tank_f: float = 135.0            # dbt: 2 to 180 °F (top of heat curve)
    hot_differential_f: float = 6.0          # htDif: 2 to 100 Δ°F

    # Cooling curve (Cold Tank)
    cold_reset_enabled: bool = False
    cold_design_outdoor_f: float = 95.0      # cdot: 0 to 119 °F
    cold_cwsd_enabled: bool = True
    cold_cwsd_f: float = 55.0                # cwsd: 33 to 119 °F
    cold_min_tank_f: float = 45.0            # mst: 2 to 180 °F (bottom of cool curve, or flat target when reset off)
    cold_max_tank_f: float = 60.0            # dst: 2 to 180 °F (top of cool curve)
    cold_differential_f: float = 8.0         # clDif: 2 to 100 Δ°F

    # Live readings for markers on chart
    current_outdoor_f: Optional[float] = None
    current_tank_f: Optional[float] = None
    computed_target_f: Optional[float] = None

    def compute_hot_target_f(self, outdoor_f: float) -> Optional[float]:
        """Compute the Hot Tank target temperature (°F) at a given outdoor temperature (°F).

        Matches HBX ECO-0600 Outdoor Reset logic:
        - If WWSD is enabled and outdoor_f > hot_wwsd_f, heating is in Warm Weather Shutdown (returns None).
        - If outdoor reset is disabled, returns flat setpoint `hot_min_tank_f`.
        - If outdoor reset is enabled, interpolates linearly between:
            (warm_anchor_f, hot_min_tank_f) and (hot_design_outdoor_f, hot_max_tank_f)
          clamped to [hot_min_tank_f, hot_max_tank_f].
        """
        if not self.hot_reset_enabled:
            return self.hot_min_tank_f

        warm_anchor = self.hot_wwsd_f if self.hot_wwsd_enabled else 70.0
        cold_anchor = self.hot_design_outdoor_f
        t_min = min(self.hot_min_tank_f, self.hot_max_tank_f)
        t_max = max(self.hot_min_tank_f, self.hot_max_tank_f)

        if abs(warm_anchor - cold_anchor) < 1e-3:
            return t_max

        if outdoor_f <= cold_anchor:
            return t_max
        if outdoor_f >= warm_anchor:
            return t_min

        # Linear interpolation: as outdoor drops from warm_anchor to cold_anchor, target rises from t_min to t_max
        ratio = (warm_anchor - outdoor_f) / (warm_anchor - cold_anchor)
        return t_min + ratio * (t_max - t_min)

    def compute_cold_target_f(self, outdoor_f: float) -> Optional[float]:
        """Compute the Cold Tank target temperature (°F) at a given outdoor temperature (°F).

        Matches HBX ECO-0600 Cooling Outdoor Reset logic:
        - If outdoor reset is disabled, returns flat setpoint `cold_min_tank_f`.
        - If outdoor reset is enabled, interpolates linearly between:
            (cold_anchor_f, cold_max_tank_f) and (hot_anchor_f, cold_min_tank_f)
          clamped to [cold_min_tank_f, cold_max_tank_f].
        """
        if not self.cold_reset_enabled:
            return self.cold_min_tank_f

        cool_anchor = self.cold_cwsd_f if self.cold_cwsd_enabled else 55.0
        hot_anchor = self.cold_design_outdoor_f
        t_min = min(self.cold_min_tank_f, self.cold_max_tank_f)
        t_max = max(self.cold_min_tank_f, self.cold_max_tank_f)

        if abs(hot_anchor - cool_anchor) < 1e-3:
            return t_min

        if outdoor_f >= hot_anchor:
            return t_min
        if outdoor_f <= cool_anchor:
            return t_max

        ratio = (outdoor_f - cool_anchor) / (hot_anchor - cool_anchor)
        return t_max - ratio * (t_max - t_min)

    @classmethod
    def from_eco_parameters(cls, params: dict[str, Any]) -> "OutdoorResetCurveConfig":
        """Build an OutdoorResetCurveConfig from extracted ECO device parameters."""
        def _scalar(val: Any, default: float) -> float:
            if val is None or val == "off":
                return default
            if hasattr(val, "to_fahrenheit"):
                return float(val.to_fahrenheit())
            if hasattr(val, "value"):
                return float(val.value)
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        hot_or = params.get("hot_tank_outdoor_reset")
        hot_or_enabled = hot_or is not None and hot_or != "off"

        wwsd = params.get("warm_weather_shutdown")
        wwsd_enabled = wwsd is not None and wwsd != "off"

        cold_or = params.get("cold_tank_outdoor_reset")
        cold_or_enabled = cold_or is not None and cold_or != "off"

        cwsd = params.get("cold_weather_shutdown")
        cwsd_enabled = cwsd is not None and cwsd != "off"

        return cls(
            hot_reset_enabled=hot_or_enabled,
            hot_design_outdoor_f=_scalar(hot_or, 0.0),
            hot_wwsd_enabled=wwsd_enabled,
            hot_wwsd_f=_scalar(wwsd, 70.0),
            hot_min_tank_f=_scalar(params.get("hot_tank_min_temp"), 85.0),
            hot_max_tank_f=_scalar(params.get("hot_tank_max_temp"), 135.0),
            hot_differential_f=_scalar(params.get("hot_tank_differential"), 6.0),
            cold_reset_enabled=cold_or_enabled,
            cold_design_outdoor_f=_scalar(cold_or, 95.0),
            cold_cwsd_enabled=cwsd_enabled,
            cold_cwsd_f=_scalar(cwsd, 55.0),
            cold_min_tank_f=_scalar(params.get("cold_tank_min_temp"), 45.0),
            cold_max_tank_f=_scalar(params.get("cold_tank_max_temp"), 60.0),
            cold_differential_f=_scalar(params.get("cold_tank_differential"), 8.0),
            current_outdoor_f=params.get("temperature_outdoor"),
            current_tank_f=params.get("temperature_tank"),
            computed_target_f=params.get("target_temperature_tank"),
        )

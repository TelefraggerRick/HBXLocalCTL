"""Interactive Outdoor Reset Curve Visualizer & Editor widget."""
from __future__ import annotations

from typing import Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..models import OutdoorResetCurveConfig, UnitHelper


class OutdoorResetChartWidget(QWidget):
    """Custom QPainter chart that plots and allows interactive dragging of HBX Outdoor Reset curves."""

    curve_edited = Signal(object)  # Emits updated OutdoorResetCurveConfig when control point dragged

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(520, 340)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self.config = OutdoorResetCurveConfig()
        self.unit: str = "F"
        self.show_cooling_curve: bool = True

        # Fixed internal domain in °F
        self._x_min_f = -40.0
        self._x_max_f = 115.0
        self._y_min_f = 30.0
        self._y_max_f = 185.0

        self._dragging_handle: Optional[str] = None
        self._hover_handle: Optional[str] = None
        self._hover_pos: Optional[QPointF] = None

    def set_config(self, config: OutdoorResetCurveConfig, unit: str = "F") -> None:
        if self._dragging_handle is None:
            self.config = config
        self.unit = unit.upper()
        self.update()

    def set_unit(self, unit: str) -> None:
        self.unit = unit.upper()
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(62.0, 28.0, max(100.0, self.width() - 86.0), max(100.0, self.height() - 72.0))

    def _f_to_screen(self, out_f: float, tank_f: float, rect: QRectF) -> QPointF:
        x_ratio = (out_f - self._x_min_f) / (self._x_max_f - self._x_min_f)
        y_ratio = (tank_f - self._y_min_f) / (self._y_max_f - self._y_min_f)
        x = rect.left() + x_ratio * rect.width()
        y = rect.bottom() - y_ratio * rect.height()
        return QPointF(x, y)

    def _screen_to_f(self, pt: QPointF, rect: QRectF) -> Tuple[float, float]:
        x_ratio = max(0.0, min(1.0, (pt.x() - rect.left()) / max(1.0, rect.width())))
        y_ratio = max(0.0, min(1.0, (rect.bottom() - pt.y()) / max(1.0, rect.height())))
        out_f = self._x_min_f + x_ratio * (self._x_max_f - self._x_min_f)
        tank_f = self._y_min_f + y_ratio * (self._y_max_f - self._y_min_f)
        return out_f, tank_f

    def _get_handles(self, rect: QRectF) -> dict[str, QPointF]:
        handles: dict[str, QPointF] = {}
        c = self.config
        if c.hot_reset_enabled:
            warm_x = c.hot_wwsd_f if c.hot_wwsd_enabled else 70.0
            handles["hot_design"] = self._f_to_screen(c.hot_design_outdoor_f, c.hot_max_tank_f, rect)
            handles["hot_warm"] = self._f_to_screen(warm_x, c.hot_min_tank_f, rect)
        else:
            handles["hot_flat"] = self._f_to_screen(35.0, c.hot_min_tank_f, rect)

        if self.show_cooling_curve and c.cold_reset_enabled:
            cool_x = c.cold_cwsd_f if c.cold_cwsd_enabled else 55.0
            handles["cold_design"] = self._f_to_screen(c.cold_design_outdoor_f, c.cold_min_tank_f, rect)
            handles["cold_cool"] = self._f_to_screen(cool_x, c.cold_max_tank_f, rect)
        return handles

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            rect = self._plot_rect()
            pos = event.position()
            for name, h_pt in self._get_handles(rect).items():
                if (pos - h_pt).manhattanLength() <= 16.0:
                    self._dragging_handle = name
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        rect = self._plot_rect()
        pos = event.position()
        self._hover_pos = pos if rect.contains(pos) else None

        if self._dragging_handle:
            out_f, tank_f = self._screen_to_f(pos, rect)
            c = self.config
            if self._dragging_handle == "hot_design":
                c.hot_design_outdoor_f = round(max(-40.0, min(110.0, out_f)))
                c.hot_max_tank_f = round(max(c.hot_min_tank_f + 2.0, min(180.0, tank_f)))
            elif self._dragging_handle == "hot_warm":
                if c.hot_wwsd_enabled:
                    c.hot_wwsd_f = round(max(34.0, min(115.0, out_f)))
                c.hot_min_tank_f = round(max(35.0, min(c.hot_max_tank_f - 2.0, tank_f)))
            elif self._dragging_handle == "hot_flat":
                c.hot_min_tank_f = round(max(35.0, min(180.0, tank_f)))
                c.hot_max_tank_f = c.hot_min_tank_f
            elif self._dragging_handle == "cold_design":
                c.cold_design_outdoor_f = round(max(40.0, min(115.0, out_f)))
                c.cold_min_tank_f = round(max(35.0, min(c.cold_max_tank_f - 2.0, tank_f)))
            elif self._dragging_handle == "cold_cool":
                if c.cold_cwsd_enabled:
                    c.cold_cwsd_f = round(max(33.0, min(100.0, out_f)))
                c.cold_max_tank_f = round(max(c.cold_min_tank_f + 2.0, min(120.0, tank_f)))

            self.curve_edited.emit(c)
            self.update()
            return

        # Check handle hover
        hovered = None
        for name, h_pt in self._get_handles(rect).items():
            if (pos - h_pt).manhattanLength() <= 16.0:
                hovered = name
                break
        self._hover_handle = hovered
        if hovered:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor if rect.contains(pos) else Qt.CursorShape.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_handle:
            self._dragging_handle = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.curve_edited.emit(self.config)
            self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_pos = None
        self._hover_handle = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Background card
        bg_rect = QRectF(0, 0, self.width(), self.height())
        painter.setPen(QPen(QColor("#2A3241"), 1.0))
        painter.setBrush(QColor("#111621"))
        painter.drawRoundedRect(bg_rect.adjusted(1, 1, -1, -1), 10, 10)

        rect = self._plot_rect()
        c = self.config
        unit_sym = "°C" if self.unit == "C" else "°F"

        # Grid lines & axes
        grid_pen = QPen(QColor("#1F2737"), 1.0, Qt.PenStyle.DotLine)
        label_font = QFont("Segoe UI", 8)
        painter.setFont(label_font)

        # X-axis ticks (Outdoor Temp)
        for out_f in range(-40, 120, 20):
            pt = self._f_to_screen(out_f, self._y_min_f, rect)
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(pt.x(), rect.top()), QPointF(pt.x(), rect.bottom()))
            painter.setPen(QColor("#8A99AD"))
            disp = UnitHelper.f_to_display(out_f, self.unit)
            painter.drawText(
                QRectF(pt.x() - 24, rect.bottom() + 6, 48, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{disp:.0f}{unit_sym}",
            )

        # Y-axis ticks (Tank Target Temp)
        for tank_f in range(40, 190, 25):
            pt = self._f_to_screen(self._x_min_f, tank_f, rect)
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(rect.left(), pt.y()), QPointF(rect.right(), pt.y()))
            painter.setPen(QColor("#8A99AD"))
            disp = UnitHelper.f_to_display(tank_f, self.unit)
            painter.drawText(
                QRectF(4, pt.y() - 9, rect.left() - 10, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{disp:.0f}{unit_sym}",
            )

        # Axis titles
        title_font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor("#9FB0C7"))
        painter.drawText(
            QRectF(rect.left(), self.height() - 22, rect.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            f"Outdoor Temperature ({unit_sym})  —  Drag control points to adjust curve",
        )
        painter.drawText(
            QRectF(rect.left(), 6, rect.width(), 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "HBX ECO-0600 Outdoor Reset Curve (Tank Target vs. Outdoor Temp)",
        )

        # Clip to plot area for curves & bands
        painter.save()
        painter.setClipRect(rect)

        # 1. Warm Weather Shutdown shaded zone
        if c.hot_wwsd_enabled:
            wwsd_pt = self._f_to_screen(c.hot_wwsd_f, self._y_max_f, rect)
            wwsd_rect = QRectF(wwsd_pt.x(), rect.top(), rect.right() - wwsd_pt.x(), rect.height())
            painter.fillRect(wwsd_rect, QColor(255, 170, 50, 18))
            painter.setPen(QPen(QColor("#F59E0B"), 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(wwsd_pt.x(), rect.top()), QPointF(wwsd_pt.x(), rect.bottom()))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(
                QRectF(wwsd_pt.x() + 4, rect.top() + 6, 130, 16),
                Qt.AlignmentFlag.AlignLeft,
                f"WWSD > {UnitHelper.format_temp(c.hot_wwsd_f, self.unit, 0)}",
            )

        # 2. Heating Curve & Differential Band
        hot_points = []
        band_upper = []
        band_lower = []
        half_hdif = c.hot_differential_f / 2.0
        max_x_hot = c.hot_wwsd_f if c.hot_wwsd_enabled else self._x_max_f

        step = 2.0
        x_val = self._x_min_f
        while x_val <= max_x_hot + 0.01:
            clamped_x = min(x_val, max_x_hot)
            target_f = c.compute_hot_target_f(clamped_x)
            if target_f is not None:
                hot_points.append(self._f_to_screen(clamped_x, target_f, rect))
                band_upper.append(self._f_to_screen(clamped_x, target_f + half_hdif, rect))
                band_lower.append(self._f_to_screen(clamped_x, target_f - half_hdif, rect))
            x_val += step

        if len(hot_points) >= 2:
            band_path = QPainterPath()
            band_path.moveTo(band_upper[0])
            for pt in band_upper[1:]:
                band_path.lineTo(pt)
            for pt in reversed(band_lower):
                band_path.lineTo(pt)
            band_path.closeSubpath()
            painter.fillPath(band_path, QColor(249, 115, 22, 36))

            hot_path = QPainterPath()
            hot_path.moveTo(hot_points[0])
            for pt in hot_points[1:]:
                hot_path.lineTo(pt)
            painter.setPen(QPen(QColor("#F97316"), 2.8))
            painter.drawPath(hot_path)

        # 3. Cooling Curve & Differential Band (optional)
        if self.show_cooling_curve:
            cold_points = []
            cband_upper = []
            cband_lower = []
            half_cdif = c.cold_differential_f / 2.0
            min_x_cold = c.cold_cwsd_f if c.cold_cwsd_enabled else self._x_min_f
            x_val = min_x_cold
            while x_val <= self._x_max_f + 0.01:
                clamped_x = max(min_x_cold, min(self._x_max_f, x_val))
                ctarget_f = c.compute_cold_target_f(clamped_x)
                if ctarget_f is not None:
                    cold_points.append(self._f_to_screen(clamped_x, ctarget_f, rect))
                    cband_upper.append(self._f_to_screen(clamped_x, ctarget_f + half_cdif, rect))
                    cband_lower.append(self._f_to_screen(clamped_x, ctarget_f - half_cdif, rect))
                x_val += step

            if len(cold_points) >= 2:
                cband_path = QPainterPath()
                cband_path.moveTo(cband_upper[0])
                for pt in cband_upper[1:]:
                    cband_path.lineTo(pt)
                for pt in reversed(cband_lower):
                    cband_path.lineTo(pt)
                cband_path.closeSubpath()
                painter.fillPath(cband_path, QColor(14, 165, 233, 30))

                cold_path = QPainterPath()
                cold_path.moveTo(cold_points[0])
                for pt in cold_points[1:]:
                    cold_path.lineTo(pt)
                painter.setPen(QPen(QColor("#38BDF8"), 2.2))
                painter.drawPath(cold_path)

        # 4. Live Outdoor & Tank Temperature markers
        if c.current_outdoor_f is not None:
            live_out_pt = self._f_to_screen(c.current_outdoor_f, self._y_min_f, rect)
            painter.setPen(QPen(QColor("#22C55E"), 1.5, Qt.PenStyle.DashDotLine))
            painter.drawLine(QPointF(live_out_pt.x(), rect.top()), QPointF(live_out_pt.x(), rect.bottom()))

            live_target = c.computed_target_f
            if live_target is None:
                live_target = c.compute_hot_target_f(c.current_outdoor_f)
            if live_target is not None:
                t_pt = self._f_to_screen(c.current_outdoor_f, live_target, rect)
                painter.setPen(QPen(QColor("#FFFFFF"), 2.0))
                painter.setBrush(QColor("#22C55E"))
                painter.drawEllipse(t_pt, 6.5, 6.5)

            if c.current_tank_f is not None:
                actual_pt = self._f_to_screen(c.current_outdoor_f, c.current_tank_f, rect)
                painter.setPen(QPen(QColor("#FACC15"), 2.0))
                painter.setBrush(QColor("#EAB308"))
                painter.drawEllipse(actual_pt, 5.0, 5.0)

        painter.restore()

        # Plot border
        painter.setPen(QPen(QColor("#334155"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        # 5. Interactive Draggable Control Handles
        handles = self._get_handles(rect)
        for name, h_pt in handles.items():
            is_hot = name.startswith("hot")
            is_hovered = (name == self._hover_handle) or (name == self._dragging_handle)
            radius = 8.0 if is_hovered else 6.0
            fill = QColor("#FB923C") if is_hot else QColor("#38BDF8")
            painter.setPen(QPen(QColor("#FFFFFF"), 2.0))
            painter.setBrush(fill)
            painter.drawEllipse(h_pt, radius, radius)

        # 6. Hover Crosshair Tooltip
        if self._hover_pos is not None:
            out_f, _ = self._screen_to_f(self._hover_pos, rect)
            hot_t = c.compute_hot_target_f(out_f)
            cold_t = c.compute_cold_target_f(out_f)
            info_parts = [f"Outdoor: {UnitHelper.format_temp(out_f, self.unit, 1)}"]
            if hot_t is not None:
                info_parts.append(f"Hot Target: {UnitHelper.format_temp(hot_t, self.unit, 1)}")
            if self.show_cooling_curve and cold_t is not None:
                info_parts.append(f"Cold Target: {UnitHelper.format_temp(cold_t, self.unit, 1)}")
            banner = "   |   ".join(info_parts)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            painter.setPen(QColor("#E2E8F0"))
            painter.drawText(
                QRectF(rect.left(), 6, rect.width() - 6, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                banner,
            )

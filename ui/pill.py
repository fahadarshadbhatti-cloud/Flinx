"""
ui/pill.py — Frameless always-on-top glassmorphic pill widget for Flinx.

Features:
- Obsidian glassmorphic design (translucent dark obsidian, subtle top-sheen border)
- Non-activating, click-through on Wayland (never steals focus from target window)
- Fluid liquid audio waveform with coral-to-violet gradient
- Vector status icons (pulsing recording dot, spinning arc loader, emerald checkmark)
- State transitions: Recording, Processing, Pasting, Error, Idle
"""

from __future__ import annotations

import sys
import math
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import QWidget, QApplication, QLabel, QHBoxLayout, QVBoxLayout, QGraphicsDropShadowEffect

from flinx import config
from flinx.core import State
from ui import animations


class WaveformBar(QWidget):
    """A fluid animated bar with rounded capsule ends and gradient fill."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(5)
        self.setFixedHeight(28)
        self._level = 0.12  # Normalised [0.0, 1.0]
        self._target_level = 0.12

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_height)
        self.timer.start(16)  # ~60fps

    def set_level(self, level: float) -> None:
        self._target_level = max(0.12, min(level, 1.0))

    def _update_height(self) -> None:
        # Smooth lerp
        self._level += (self._target_level - self._level) * 0.25
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        h = max(4.0, float(self.height()) * self._level)
        y = (float(self.height()) - h) / 2.0

        path = QPainterPath()
        path.addRoundedRect(0.0, y, float(self.width()), h, 2.5, 2.5)

        # Gradient: coral to violet
        grad = QLinearGradient(0, y, 0, y + h)
        grad.setColorAt(0.0, QColor("#F43F5E"))  # Coral
        grad.setColorAt(1.0, QColor("#8B5CF6"))  # Violet

        painter.fillPath(path, QBrush(grad))


class WaveformWidget(QWidget):
    """Container for 5 fluid waveform bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(46)
        self.setFixedHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.bars = [WaveformBar(self) for _ in range(5)]
        for bar in self.bars:
            layout.addWidget(bar)

    def update_level(self, level: float) -> None:
        import random
        for i, bar in enumerate(self.bars):
            factor = 1.0 - abs(2 - i) * 0.22
            noise = random.uniform(0.85, 1.15)
            bar.set_level(level * factor * noise)


class StatusSpinner(QWidget):
    """Antialiased spinning circular arc loader for processing state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)

    def start(self) -> None:
        self._timer.start(16)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _rotate(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(255, 255, 255, 30), 2.5)
        painter.setPen(pen)
        painter.drawEllipse(3, 3, 16, 16)

        pen_arc = QPen(QColor("#6366F1"), 2.5)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(3, 3, 16, 16, self._angle * 16, 110 * 16)


class StatusGlyph(QWidget):
    """Vector checkmark or warning indicator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self._mode: str = "check"  # "check" or "error"

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._mode == "check":
            # Emerald circle with white check
            painter.setBrush(QColor("#10B981"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(1, 1, 20, 20)

            pen = QPen(QColor("#FFFFFF"), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(6.5, 11.5)
            path.lineTo(9.5, 14.5)
            path.lineTo(15.5, 8.0)
            painter.drawPath(path)

        elif self._mode == "error":
            # Amber/crimson circle with exclamation
            painter.setBrush(QColor("#EF4444"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(1, 1, 20, 20)

            pen = QPen(QColor("#FFFFFF"), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(11, 6, 11, 12)
            painter.drawPoint(11, 15)


class FlinxPill(QWidget):
    """The floating voice-to-text pill widget for Flinx."""

    def __init__(self) -> None:
        super().__init__()

        # Configure frameless, always-on-top, non-focusable, and click-through window flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.setFixedSize(390, 60)

        # Set up layouts
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(18, 8, 18, 8)
        self.layout.setSpacing(12)

        # Vector Status Glyph (Checkmark / Error)
        self.status_glyph = StatusGlyph(self)
        self.status_glyph.hide()
        self.layout.addWidget(self.status_glyph)

        # Spinner
        self.spinner = StatusSpinner(self)
        self.spinner.hide()
        self.layout.addWidget(self.spinner)

        # Liquid Waveform
        self.waveform = WaveformWidget(self)
        self.layout.addWidget(self.waveform)

        # Text label (rich details/states)
        self.text_label = QLabel("Listening...", self)
        self.text_label.setStyleSheet(
            "color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif; "
            "font-size: 13.5px; font-weight: 600;"
        )
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.text_label)

        # Setup modern drop shadow for premium depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        # Internal state tracking
        self.current_state = State.IDLE
        self._pulse_alpha = 255
        self._pulse_direction = -1
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)

        # Auto-hide timer for success/error
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_pill)

        # Start hidden
        self.center_on_screen()
        self.hide()

    def center_on_screen(self) -> None:
        """Positions the pill at top-center of the primary monitor."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()

        # Centered horizontally, 44px down from the top
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + 44
        self.move(x, y)

    def transition_to(self, state: State, message: str = "") -> None:
        """Transitions the pill to a new state and triggers corresponding animations."""
        self.current_state = state
        self._pulse_timer.stop()
        self.hide_timer.stop()

        if state == State.IDLE:
            self.spinner.stop()
            self.hide_pill()

        elif state == State.RECORDING:
            self.spinner.stop()
            self.status_glyph.hide()
            self.waveform.show()
            self.text_label.setText(message or "Listening...")
            self.text_label.setStyleSheet("color: #F8FAFC; font-size: 13.5px; font-weight: 600;")
            self._pulse_timer.start(16)
            self.show_pill()

        elif state == State.PROCESSING:
            self.waveform.hide()
            self.status_glyph.hide()
            self.spinner.start()
            self.text_label.setText(message or "Transcribing...")
            self.text_label.setStyleSheet("color: #E2E8F0; font-size: 13.5px; font-weight: 500;")
            self.show_pill()

        elif state == State.PASTING:
            self.waveform.hide()
            self.spinner.stop()
            self.status_glyph.set_mode("check")
            self.status_glyph.show()
            self.text_label.setText(message or "Pasting...")
            self.text_label.setStyleSheet("color: #34D399; font-size: 13.5px; font-weight: 600;")
            self.hide_timer.start(1500)

        elif state == State.ERROR:
            self.waveform.hide()
            self.spinner.stop()
            self.status_glyph.set_mode("error")
            self.status_glyph.show()
            self.text_label.setText(message or "Error")
            self.text_label.setStyleSheet("color: #F87171; font-size: 13px; font-weight: 500;")

            self.shake_anim = animations.shake(self)
            self.shake_anim.start()
            self.hide_timer.start(2500)

        self.update()

    def show_pill(self) -> None:
        self.center_on_screen()
        self.show()

    def hide_pill(self) -> None:
        self.hide()

    def _update_pulse(self) -> None:
        self._pulse_alpha += self._pulse_direction * 6
        if self._pulse_alpha <= 110:
            self._pulse_alpha = 110
            self._pulse_direction = 1
        elif self._pulse_alpha >= 255:
            self._pulse_alpha = 255
            self._pulse_direction = -1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Border color & accent glow based on state
        if self.current_state == State.RECORDING:
            border_color = QColor(244, 63, 94, self._pulse_alpha)  # Coral pulse
            bg_color = QColor(14, 16, 23, 235)
        elif self.current_state == State.PROCESSING:
            border_color = QColor(99, 102, 241, 200)  # Indigo
            bg_color = QColor(14, 16, 23, 235)
        elif self.current_state == State.PASTING:
            border_color = QColor(16, 185, 129, 240)  # Emerald
            bg_color = QColor(10, 20, 16, 235)
        elif self.current_state == State.ERROR:
            border_color = QColor(239, 68, 68, 240)  # Red
            bg_color = QColor(24, 12, 14, 235)
        else:
            border_color = QColor(255, 255, 255, 25)
            bg_color = QColor(14, 16, 23, 230)

        path = QPainterPath()
        path.addRoundedRect(0, 0, float(self.width()), float(self.height()), 18.0, 18.0)

        # Fill background
        painter.fillPath(path, QBrush(bg_color))

        # Stroke border
        pen = QPen(border_color, 1.4)
        painter.setPen(pen)
        painter.drawPath(path)


# Backward compatibility alias
LowenPill = FlinxPill


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pill = FlinxPill()

    states = [
        (State.RECORDING, "Listening to speech..."),
        (State.PROCESSING, "Transcribing with Whisper Turbo..."),
        (State.PASTING, "Pasting text into editor..."),
        (State.ERROR, "Groq API key not configured"),
        (State.IDLE, ""),
    ]

    idx = 0
    def next_state():
        global idx
        if idx >= len(states):
            app.quit()
            return
        state, msg = states[idx]
        pill.transition_to(state, msg)
        idx += 1
        QTimer.singleShot(2600, next_state)

    pill.show()
    QTimer.singleShot(400, next_state)
    sys.exit(app.exec())

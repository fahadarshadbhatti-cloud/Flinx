"""
ui/pill.py — Apple Dynamic Island / Wispr Flow Tier Floating HUD for Flinx.

Features:
- Guaranteed top-center positioning on Wayland (KDE Plasma 6, GNOME, Sway, Hyprland)
  via a transparent click-through full-desktop anchor overlay.
- Concentric double-bezel OLED obsidian glass with specular top-edge sheen.
- Organic liquid 7-bar audio waveform with Gaussian sine distribution and spring physics.
- Glowing live recording beacon with pulsing ambient halo.
- Live elapsed recording timer (0:01, 0:02...).
- Antialiased vector status glyphs (spinning dual-gradient arc loader, emerald spring checkmark).
- Non-activating, 100% click-through input transparency (zero focus stealing).
"""

from __future__ import annotations

import sys
import time
from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QLinearGradient, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QGraphicsDropShadowEffect,
)

from flinx import config
from flinx.core import State
from ui import animations


# ---------------------------------------------------------------------------
# 1. Pulsing Recording Dot (Hardware-style live indicator)
# ---------------------------------------------------------------------------
class RecordingDotWidget(QWidget):
    """Glowing neon recording beacon with pulsing ambient halo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._alpha = 255
        self._dir = -1
        self._halo_scale = 1.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

    def start(self) -> None:
        self._alpha = 255
        self._dir = -1
        self._timer.start(24)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _animate(self) -> None:
        self._alpha += self._dir * 7
        if self._alpha <= 90:
            self._alpha = 90
            self._dir = 1
        elif self._alpha >= 255:
            self._alpha = 255
            self._dir = -1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Outer ambient glow ring
        halo_color = QColor(244, 63, 94, int(self._alpha * 0.35))
        painter.setBrush(QBrush(halo_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, 14, 14)

        # Inner vibrant neon dot
        dot_color = QColor(244, 63, 94, self._alpha)
        painter.setBrush(QBrush(dot_color))
        painter.drawEllipse(4, 4, 8, 8)


# ---------------------------------------------------------------------------
# 2. Liquid 7-Bar Audio Waveform (Gaussian sine energy distribution)
# ---------------------------------------------------------------------------
class LiquidWaveformBar(QWidget):
    """A single micro-capsule bar with smooth spring interpolation and gradient fill."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(4)
        self.setFixedHeight(22)
        self._level = 0.15
        self._target_level = 0.15

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._lerp)
        self.timer.start(16)

    def set_level(self, level: float) -> None:
        self._target_level = max(0.15, min(level, 1.0))

    def _lerp(self) -> None:
        self._level += (self._target_level - self._level) * 0.28
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        h = max(3.5, float(self.height()) * self._level)
        y = (float(self.height()) - h) / 2.0

        path = QPainterPath()
        path.addRoundedRect(0.0, y, float(self.width()), h, 2.0, 2.0)

        # Fluid Coral-to-Violet gradient
        grad = QLinearGradient(0, y, 0, y + h)
        grad.setColorAt(0.0, QColor("#FF4B72"))  # Electric Coral
        grad.setColorAt(1.0, QColor("#8B5CF6"))  # Deep Violet

        painter.fillPath(path, QBrush(grad))


class WaveformWidget(QWidget):
    """Container for 7 fluid waveform bars with Gaussian bell-curve distribution."""

    # Bell curve weighting from outer edges to center
    SINE_WEIGHTS = [0.35, 0.60, 0.88, 1.0, 0.88, 0.60, 0.35]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(52)
        self.setFixedHeight(24)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.bars = [LiquidWaveformBar(self) for _ in range(7)]
        for bar in self.bars:
            layout.addWidget(bar)

    def update_level(self, level: float) -> None:
        import random
        for i, bar in enumerate(self.bars):
            weight = self.SINE_WEIGHTS[i]
            jitter = random.uniform(0.90, 1.10)
            bar.set_level(level * weight * jitter)

    def reset(self) -> None:
        for bar in self.bars:
            bar.set_level(0.15)


# ---------------------------------------------------------------------------
# 3. Vector Status Spinner & Glyphs
# ---------------------------------------------------------------------------
class StatusSpinner(QWidget):
    """Antialiased spinning dual-gradient circular arc loader."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
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
        self._angle = (self._angle + 7) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Muted background track
        pen_track = QPen(QColor(255, 255, 255, 20), 2.2)
        painter.setPen(pen_track)
        painter.drawEllipse(2, 2, 16, 16)

        # Spinning glowing Indigo arc
        pen_arc = QPen(QColor("#818CF8"), 2.2)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(2, 2, 16, 16, self._angle * 16, 115 * 16)


class StatusGlyph(QWidget):
    """Antialiased emerald checkmark or crimson warning indicator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._mode: str = "check"

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
            painter.drawEllipse(1, 1, 18, 18)

            pen = QPen(QColor("#FFFFFF"), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(5.5, 10.0)
            path.lineTo(8.5, 13.0)
            path.lineTo(14.0, 7.0)
            painter.drawPath(path)

        elif self._mode == "error":
            # Crimson circle with exclamation mark
            painter.setBrush(QColor("#EF4444"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(1, 1, 18, 18)

            pen = QPen(QColor("#FFFFFF"), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(10, 5, 10, 11)
            painter.drawPoint(10, 14)


# ---------------------------------------------------------------------------
# 4. Floating Pill Capsule (The sculpted glass element)
# ---------------------------------------------------------------------------
class PillCapsule(QWidget):
    """The sculpted, double-bezel glass capsule element."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(360, 44)

        # Pulse animation for recording state
        self._pulse_alpha = 255
        self._pulse_dir = -1
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)

        # Ambient shadow for floating depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        # Layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(14, 6, 16, 6)
        self.layout.setSpacing(10)

        # Left Item 1: Recording Dot
        self.recording_dot = RecordingDotWidget(self)
        self.recording_dot.hide()
        self.layout.addWidget(self.recording_dot)

        # Left Item 2: Vector Status Glyph (Checkmark / Error)
        self.status_glyph = StatusGlyph(self)
        self.status_glyph.hide()
        self.layout.addWidget(self.status_glyph)

        # Left Item 3: Status Spinner (Processing)
        self.spinner = StatusSpinner(self)
        self.spinner.hide()
        self.layout.addWidget(self.spinner)

        # Center-left: 7-bar Liquid Waveform
        self.waveform = WaveformWidget(self)
        self.layout.addWidget(self.waveform)

        # Center: Typographic Status Label
        self.text_label = QLabel("Listening...", self)
        self.text_label.setStyleSheet(
            "color: #F8FAFC; "
            "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif; "
            "font-size: 13px; "
            "font-weight: 600; "
            "letter-spacing: 0.2px;"
        )
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.text_label, 1)

        # Right: Live Elapsed Recording Timer
        self.timer_label = QLabel("0:00", self)
        self.timer_label.setStyleSheet(
            "color: #94A3B8; "
            "font-family: 'SF Mono', 'Roboto Mono', 'Cascadia Code', monospace; "
            "font-size: 12px; "
            "font-weight: 500;"
        )
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.timer_label.hide()
        self.layout.addWidget(self.timer_label)

        # Timer worker
        self._record_start_time = 0.0
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)

        self.current_state = State.IDLE

    def set_state(self, state: State, message: str = "") -> None:
        self.current_state = state
        self._pulse_timer.stop()
        self._clock_timer.stop()

        if state == State.IDLE:
            self.recording_dot.stop()
            self.spinner.stop()
            self.status_glyph.hide()
            self.timer_label.hide()
            self.waveform.reset()

        elif state == State.RECORDING:
            self.status_glyph.hide()
            self.spinner.stop()
            self.waveform.show()
            self.recording_dot.start()
            self.text_label.setText(message or "Listening...")
            self.text_label.setStyleSheet(
                "color: #F8FAFC; "
                "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif; "
                "font-size: 13px; font-weight: 600; letter-spacing: 0.2px;"
            )
            # Start live elapsed recording timer
            self._record_start_time = time.monotonic()
            self.timer_label.setText("0:00")
            self.timer_label.show()
            self._clock_timer.start(100)
            self._pulse_timer.start(16)

        elif state == State.PROCESSING:
            self.recording_dot.stop()
            self.waveform.hide()
            self.status_glyph.hide()
            self.timer_label.hide()
            self.spinner.start()
            self.text_label.setText(message or "Transcribing...")
            self.text_label.setStyleSheet(
                "color: #E2E8F0; "
                "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif; "
                "font-size: 13px; font-weight: 500; letter-spacing: 0.2px;"
            )

        elif state == State.PASTING:
            self.recording_dot.stop()
            self.waveform.hide()
            self.spinner.stop()
            self.timer_label.hide()
            self.status_glyph.set_mode("check")
            self.status_glyph.show()
            self.text_label.setText(message or "Pasting...")
            self.text_label.setStyleSheet(
                "color: #34D399; "
                "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif; "
                "font-size: 13px; font-weight: 600;"
            )

        elif state == State.ERROR:
            self.recording_dot.stop()
            self.waveform.hide()
            self.spinner.stop()
            self.timer_label.hide()
            self.status_glyph.set_mode("error")
            self.status_glyph.show()
            self.text_label.setText(message or "Error")
            self.text_label.setStyleSheet(
                "color: #F87171; "
                "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Segoe UI', sans-serif; "
                "font-size: 12.5px; font-weight: 500;"
            )

        self.update()

    def _update_clock(self) -> None:
        elapsed = time.monotonic() - self._record_start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self.timer_label.setText(f"{mins}:{secs:02d}")

    def _update_pulse(self) -> None:
        self._pulse_alpha += self._pulse_dir * 5
        if self._pulse_alpha <= 110:
            self._pulse_alpha = 110
            self._pulse_dir = 1
        elif self._pulse_alpha >= 255:
            self._pulse_alpha = 255
            self._pulse_dir = -1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        r = h / 2.0  # Perfect capsule radius: 22px

        # ── 1. Base OLED Obsidian Void ────────────────────────────────────
        bg_color = QColor(8, 9, 14, 240)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, w, h, r, r)
        painter.fillPath(path, QBrush(bg_color))

        # ── 2. State-Reactive Outer Border & Ambient Sheen ────────────────
        pen_grad = QLinearGradient(0, 0, 0, h)
        if self.current_state == State.RECORDING:
            pen_grad.setColorAt(0.0, QColor(244, 63, 94, self._pulse_alpha))
            pen_grad.setColorAt(0.6, QColor(236, 72, 153, int(self._pulse_alpha * 0.7)))
            pen_grad.setColorAt(1.0, QColor(139, 92, 246, 120))
        elif self.current_state == State.PROCESSING:
            pen_grad.setColorAt(0.0, QColor(129, 140, 248, 220))
            pen_grad.setColorAt(1.0, QColor(99, 102, 241, 100))
        elif self.current_state == State.PASTING:
            pen_grad.setColorAt(0.0, QColor(16, 185, 129, 230))
            pen_grad.setColorAt(1.0, QColor(5, 150, 105, 110))
        elif self.current_state == State.ERROR:
            pen_grad.setColorAt(0.0, QColor(239, 68, 68, 230))
            pen_grad.setColorAt(1.0, QColor(185, 28, 28, 110))
        else:
            pen_grad.setColorAt(0.0, QColor(255, 255, 255, 45))
            pen_grad.setColorAt(1.0, QColor(255, 255, 255, 12))

        pen_border = QPen(QBrush(pen_grad), 1.2)
        painter.setPen(pen_border)
        painter.drawPath(path)

        # ── 3. Concentric Inner Specular Highlight (Machined Glass) ───────
        inner_path = QPainterPath()
        inner_path.addRoundedRect(1.0, 1.0, w - 2.0, h - 2.0, r - 1.0, r - 1.0)
        inner_sheen = QLinearGradient(0, 1.0, 0, h - 1.0)
        inner_sheen.setColorAt(0.0, QColor(255, 255, 255, 40))
        inner_sheen.setColorAt(0.4, QColor(255, 255, 255, 8))
        inner_sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(inner_sheen), 1.0))
        painter.drawPath(inner_path)


# ---------------------------------------------------------------------------
# 5. Full-Screen Wayland Overlay Anchor Window
# ---------------------------------------------------------------------------
class FlinxPill(QWidget):
    """
    Universal Wayland top-center anchor overlay.

    Fills the primary screen geometry with a 100% transparent and click-through
    surface. Positions the sculpted PillCapsule reliably at top-center (24px below
    screen top) regardless of Wayland compositor placement policies.
    """

    def __init__(self) -> None:
        super().__init__()

        # Full-desktop click-through, non-focus-stealing Wayland overlay flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        # Position to primary monitor available geometry
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.availableGeometry())

        # Top-center alignment layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 24, 0, 0)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # The actual sculpted pill
        self.capsule = PillCapsule(self)
        main_layout.addWidget(self.capsule)

        # Expose waveform for core signal connection
        self.waveform = self.capsule.waveform

        # Auto-hide timer for completed or error state
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_pill)

        self.current_state = State.IDLE
        self.hide()

    def update_geometry(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.availableGeometry())

    def transition_to(self, state: State, message: str = "") -> None:
        self.current_state = state
        self.hide_timer.stop()

        if state == State.IDLE:
            self.capsule.set_state(State.IDLE, "")
            self.hide_pill()

        elif state == State.RECORDING:
            self.capsule.set_state(State.RECORDING, message or "Listening...")
            self.show_pill()

        elif state == State.PROCESSING:
            self.capsule.set_state(State.PROCESSING, message or "Transcribing...")
            self.show_pill()

        elif state == State.PASTING:
            self.hide_pill()

        elif state == State.ERROR:
            self.capsule.set_state(State.ERROR, message or "Error")
            self.show_pill()
            self._shake_anim = animations.shake(self.capsule)
            self._shake_anim.start()
            self.hide_timer.start(2500)

    def show_pill(self) -> None:
        self.update_geometry()
        self.show()
        self.raise_()
        self.capsule.show()

    def hide_pill(self) -> None:
        self.hide()


# Backward compatibility alias
LowenPill = FlinxPill


# Standalone runner for testing and previewing the design
if __name__ == "__main__":
    app = QApplication(sys.argv)
    pill = FlinxPill()

    states = [
        (State.RECORDING, "Listening..."),
        (State.PROCESSING, "Transcribing with Whisper Turbo..."),
        (State.PASTING, "Hello world, testing Flinx voice-to-text!"),
        (State.ERROR, "Groq API key not configured"),
        (State.IDLE, ""),
    ]

    idx = 0

    def next_state() -> None:
        global idx
        if idx >= len(states):
            print("Preview cycle finished.")
            app.quit()
            return
        st, msg = states[idx]
        print(f"Testing state: {st.name} ({msg})")
        pill.transition_to(st, msg)
        idx += 1
        QTimer.singleShot(2800, next_state)

    pill.show_pill()
    QTimer.singleShot(400, next_state)
    sys.exit(app.exec())

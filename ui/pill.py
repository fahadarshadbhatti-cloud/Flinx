"""
ui/pill.py — Frameless always-on-top pill widget using PyQt6.

Features:
- Glassmorphism design (rounded corners, dark translucent background, subtle border)
- 5 states: Hidden, Recording, Processing, Success, Error
- Real-time animated audio waveform (5 bars) driven by recorder level
- Custom state rendering and animations (fade in/out, shake, slide)
"""

from __future__ import annotations

import sys
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPainterPath
from PyQt6.QtWidgets import QWidget, QApplication, QLabel, QHBoxLayout, QVBoxLayout, QGraphicsDropShadowEffect

from lowen import config
from lowen.core import State
from ui import animations


class WaveformBar(QWidget):
    """A single animated bar in the waveform visualization."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(4)
        self.setFixedHeight(24)
        self._level = 0.1  # Normalised [0.0, 1.0]
        self._target_level = 0.1
        self._color = QColor(255, 60, 60) # Default red for recording

        # Smooth animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_height)
        self.timer.start(16)  # ~60fps

    def set_level(self, level: float) -> None:
        # Prevent absolute zero to keep a small bar visible
        self._target_level = max(0.1, min(level, 1.0))

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def _update_height(self) -> None:
        # Linear interpolation to smooth out rapid level changes
        self._level += (self._target_level - self._level) * 0.2
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate height based on level
        h = int(self.height() * self._level)
        y = (self.height() - h) // 2
        
        path = QPainterPath()
        path.addRoundedRect(0, float(y), float(self.width()), float(h), 2.0, 2.0)
        
        painter.fillPath(path, QBrush(self._color))


class WaveformWidget(QWidget):
    """Container for 5 waveform bars that bounce with input levels."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(40)
        self.setFixedHeight(30)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        
        self.bars = [WaveformBar(self) for _ in range(5)]
        for bar in self.bars:
            layout.addWidget(bar)
            
    def update_level(self, level: float) -> None:
        # Distribute the level with slight variation across bars to look natural
        import random
        for i, bar in enumerate(self.bars):
            # Middle bar responds directly, outer bars respond with slight delay/attenuation
            factor = 1.0 - abs(2 - i) * 0.2
            noise = random.uniform(0.8, 1.2)
            bar.set_level(level * factor * noise)

    def set_color(self, color: QColor) -> None:
        for bar in self.bars:
            bar.set_color(color)


class LowenPill(QWidget):
    """The floating voice-to-text pill widget."""
    
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
        
        self.setFixedSize(380, 64)
        
        # Set up layouts
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 8, 15, 8)
        self.layout.setSpacing(12)
        
        # Icon / Waveform area
        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.icon_label)
        
        self.waveform = WaveformWidget(self)
        self.waveform.hide()
        self.layout.addWidget(self.waveform)
        
        # Text label (rich details/states)
        self.text_label = QLabel("Ready", self)
        self.text_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 500;")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.text_label)
        
        # Setup modern drop shadow for premium depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
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
        
        # Start completely hidden but pre-mapped to avoid focus-stealing map events
        self.setWindowOpacity(0.0)
        self.center_on_screen()
        self.show()

    def center_on_screen(self) -> None:
        """Positions the pill at top-center of the primary monitor."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        
        # Centered horizontally, 40px down from the top
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + 40
        self.move(x, y)

    def transition_to(self, state: State, message: str = "") -> None:
        """Transitions the pill to a new state and triggers corresponding animations."""
        self.current_state = state
        self._pulse_timer.stop()
        self.hide_timer.stop()
        
        # Reset colors and elements based on state
        if state == State.IDLE:
            # We fade out on IDLE transition if not already hidden
            self.hide_pill()
            
        elif state == State.RECORDING:
            self.text_label.setText(message or "Recording...")
            self.text_label.setStyleSheet("color: #FF7878; font-size: 14px; font-weight: 600;")
            self.icon_label.hide()
            self.waveform.set_color(QColor(255, 70, 70))
            self.waveform.show()
            self._pulse_timer.start(16) # Fast pulse for recording
            self.show_pill()
            
        elif state == State.PROCESSING:
            self.text_label.setText(message or "Processing...")
            self.text_label.setStyleSheet("color: #FFE082; font-size: 14px; font-weight: 500;")
            self.waveform.hide()
            self.icon_label.setText("⏳")
            self.icon_label.setStyleSheet("font-size: 16px;")
            self.icon_label.show()
            self.show_pill()
            
        elif state == State.PASTING:
            self.text_label.setText(message or "Pasting...")
            self.text_label.setStyleSheet("color: #81C784; font-size: 14px; font-weight: 600;")
            self.waveform.hide()
            self.icon_label.setText("✓")
            self.icon_label.setStyleSheet("color: #81C784; font-size: 18px; font-weight: bold;")
            self.icon_label.show()
            # Remain visible for 1.5s then fade out
            self.hide_timer.start(1500)
            
        elif state == State.ERROR:
            self.text_label.setText(message or "Error")
            self.text_label.setStyleSheet("color: #E57373; font-size: 13px; font-weight: 500;")
            self.waveform.hide()
            self.icon_label.setText("⚠️")
            self.icon_label.setStyleSheet("font-size: 16px;")
            self.icon_label.show()
            
            # Shake effect to grab attention
            self.shake_anim = animations.shake(self)
            self.shake_anim.start()
            
            # Stay visible for 2.5s then fade out
            self.hide_timer.start(2500)
            
        self.update()

    def show_pill(self) -> None:
        if self.windowOpacity() < 1.0:
            self.fade_anim = animations.fade_in(self, 150)
            self.fade_anim.start()

    def hide_pill(self) -> None:
        if self.windowOpacity() > 0.0:
            self.fade_anim = animations.fade_out(self, 250)
            self.fade_anim.start()

    def _update_pulse(self) -> None:
        # Pulsing opacity effect for recording border/glow
        self._pulse_alpha += self._pulse_direction * 6
        if self._pulse_alpha <= 100:
            self._pulse_alpha = 100
            self._pulse_direction = 1
        elif self._pulse_alpha >= 255:
            self._pulse_alpha = 255
            self._pulse_direction = -1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Border color based on current state
        if self.current_state == State.RECORDING:
            border_color = QColor(255, 60, 60, self._pulse_alpha)
            bg_color = QColor(20, 10, 10, 230)
        elif self.current_state == State.PROCESSING:
            border_color = QColor(255, 160, 0, 200)
            bg_color = QColor(20, 18, 10, 230)
        elif self.current_state == State.PASTING:
            border_color = QColor(76, 175, 80, 255)
            bg_color = QColor(10, 20, 12, 230)
        elif self.current_state == State.ERROR:
            border_color = QColor(244, 67, 54, 255)
            bg_color = QColor(25, 10, 10, 235)
        else:
            border_color = QColor(255, 255, 255, 40)
            bg_color = QColor(18, 18, 18, 220)

        # Draw glassmorphic pill body
        path = QPainterPath()
        path.addRoundedRect(0, 0, float(self.width()), float(self.height()), 18.0, 18.0)
        
        # Fill background
        painter.fillPath(path, QBrush(bg_color))
        
        # Stroke border
        pen = QPen(border_color, 1.5)
        painter.setPen(pen)
        painter.drawPath(path)


if __name__ == "__main__":
    # Test script to preview the UI design directly
    app = QApplication(sys.argv)
    pill = LowenPill()
    
    # State switching rotation for validation
    states = [
        (State.RECORDING, "Recording voice input..."),
        (State.PROCESSING, "Transcribing with Whisper..."),
        (State.PASTING, "Transcribing finished, pasting into field"),
        (State.ERROR, "Groq API key invalid. Please configure key."),
        (State.IDLE, "")
    ]
    
    idx = 0
    def next_state():
        global idx
        if idx >= len(states):
            app.quit()
            return
        state, msg = states[idx]
        print(f"Testing state: {state.name}")
        pill.transition_to(state, msg)
        idx += 1
        # Set next transition delay
        QTimer.singleShot(3000, next_state)

    pill.show()
    QTimer.singleShot(500, next_state)
    sys.exit(app.exec())

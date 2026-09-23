"""
ui/control_center.py — Flinx Obsidian Control Center GUI

Modern, dark-themed configuration dashboard and first-run onboarding setup for Flinx.
Provides live Groq API key testing, interactive microphone VU meter, hotkey binding,
AI post-processing settings, and one-click Polkit permission assistance.
"""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QBrush, QLinearGradient, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import sounddevice as sd
import numpy as np

from flinx import config

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"


# ---------------------------------------------------------------------------
# Stylesheet: Obsidian Studio Dark Theme
# ---------------------------------------------------------------------------
OBSIDIAN_STYLE = """
QWidget {
    background-color: #0E1017;
    color: #E2E8F0;
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
}

QFrame#sidebar {
    background-color: #090A0E;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}

QPushButton.nav-btn {
    text-align: left;
    padding: 10px 14px;
    border-radius: 8px;
    font-weight: 500;
    font-size: 13px;
    color: #94A3B8;
    background-color: transparent;
    border: none;
}

QPushButton.nav-btn:hover {
    background-color: rgba(255, 255, 255, 0.04);
    color: #F8FAFC;
}

QPushButton.nav-btn:checked {
    background-color: rgba(99, 102, 241, 0.15);
    color: #818CF8;
    font-weight: 600;
    border-left: 3px solid #6366F1;
}

QFrame.card {
    background-color: #141722;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 12px;
    padding: 16px;
}

QLabel.card-title {
    font-size: 14px;
    font-weight: 600;
    color: #F8FAFC;
    background: transparent;
}

QLabel.card-desc {
    font-size: 12px;
    color: #64748B;
    background: transparent;
}

QLineEdit, QComboBox, QTextEdit {
    background-color: #0B0D13;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 8px 12px;
    color: #F8FAFC;
    selection-background-color: #6366F1;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #6366F1;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QPushButton.primary-btn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #8B5CF6);
    color: #FFFFFF;
    font-weight: 600;
    padding: 9px 18px;
    border-radius: 8px;
    border: none;
}

QPushButton.primary-btn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #7C3AED);
}

QPushButton.secondary-btn {
    background-color: #1E2230;
    color: #CBD5E1;
    font-weight: 500;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.08);
}

QPushButton.secondary-btn:hover {
    background-color: #282E40;
    color: #FFFFFF;
}

QCheckBox {
    spacing: 8px;
    background: transparent;
    color: #E2E8F0;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background-color: #0B0D13;
}

QCheckBox::indicator:checked {
    background-color: #6366F1;
    border: 1px solid #6366F1;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #1E2230;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #6366F1;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 2px solid #6366F1;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}
"""


# ---------------------------------------------------------------------------
# Background Worker: Test Groq Connection
# ---------------------------------------------------------------------------
class PingWorker(QThread):
    ping_result = pyqtSignal(bool, str, int)  # (success, message, latency_ms)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self.api_key = api_key

    def run(self) -> None:
        if not self.api_key or not self.api_key.startswith("gsk_"):
            self.ping_result.emit(False, "API key must start with 'gsk_'", 0)
            return

        t0 = time.monotonic()
        try:
            from groq import Groq
            client = Groq(api_key=self.api_key, timeout=6.0)
            # Query models endpoint to test validity & latency
            _ = client.models.list()
            latency = int((time.monotonic() - t0) * 1000)
            self.ping_result.emit(True, f"Connected ({latency}ms)", latency)
        except Exception as e:
            err_msg = str(e)
            if "401" in err_msg or "invalid_api_key" in err_msg:
                self.ping_result.emit(False, "Invalid API Key", 0)
            else:
                self.ping_result.emit(False, f"Connection Error: {err_msg[:40]}", 0)


# ---------------------------------------------------------------------------
# Widget: Live Microphone VU / Audio Level Meter
# ---------------------------------------------------------------------------
class AudioVUMeter(QWidget):
    """Real-time animated audio level bar powered by sounddevice."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(14)
        self._level = 0.05
        self._target_level = 0.05
        self._stream: sd.InputStream | None = None

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._step_anim)
        self._anim_timer.start(20)  # 50 fps

    def start_listening(self, device: str | int | None = None) -> None:
        self.stop_listening()
        try:
            dev = None if device == "default" else device
            self._stream = sd.InputStream(
                channels=1,
                samplerate=16000,
                dtype="int16",
                device=dev,
                blocksize=1024,
                callback=self._audio_cb,
            )
            self._stream.start()
        except Exception as e:
            print(f"[flinx] VU meter preview error: {e}", file=sys.stderr)

    def stop_listening(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._target_level = 0.05

    def _audio_cb(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        chunk = indata.astype(np.float32)
        rms = float(np.sqrt(np.mean(chunk**2)))
        # Map 0..32768 to 0.05..1.0
        val = min(rms / 32768.0 * 7.5, 1.0)
        self._target_level = max(0.05, val)

    def _step_anim(self) -> None:
        # Smooth lerp
        self._level += (self._target_level - self._level) * 0.25
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Track background
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0, 0, float(self.width()), float(self.height()), 6.0, 6.0)
        painter.fillPath(bg_path, QColor("#090A0F"))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        painter.drawPath(bg_path)

        # Active Level Fill
        fill_width = int(self.width() * self._level)
        if fill_width > 4:
            fill_path = QPainterPath()
            fill_path.addRoundedRect(1, 1, float(fill_width - 2), float(self.height() - 2), 5.0, 5.0)

            grad = QLinearGradient(0, 0, float(self.width()), 0)
            grad.setColorAt(0.0, QColor("#10B981"))  # Green
            grad.setColorAt(0.65, QColor("#F59E0B")) # Yellow
            grad.setColorAt(0.95, QColor("#EF4444")) # Red
            painter.fillPath(fill_path, QBrush(grad))


# ---------------------------------------------------------------------------
# Main Window: Flinx Control Center
# ---------------------------------------------------------------------------
class FlinxControlCenter(QWidget):
    """The master settings dashboard and onboarding GUI for Flinx."""

    settings_applied = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flinx Control Center")
        self.setFixedSize(820, 580)
        self.setStyleSheet(OBSIDIAN_STYLE)

        icon_path = RESOURCES_DIR / "icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._ping_worker: PingWorker | None = None

        self._build_ui()
        self._load_current_settings()

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Left Sidebar ──────────────────────────────────────────────────
        sidebar = QFrame(self)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 24, 16, 20)
        sb_layout.setSpacing(6)

        # App Brand Header
        brand_layout = QHBoxLayout()
        logo_label = QLabel("🎙️", sidebar)
        logo_label.setStyleSheet("font-size: 22px; background: transparent;")
        brand_text = QLabel("Flinx", sidebar)
        brand_text.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF; background: transparent;")
        brand_layout.addWidget(logo_label)
        brand_layout.addWidget(brand_text)
        brand_layout.addStretch()
        sb_layout.addLayout(brand_layout)

        subtitle = QLabel("Voice-to-Text for Wayland", sidebar)
        subtitle.setStyleSheet("font-size: 11px; color: #64748B; margin-bottom: 14px; background: transparent;")
        sb_layout.addWidget(subtitle)

        # Navigation Buttons
        self.nav_buttons: list[QPushButton] = []
        nav_items = [
            ("🚀  General & Key", 0),
            ("🎙️  Voice & Audio", 1),
            ("⌨️  Shortcuts", 2),
            ("🧠  AI Engine", 3),
            ("🛠️  System Check", 4),
        ]

        for text, idx in nav_items:
            btn = QPushButton(text, sidebar)
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, i=idx: self._switch_tab(i))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sb_layout.addStretch()

        # Version tag
        version_label = QLabel(f"v{config.__dict__.get('__version__', '0.2.0')}", sidebar)
        version_label.setStyleSheet("color: #475569; font-size: 11px; background: transparent;")
        sb_layout.addWidget(version_label)

        main_layout.addWidget(sidebar)

        # ── Right Content Container with Persistent Footer ─────────────────
        content_panel = QWidget(self)
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.stack = QStackedWidget(content_panel)
        content_layout.addWidget(self.stack, 1)

        self.stack.addWidget(self._create_tab_general())
        self.stack.addWidget(self._create_tab_audio())
        self.stack.addWidget(self._create_tab_shortcuts())
        self.stack.addWidget(self._create_tab_ai())
        self.stack.addWidget(self._create_tab_system())

        # Global Bottom Bar (available across all tabs)
        footer = QFrame(content_panel)
        footer.setStyleSheet("background-color: #090A0E; border-top: 1px solid rgba(255, 255, 255, 0.06);")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 14)
        footer_layout.setSpacing(12)

        self.lbl_save_status = QLabel("", footer)
        self.lbl_save_status.setStyleSheet("color: #10B981; font-weight: 500; font-size: 13px;")

        btn_close = QPushButton("Minimize to Tray", footer)
        btn_close.setProperty("class", "secondary-btn")
        btn_close.clicked.connect(self.close)

        btn_save = QPushButton("Save & Apply Settings", footer)
        btn_save.setProperty("class", "primary-btn")
        btn_save.clicked.connect(self._save_all_settings)

        footer_layout.addWidget(self.lbl_save_status)
        footer_layout.addStretch()
        footer_layout.addWidget(btn_close)
        footer_layout.addWidget(btn_save)

        content_layout.addWidget(footer)
        main_layout.addWidget(content_panel, 1)

        # Select first tab by default
        self._switch_tab(0)

    def _switch_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

        # Activate mic VU meter only when audio tab is visible to save battery/CPU
        if index == 1:
            dev = self.mic_combo.currentData()
            self.vu_meter.start_listening(dev)
        else:
            self.vu_meter.stop_listening()

    # ──────────────────────────────────────────────────────────────────────
    # TAB 1: General & Setup
    # ──────────────────────────────────────────────────────────────────────
    def _create_tab_general(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(18)

        # Title
        title = QLabel("General Configuration", page)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(title)

        # Card 1: Groq API Key
        card_api = QFrame(page)
        card_api.setProperty("class", "card")
        api_layout = QVBoxLayout(card_api)
        api_layout.setSpacing(8)

        api_title = QLabel("Groq Cloud API Key", card_api)
        api_title.setProperty("class", "card-title")
        api_desc = QLabel(
            "Flinx uses Groq's high-speed LPU Whisper Large v3 Turbo engine (~350ms dictation). "
            "Get your free API key at console.groq.com.",
            card_api,
        )
        api_desc.setProperty("class", "card-desc")
        api_desc.setWordWrap(True)

        api_input_layout = QHBoxLayout()
        self.api_key_input = QLineEdit(card_api)
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

        self.btn_show_key = QPushButton("👁️", card_api)
        self.btn_show_key.setProperty("class", "secondary-btn")
        self.btn_show_key.setFixedWidth(40)
        self.btn_show_key.clicked.connect(self._toggle_key_visibility)

        self.btn_test_key = QPushButton("Test Connection", card_api)
        self.btn_test_key.setProperty("class", "secondary-btn")
        self.btn_test_key.clicked.connect(self._ping_groq_key)

        btn_get_key = QPushButton("Get Free Key ↗", card_api)
        btn_get_key.setProperty("class", "secondary-btn")
        btn_get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://console.groq.com/keys")))

        api_input_layout.addWidget(self.api_key_input)
        api_input_layout.addWidget(self.btn_show_key)
        api_input_layout.addWidget(self.btn_test_key)
        api_input_layout.addWidget(btn_get_key)

        self.lbl_ping_status = QLabel("", card_api)
        self.lbl_ping_status.setStyleSheet("font-size: 12px; font-weight: 500;")

        api_layout.addWidget(api_title)
        api_layout.addWidget(api_desc)
        api_layout.addLayout(api_input_layout)
        api_layout.addWidget(self.lbl_ping_status)
        layout.addWidget(card_api)

        # Card 2: Desktop Integration
        card_desk = QFrame(page)
        card_desk.setProperty("class", "card")
        desk_layout = QVBoxLayout(card_desk)
        desk_layout.setSpacing(12)

        desk_title = QLabel("Desktop Experience", card_desk)
        desk_title.setProperty("class", "card-title")

        self.chk_autostart = QCheckBox("Launch Flinx automatically on desktop login (Systemd user service)", card_desk)
        self.chk_show_pill = QCheckBox("Show floating glassmorphic pill overlay during dictation", card_desk)

        desk_layout.addWidget(desk_title)
        desk_layout.addWidget(self.chk_autostart)
        desk_layout.addWidget(self.chk_show_pill)
        layout.addWidget(card_desk)

        layout.addStretch()
        return page

    # ──────────────────────────────────────────────────────────────────────
    # TAB 2: Voice & Audio
    # ──────────────────────────────────────────────────────────────────────
    def _create_tab_audio(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(18)

        title = QLabel("Voice & Microphone Settings", page)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(title)

        # Card: Microphone Selection & Live Meter
        card_mic = QFrame(page)
        card_mic.setProperty("class", "card")
        mic_layout = QVBoxLayout(card_mic)
        mic_layout.setSpacing(12)

        mic_title = QLabel("Active Microphone", card_mic)
        mic_title.setProperty("class", "card-title")
        mic_desc = QLabel("Speak into your mic to verify the input level in the live meter below.", card_mic)
        mic_desc.setProperty("class", "card-desc")

        self.mic_combo = QComboBox(card_mic)
        self._populate_microphones()
        self.mic_combo.currentIndexChanged.connect(self._on_mic_changed)

        self.vu_meter = AudioVUMeter(card_mic)

        mic_layout.addWidget(mic_title)
        mic_layout.addWidget(mic_desc)
        mic_layout.addWidget(self.mic_combo)
        mic_layout.addWidget(self.vu_meter)
        layout.addWidget(card_mic)

        # Card: Audio Feedback & Duration
        card_audio = QFrame(page)
        card_audio.setProperty("class", "card")
        audio_layout = QVBoxLayout(card_audio)
        audio_layout.setSpacing(12)

        audio_title = QLabel("Acoustic Clicks & Filters", card_audio)
        audio_title.setProperty("class", "card-title")

        self.chk_sound = QCheckBox("Play subtle click sounds on recording start and stop", card_audio)

        slider_layout = QVBoxLayout()
        self.lbl_duration = QLabel(f"Minimum speech duration: {config.MIN_RECORDING_DURATION:.1f}s", card_audio)
        self.lbl_duration.setStyleSheet("font-size: 12px; color: #CBD5E1;")

        self.slider_duration = QSlider(Qt.Orientation.Horizontal, card_audio)
        self.slider_duration.setRange(1, 10)  # 0.1s to 1.0s
        self.slider_duration.setValue(int(config.MIN_RECORDING_DURATION * 10))
        self.slider_duration.valueChanged.connect(
            lambda v: self.lbl_duration.setText(f"Minimum speech duration: {v/10:.1f}s (shorter clicks are ignored)")
        )
        slider_layout.addWidget(self.lbl_duration)
        slider_layout.addWidget(self.slider_duration)

        audio_layout.addWidget(audio_title)
        audio_layout.addWidget(self.chk_sound)
        audio_layout.addLayout(slider_layout)
        layout.addWidget(card_audio)

        layout.addStretch()
        return page

    # ──────────────────────────────────────────────────────────────────────
    # TAB 3: Shortcuts
    # ──────────────────────────────────────────────────────────────────────
    def _create_tab_shortcuts(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(18)

        title = QLabel("Global Hotkey Shortcuts", page)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(title)

        card_hotkey = QFrame(page)
        card_hotkey.setProperty("class", "card")
        hk_layout = QVBoxLayout(card_hotkey)
        hk_layout.setSpacing(12)

        hk_title = QLabel("Push-to-Talk Shortcut", card_hotkey)
        hk_title.setProperty("class", "card-title")
        hk_desc = QLabel(
            "Hold the trigger shortcut, speak into your mic, and release. "
            "Text is immediately pasted into your active application.",
            card_hotkey,
        )
        hk_desc.setProperty("class", "card-desc")
        hk_desc.setWordWrap(True)

        self.hotkey_combo = QComboBox(card_hotkey)
        self.hotkey_combo.addItem("Dual Shift (Left Shift + Right Shift) [Recommended]", "KEY_LEFTSHIFT+KEY_RIGHTSHIFT")
        self.hotkey_combo.addItem("Right Alt (AltGr)", "KEY_RIGHTALT")
        self.hotkey_combo.addItem("Right Control", "KEY_RIGHTCTRL")
        self.hotkey_combo.addItem("Left Alt + Right Alt", "KEY_LEFTALT+KEY_RIGHTALT")

        hk_layout.addWidget(hk_title)
        hk_layout.addWidget(hk_desc)
        hk_layout.addWidget(self.hotkey_combo)
        layout.addWidget(card_hotkey)

        card_mode = QFrame(page)
        card_mode.setProperty("class", "card")
        mode_layout = QVBoxLayout(card_mode)
        mode_layout.setSpacing(8)

        mode_title = QLabel("Dictation Trigger Mode", card_mode)
        mode_title.setProperty("class", "card-title")
        mode_desc = QLabel("Push-to-Talk (hold down while speaking) is recommended for lightning speed.", card_mode)
        mode_desc.setProperty("class", "card-desc")

        self.mode_combo = QComboBox(card_mode)
        self.mode_combo.addItem("Push-to-Talk (Hold to speak, release to paste)", "hold")
        self.mode_combo.setEnabled(False)  # Future toggle support

        mode_layout.addWidget(mode_title)
        mode_layout.addWidget(mode_desc)
        mode_layout.addWidget(self.mode_combo)
        layout.addWidget(card_mode)

        layout.addStretch()
        return page

    # ──────────────────────────────────────────────────────────────────────
    # TAB 4: AI Engine & Vocabulary
    # ──────────────────────────────────────────────────────────────────────
    def _create_tab_ai(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(18)

        title = QLabel("AI & Language Model Settings", page)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(title)

        card_ai = QFrame(page)
        card_ai.setProperty("class", "card")
        ai_layout = QVBoxLayout(card_ai)
        ai_layout.setSpacing(12)

        ai_title = QLabel("Spoken Language", card_ai)
        ai_title.setProperty("class", "card-title")

        self.lang_combo = QComboBox(card_ai)
        languages = [
            ("English", "en"),
            ("Auto-Detect Language", ""),
            ("Spanish", "es"),
            ("French", "fr"),
            ("German", "de"),
            ("Arabic", "ar"),
            ("Urdu", "ur"),
            ("Chinese", "zh"),
            ("Japanese", "ja"),
        ]
        for name, code in languages:
            self.lang_combo.addItem(name, code)

        self.chk_llm_clean = QCheckBox(
            "AI Post-Processing: Strip filler words ('um', 'uh') & polish punctuation via Groq Llama 3.1 8B",
            card_ai,
        )

        ai_layout.addWidget(ai_title)
        ai_layout.addWidget(self.lang_combo)
        ai_layout.addWidget(self.chk_llm_clean)
        layout.addWidget(card_ai)

        card_prompt = QFrame(page)
        card_prompt.setProperty("class", "card")
        prompt_layout = QVBoxLayout(card_prompt)
        prompt_layout.setSpacing(8)

        prompt_title = QLabel("Custom Vocabulary & Context Prompt", card_prompt)
        prompt_title.setProperty("class", "card-title")
        prompt_desc = QLabel(
            "Add personal names, acronyms, or technical keywords to hint Whisper's spelling.",
            card_prompt,
        )
        prompt_desc.setProperty("class", "card-desc")

        self.prompt_text = QLineEdit(card_prompt)
        self.prompt_text.setPlaceholderText("e.g. Flinx, Wayland, PyQt6, Kubernetes, Fahad")

        prompt_layout.addWidget(prompt_title)
        prompt_layout.addWidget(prompt_desc)
        prompt_layout.addWidget(self.prompt_text)
        layout.addWidget(card_prompt)

        layout.addStretch()
        return page

    # ──────────────────────────────────────────────────────────────────────
    # TAB 5: System & Diagnostics
    # ──────────────────────────────────────────────────────────────────────
    def _create_tab_system(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.setSpacing(18)

        title = QLabel("System Diagnostics & Permissions", page)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(title)

        card_diag = QFrame(page)
        card_diag.setProperty("class", "card")
        diag_layout = QVBoxLayout(card_diag)
        diag_layout.setSpacing(10)

        diag_title = QLabel("Wayland Environment Status", card_diag)
        diag_title.setProperty("class", "card-title")

        self.lbl_diag_input = QLabel("Checking...", card_diag)
        self.lbl_diag_ydotool = QLabel("Checking...", card_diag)
        self.lbl_diag_wlcopy = QLabel("Checking...", card_diag)

        diag_layout.addWidget(diag_title)
        diag_layout.addWidget(self.lbl_diag_input)
        diag_layout.addWidget(self.lbl_diag_ydotool)
        diag_layout.addWidget(self.lbl_diag_wlcopy)
        layout.addWidget(card_diag)

        # Polkit Fixer
        card_polkit = QFrame(page)
        card_polkit.setProperty("class", "card")
        polkit_layout = QVBoxLayout(card_polkit)
        polkit_layout.setSpacing(8)

        polkit_title = QLabel("Permission Assistant", card_polkit)
        polkit_title.setProperty("class", "card-title")
        polkit_desc = QLabel(
            "If global shortcuts aren't registering, your Linux user may need to be added to the kernel 'input' group. "
            "Click below to authorize via desktop password prompt without using the terminal.",
            card_polkit,
        )
        polkit_desc.setProperty("class", "card-desc")
        polkit_desc.setWordWrap(True)

        self.btn_polkit_fix = QPushButton("Fix Input Permissions (Polkit)", card_polkit)
        self.btn_polkit_fix.setProperty("class", "secondary-btn")
        self.btn_polkit_fix.clicked.connect(self._run_polkit_fix)

        polkit_layout.addWidget(polkit_title)
        polkit_layout.addWidget(polkit_desc)
        polkit_layout.addWidget(self.btn_polkit_fix)
        layout.addWidget(card_polkit)

        layout.addStretch()

        btn_refresh = QPushButton("Re-run Diagnostics", page)
        btn_refresh.setProperty("class", "secondary-btn")
        btn_refresh.clicked.connect(self._check_diagnostics)
        layout.addWidget(btn_refresh)

        # Initial check
        self._check_diagnostics()

        return page

    # ──────────────────────────────────────────────────────────────────────
    # Logic & Event Handlers
    # ──────────────────────────────────────────────────────────────────────
    def _load_current_settings(self) -> None:
        self.api_key_input.setText(config.GROQ_API_KEY)
        self.chk_show_pill.setChecked(config.SHOW_PILL)
        self.chk_sound.setChecked(config.SOUND_FEEDBACK)
        self.chk_llm_clean.setChecked(config.LLM_CLEAN)
        self.prompt_text.setText(config.TRANSCRIPTION_PROMPT)

        # Check autostart service
        res = subprocess.run(
            ["systemctl", "--user", "is-enabled", "flinx"],
            capture_output=True,
            text=True,
        )
        self.chk_autostart.setChecked("enabled" in res.stdout)

        # Set hotkey
        idx = self.hotkey_combo.findData(config.HOTKEY)
        if idx >= 0:
            self.hotkey_combo.setCurrentIndex(idx)

        # Set language
        l_idx = self.lang_combo.findData(config.LANGUAGE)
        if l_idx >= 0:
            self.lang_combo.setCurrentIndex(l_idx)

    def _populate_microphones(self) -> None:
        self.mic_combo.clear()
        self.mic_combo.addItem("Default System Microphone", "default")
        try:
            devices = sd.query_devices()
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", f"Microphone {idx}")
                    self.mic_combo.addItem(f"{name} (#{idx})", idx)
        except Exception:
            pass

    def _on_mic_changed(self) -> None:
        dev = self.mic_combo.currentData()
        self.vu_meter.start_listening(dev)

    def _toggle_key_visibility(self) -> None:
        if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

    def _ping_groq_key(self) -> None:
        key = self.api_key_input.text().strip()
        self.lbl_ping_status.setText("Testing connection to Groq Cloud...")
        self.lbl_ping_status.setStyleSheet("color: #94A3B8;")
        self.btn_test_key.setEnabled(False)

        self._ping_worker = PingWorker(key)
        self._ping_worker.ping_result.connect(self._on_ping_result)
        self._ping_worker.start()

    def _on_ping_result(self, success: bool, message: str, latency: int) -> None:
        self.btn_test_key.setEnabled(True)
        if success:
            self.lbl_ping_status.setText(f"✓ {message}")
            self.lbl_ping_status.setStyleSheet("color: #10B981; font-weight: 600;")
        else:
            self.lbl_ping_status.setText(f"✗ {message}")
            self.lbl_ping_status.setStyleSheet("color: #EF4444; font-weight: 600;")

    def _check_diagnostics(self) -> None:
        # Input group
        try:
            username = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
            in_group = username in grp.getgrnam("input").gr_mem
        except Exception:
            in_group = False

        if in_group:
            self.lbl_diag_input.setText("✓ User is in kernel 'input' group (Hotkey capture ready)")
            self.lbl_diag_input.setStyleSheet("color: #10B981;")
            self.btn_polkit_fix.setEnabled(False)
            self.btn_polkit_fix.setText("✓ Permissions already configured")
        else:
            self.lbl_diag_input.setText("✗ User not in 'input' group (Requires logout/login or Polkit authorization)")
            self.lbl_diag_input.setStyleSheet("color: #EF4444;")
            self.btn_polkit_fix.setEnabled(True)

        # ydotoold
        res = subprocess.run(["systemctl", "--user", "is-active", "ydotoold"], capture_output=True, text=True)
        if res.stdout.strip() == "active":
            self.lbl_diag_ydotool.setText("✓ ydotoold daemon is active (Wayland keystroke paste ready)")
            self.lbl_diag_ydotool.setStyleSheet("color: #10B981;")
        else:
            self.lbl_diag_ydotool.setText("⚠ ydotoold daemon is not running (Run: systemctl --user start ydotoold)")
            self.lbl_diag_ydotool.setStyleSheet("color: #F59E0B;")

        # wl-copy
        if shutil.which("wl-copy"):
            self.lbl_diag_wlcopy.setText("✓ wl-clipboard tools installed")
            self.lbl_diag_wlcopy.setStyleSheet("color: #10B981;")
        else:
            self.lbl_diag_wlcopy.setText("✗ wl-clipboard not found (Install wl-clipboard)")
            self.lbl_diag_wlcopy.setStyleSheet("color: #EF4444;")

    def _run_polkit_fix(self) -> None:
        username = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
        rule_content = 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"'
        cmd = f"usermod -aG input {username} && echo '{rule_content}' > /etc/udev/rules.d/80-uinput.rules && udevadm control --reload-rules && udevadm trigger"

        try:
            subprocess.run(["pkexec", "bash", "-c", cmd], check=True)
            QMessageBox.information(
                self,
                "Permissions Granted",
                "Permissions have been granted successfully!\n\n"
                "Please log out of your desktop session and log back in once for the input group changes to take full effect.",
            )
            self._check_diagnostics()
        except Exception as e:
            QMessageBox.warning(self, "Authorization Cancelled", f"Could not update permissions: {e}")

    def _save_all_settings(self) -> None:
        updates = {
            "GROQ_API_KEY": self.api_key_input.text().strip(),
            "SHOW_PILL": self.chk_show_pill.isChecked(),
            "SOUND_FEEDBACK": self.chk_sound.isChecked(),
            "HOTKEY": self.hotkey_combo.currentData() or "KEY_LEFTSHIFT+KEY_RIGHTSHIFT",
            "LANGUAGE": self.lang_combo.currentData() or "",
            "LLM_CLEAN": self.chk_llm_clean.isChecked(),
            "TRANSCRIPTION_PROMPT": self.prompt_text.text().strip() or "Flinx, dictation, voice-to-text, Wayland, Linux.",
            "MIN_RECORDING_DURATION": self.slider_duration.value() / 10.0,
            "MIC_DEVICE": self.mic_combo.currentData() if self.mic_combo.currentData() is not None else "default",
        }

        # Handle systemd autostart toggle
        if self.chk_autostart.isChecked():
            subprocess.run(["systemctl", "--user", "enable", "flinx"], capture_output=True)
        else:
            subprocess.run(["systemctl", "--user", "disable", "flinx"], capture_output=True)

        config.save_config(updates)
        self.settings_applied.emit()

        self.lbl_save_status.setText("✓ Settings saved & activated in real-time!")
        QTimer.singleShot(3000, lambda: self.lbl_save_status.setText(""))

    def closeEvent(self, event: Any) -> None:
        # Stop VU meter listening on close
        self.vu_meter.stop_listening()
        event.accept()


# Standalone runner for testing
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FlinxControlCenter()
    window.show()
    sys.exit(app.exec())

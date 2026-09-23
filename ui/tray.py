"""
ui/tray.py — KDE System Tray icon for Flinx

Provides status monitoring, configuration editing, reload controls,
and quit actions directly from the system tray.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QMessageBox

from flinx import config


class FlinxTray(QObject):
    """System tray component for Flinx."""
    
    reload_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        
        # Load icon from standard KDE/Freedesktop theme fallback to generic audio-input-microphone
        self.icon = QIcon.fromTheme("audio-input-microphone")
        if self.icon.isNull():
            # Create a simple red dot fallback icon if theme icon not found
            from PyQt6.QtGui import QPixmap, QColor, QPainter
            pixmap = QPixmap(24, 24)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(255, 60, 60))
            painter.setPen(QColor(255, 255, 255, 80))
            painter.drawEllipse(4, 4, 16, 16)
            painter.end()
            self.icon = QIcon(pixmap)

        self.tray_icon = QSystemTrayIcon(self.icon, parent)
        self.tray_icon.setToolTip("Flinx Voice-to-Text")

        # Setup menu
        self.menu = QMenu()
        
        # Status item
        self.status_action = QAction("🟢 Flinx — Running", self)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        
        # Last transcription preview
        self.last_trans_action = QAction("📋 No transcription yet", self)
        self.last_trans_action.setEnabled(False)
        self.menu.addAction(self.last_trans_action)
        
        self.menu.addSeparator()
        
        # Configuration actions
        open_config_action = QAction("⚙️ Edit Configuration", self)
        open_config_action.triggered.connect(self._open_config)
        self.menu.addAction(open_config_action)
        
        reload_config_action = QAction("🔄 Reload Configuration", self)
        reload_config_action.triggered.connect(self._reload_config)
        self.menu.addAction(reload_config_action)
        
        self.menu.addSeparator()
        
        # Quit
        quit_action = QAction("❌ Quit", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()

    def set_last_transcription(self, text: str) -> None:
        """Updates the menu with a preview of the last transcription."""
        if not text:
            self.last_trans_action.setText("📋 No transcription yet")
            return
        
        preview = text[:35] + "..." if len(text) > 35 else text
        self.last_trans_action.setText(f"📋 Last: {preview}")

    def _open_config(self) -> None:
        """Opens the configuration file in the default text editor."""
        config_path = os.path.expanduser("~/.config/flinx/.env")
        if not os.path.exists(config_path):
            # Check legacy config first
            legacy_path = os.path.expanduser("~/.config/lowen/.env")
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            import shutil
            example_path = Path(__file__).resolve().parent.parent / ".env.example"
            try:
                if os.path.exists(legacy_path):
                    shutil.copy(legacy_path, config_path)
                elif example_path.exists():
                    shutil.copy(example_path, config_path)
            except Exception as e:
                QMessageBox.critical(None, "Error", f"Failed to create config file: {e}")
                return

        # Open file with default desktop handler (xdg-open)
        try:
            subprocess.Popen(["xdg-open", config_path])
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to open config file: {e}")

    def _reload_config(self) -> None:
        """Triggers a configuration reload."""
        try:
            config.reload()
            self.reload_requested.emit()
            self.tray_icon.showMessage(
                "Flinx",
                "Configuration reloaded successfully.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to reload config: {e}")


# Alias for backward compatibility
LowenTray = FlinxTray

"""
flinx/hotkey.py — Global Wayland-safe hotkey listener using evdev.

Supports single keys (KEY_RIGHTALT) and combos (KEY_LEFTSHIFT+KEY_RIGHTSHIFT).
Combos fire when ALL specified keys are held simultaneously.
Runs in a background thread; never grabs the device so typing is unaffected.
"""

from __future__ import annotations

import selectors
import sys
import threading
import time
from PyQt6.QtCore import QThread, pyqtSignal
import evdev
from evdev import ecodes

from flinx import config


class HotkeyListener(QThread):
    """
    Background thread that listens to global keyboard events via evdev.
    Emits signals on hotkey press and release.
    """
    # Signals to communicate with UI / Core
    hotkey_pressed = pyqtSignal()
    hotkey_released = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._running = False
        self._selector = selectors.DefaultSelector()
        self._devices: list[evdev.InputDevice] = []

        self._hotkey_codes: set[int] = set()
        self._pressed: set[int] = set()   # Which hotkey codes are currently held
        self._hotkey_active = False        # Whether we've fired hotkey_pressed
        self._last_trigger_time = 0.0
        self.update_hotkey(config.HOTKEY)

    def update_hotkey(self, hotkey_str: str | None = None) -> None:
        """Dynamically update listening key codes without restarting thread."""
        raw_key = hotkey_str or config.HOTKEY
        new_codes: set[int] = set()
        for part in raw_key.split("+"):
            part = part.strip()
            code = getattr(ecodes, part, None) or ecodes.ecodes.get(part)
            if code is not None:
                new_codes.add(code)
        if new_codes:
            self._hotkey_codes = new_codes
            self._pressed.clear()
            self._hotkey_active = False

    def _find_keyboards(self) -> list[evdev.InputDevice]:
        """Auto-detect keyboard devices that support at least one hotkey code."""
        keyboards = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if ecodes.EV_KEY in caps:
                    supported = caps[ecodes.EV_KEY]
                    if any(code in supported for code in self._hotkey_codes):
                        keyboards.append(dev)
            except Exception:
                pass
        return keyboards

    def run(self) -> None:
        self._running = True
        
        try:
            self._devices = self._find_keyboards()
        except Exception as e:
            self.error_occurred.emit(f"Failed to scan input devices: {e}")
            return

        if not self._devices:
            self.error_occurred.emit(
                f"No keyboard device found supporting hotkey {config.HOTKEY}. "
                "Ensure your user is in the 'input' group and has re-logged in."
            )
            return

        # Register all keyboard devices with the selector (passive read — no grab)
        for dev in self._devices:
            try:
                self._selector.register(dev, selectors.EVENT_READ)
            except Exception as e:
                self.error_occurred.emit(f"Failed to register input device {dev.name}: {e}")
                self.stop()
                return

        # Event loop
        while self._running:
            events = self._selector.select(timeout=0.1)
            for key, mask in events:
                device = key.fileobj
                try:
                    for event in device.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        if event.code not in self._hotkey_codes:
                            continue

                        if event.value == 1:   # key down
                            self._pressed.add(event.code)
                            # Fire when ALL combo keys are held for the first time
                            if self._pressed >= self._hotkey_codes and not self._hotkey_active:
                                now = time.monotonic()
                                if now - self._last_trigger_time >= 0.08:
                                    self._last_trigger_time = now
                                    self._hotkey_active = True
                                    self.hotkey_pressed.emit()

                        elif event.value == 0:  # key up
                            self._pressed.discard(event.code)
                            if self._hotkey_active:
                                self._hotkey_active = False
                                self._last_trigger_time = time.monotonic()
                                self.hotkey_released.emit()
                except Exception as e:
                    # Handle device disconnected
                    self._selector.unregister(device)
                    if device in self._devices:
                        self._devices.remove(device)
                    
                    if not self._devices:
                        self.error_occurred.emit("All keyboard devices disconnected.")
                        self._running = False
                        break

    def stop(self) -> None:
        """Stop the listener thread and clean up."""
        self._running = False
        self._pressed.clear()
        self._hotkey_active = False
        self.wait() # Wait for thread to exit
        
        # Unregister devices
        for dev in self._devices:
            try:
                self._selector.unregister(dev)
            except Exception:
                pass
        self._devices.clear()
        self._selector.close()

#!/usr/bin/env python3
"""
main.py — Lowen entry point

Usage:
    python main.py              # Launch full daemon (UI, tray, hotkeys)
    python main.py --test       # Record 5s, transcribe, print (no paste)
    python main.py --test-paste # Paste "hello from lowen" into focused window
    python main.py --check      # Check config + system deps, then exit
"""

from __future__ import annotations

import argparse
import sys
import signal


def cmd_check() -> None:
    """Validate config, system dependencies, daemon status, and mic permissions."""
    import shutil
    import subprocess
    import grp
    import os
    import pwd
    from lowen import config

    print("=" * 55)
    print("  Lowen — Comprehensive System Check")
    print("=" * 55)

    errors = config.validate()
    if errors:
        for err in errors:
            print(f"  ✗ {err}")
    else:
        print("  ✓ GROQ_API_KEY is configured")

    # Command-line tools
    for dep, package in [
        ("wl-copy", "wl-clipboard"),
        ("ydotool", "ydotool"),
    ]:
        found = shutil.which(dep) is not None
        mark = "✓" if found else "✗"
        hint = "" if found else f"  → install '{package}'"
        print(f"  {mark} {dep}{hint}")

    # Check ydotoold user daemon status
    daemon_running = False
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", "ydotoold"],
            capture_output=True,
            text=True,
        )
        daemon_running = (res.stdout.strip() == "active")
    except Exception:
        pass

    mark = "✓" if daemon_running else "⚠"
    hint = "" if daemon_running else "  → run: systemctl --user enable --now ydotoold"
    print(f"  {mark} ydotoold daemon running{hint}")

    # Check input group membership
    try:
        username = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
        input_group = grp.getgrnam("input")
        in_group = username in input_group.gr_mem
    except Exception:
        in_group = False
    mark = "✓" if in_group else "✗"
    hint = "" if in_group else "  → sudo usermod -aG input $USER (then re-login)"
    print(f"  {mark} user in 'input' group{hint}")

    # Check sound playback tools
    sound_tool = any(shutil.which(p) for p in ["pw-play", "paplay", "aplay"])
    mark = "✓" if sound_tool else "⚠"
    hint = "" if sound_tool else "  (install pipewire-utils or alsa-utils for audio clicks)"
    print(f"  {mark} audio feedback player available{hint}")

    print("=" * 55)
    if errors or not in_group:
        print("Issues found. Please resolve the items marked with ✗ above.")
        sys.exit(1)
    else:
        print("All required dependencies and permissions look ready!")
    print()


def cmd_test() -> None:
    """Record 5 seconds, transcribe, print result — no paste."""
    from lowen import config
    errors = config.validate()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    from lowen.core import LowenCore
    core = LowenCore()
    text = core.test_pipeline(duration=5.0)
    if text:
        print(f"\nTranscription:\n  {text}")
    else:
        print("\nNo speech detected.")


def cmd_test_paste() -> None:
    """Paste a test string into the currently focused window."""
    from lowen.core import LowenCore
    core = LowenCore()
    print("Switch to a text field in the next 3 seconds…")
    import time; time.sleep(3.0)
    core.test_paste("Hello from Lowen! Voice-to-text is working correctly.")


def cmd_run() -> None:
    """Launch the full Lowen daemon with UI, system tray, and global hotkeys."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from lowen import config
    from lowen.core import LowenCore, State
    from lowen.hotkey import HotkeyListener
    from ui.pill import LowenPill
    from ui.tray import LowenTray

    # Initialize PyQt application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Initialize components
    core = LowenCore()
    pill = LowenPill() if config.SHOW_PILL else None
    hotkey = HotkeyListener()
    tray = LowenTray()

    # Connect hotkey signals to state machine
    hotkey.hotkey_pressed.connect(core.start_recording)
    hotkey.hotkey_released.connect(core.stop_recording)
    
    def handle_hotkey_error(err_msg: str) -> None:
        print(f"[lowen] Hotkey Error: {err_msg}", file=sys.stderr)
        if pill:
            pill.transition_to(State.ERROR, err_msg)

    hotkey.error_occurred.connect(handle_hotkey_error)

    # Connect core signals to pill UI and System Tray
    if pill:
        core.state_changed.connect(pill.transition_to)
        core.rms_level_updated.connect(pill.waveform.update_level)
    
    # Update tray menu with last transcription when copy succeeds
    def handle_state_change(state: State, message: str) -> None:
        if state == State.PASTING:
            # message contains the text preview
            tray.set_last_transcription(message)
        elif state == State.RECORDING:
            tray.status_action.setText("🔴 Recording...")
        elif state == State.PROCESSING:
            tray.status_action.setText("🟡 Processing...")
        elif state == State.ERROR:
            tray.status_action.setText(f"⚠️ Error: {message[:25]}..." if len(message) > 25 else f"⚠️ {message}")
            from PyQt6.QtWidgets import QSystemTrayIcon
            tray.tray_icon.showMessage("Lowen", message, QSystemTrayIcon.MessageIcon.Warning, 3000)
        elif state == State.IDLE:
            tray.status_action.setText("🟢 Lowen — Running")

    core.state_changed.connect(handle_state_change)

    # Connect tray signals
    def on_reload() -> None:
        config.reload()
        hotkey.update_hotkey(config.HOTKEY)
        print(f"[lowen] Config reloaded: Hotkey={config.HOTKEY}, Sound={config.SOUND_FEEDBACK}, LLM={config.LLM_CLEAN}")

    tray.reload_requested.connect(on_reload)
    tray.quit_requested.connect(app.quit)

    # Allow clean exit with Ctrl+C from terminal
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)  # Let python interpreter run to catch signals

    # Start hotkey thread
    hotkey.start()
    
    print(f"[lowen] Daemon active in system tray. Hold '{config.HOTKEY}' to record.")
    
    try:
        sys.exit(app.exec())
    finally:
        # Clean up hotkeys on exit
        hotkey.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lowen",
        description="Lowen — voice-to-text pill for KDE Plasma 6 / Wayland",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Record 5s, transcribe, print — no paste",
    )
    parser.add_argument(
        "--test-paste",
        action="store_true",
        help="Paste a test string into the focused window",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check config and system dependencies",
    )

    args = parser.parse_args()

    if args.check:
        cmd_check()
    elif args.test:
        cmd_test()
    elif args.test_paste:
        cmd_test_paste()
    else:
        cmd_run()


if __name__ == "__main__":
    main()

"""
lowen/clipboard.py — Wayland text injection

Injection strategy (tried in order):
  1. wtype  — Wayland-native text injection via zwp_text_input_v3 protocol.
              Focus-independent: works even if AltGr disrupted the cursor.
              Install: sudo dnf install wtype

  2. wl-copy + ydotool  — Clipboard fallback. Copies text then simulates
              Ctrl+V. Requires ydotoold daemon running. More sensitive
              to focus issues than wtype.

Requirements:
  Primary:  wtype  (sudo dnf install wtype)
  Fallback: wl-clipboard + ydotool  (sudo dnf install wl-clipboard ydotool)
            + ydotoold daemon:  systemctl --user start ydotoold
"""

from __future__ import annotations

import subprocess
import time
import shutil


_wtype_supported: bool | None = None


def _check_wtype() -> bool:
    """Test once if the current Wayland compositor supports wtype's virtual keyboard."""
    global _wtype_supported
    if _wtype_supported is not None:
        return _wtype_supported
    if not shutil.which("wtype"):
        _wtype_supported = False
        return False
    try:
        proc = subprocess.run(
            ["wtype", ""],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=0.5,
        )
        if proc.returncode == 0:
            _wtype_supported = True
        elif "does not support" in proc.stderr.lower():
            _wtype_supported = False
        else:
            _wtype_supported = (proc.returncode == 0)
    except Exception:
        _wtype_supported = False
    return _wtype_supported


def paste_text(text: str) -> None:
    """
    Inject text into the active Wayland application.

    Tries wtype first if supported by the compositor (wlroots/Sway/Hyprland),
    falls back to wl-copy + ydotool (KDE Plasma 6 / GNOME / Universal).

    Raises:
        RuntimeError: If neither injection method is available.
    """
    # ── Method 1: wtype (Wayland-native for wlroots) ───────────────────────
    if _check_wtype():
        try:
            subprocess.run(
                ["wtype", "--", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return
        except subprocess.CalledProcessError:
            pass

    # ── Method 2: wl-copy + ydotool Ctrl+V (fallback) ─────────────────────
    if not shutil.which("wl-copy"):
        raise RuntimeError(
            "No text injection method available. "
            "Install wtype:  sudo dnf install wtype"
        )
    if not shutil.which("ydotool"):
        raise RuntimeError(
            "'ydotool' not found. Run: sudo dnf install ydotool"
        )

    # Write text to Wayland clipboard
    subprocess.run(
        ["wl-copy"],
        input=text.encode("utf-8"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    # 400ms — gives the OS time to settle after Right Alt key release and
    # re-establish focus on the target window before we fire Ctrl+V.
    time.sleep(0.4)

    # Simulate Ctrl+V via raw keycodes:
    # 29 = KEY_LEFTCTRL, 47 = KEY_V.  1 = key down, 0 = key up.
    try:
        subprocess.run(
            ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace").strip()
        if "ydotoold" in stderr.lower() or "socket" in stderr.lower():
            raise RuntimeError(
                "ydotoold daemon is not running. "
                "Start it with: systemctl --user start ydotoold\n"
                f"(raw error: {stderr})"
            ) from exc
        raise


def copy_to_clipboard(text: str) -> None:
    """
    Copy text to Wayland clipboard WITHOUT injecting/pasting.
    Used by --test mode to verify the clipboard step in isolation.
    """
    if not shutil.which("wl-copy"):
        raise RuntimeError("'wl-copy' not found. Run: sudo dnf install wl-clipboard")
    subprocess.run(
        ["wl-copy"],
        input=text.encode("utf-8"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

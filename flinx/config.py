"""
flinx/config.py — Configuration loader

Reads from (in priority order):
  1. ~/.config/flinx/.env
  2. ~/.config/lowen/.env (backward compatibility)
  3. ~/flinx/.env or repo-root .env (dev convenience)
  4. Built-in defaults
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Locate and load .env file (with auto-migration from lowen)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_FLINX_CONFIG = Path.home() / ".config" / "flinx" / ".env"
_LOWEN_CONFIG = Path.home() / ".config" / "lowen" / ".env"

# Auto-migrate config if lowen config exists and flinx does not
if not _FLINX_CONFIG.exists() and _LOWEN_CONFIG.exists():
    try:
        _FLINX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_LOWEN_CONFIG, _FLINX_CONFIG)
    except Exception:
        pass

_CONFIG_PATHS = [
    _FLINX_CONFIG,
    _LOWEN_CONFIG,
    _REPO_ROOT / ".env",
    Path.home() / "flinx" / ".env",
    Path.home() / "lowen" / ".env",
]

for _path in _CONFIG_PATHS:
    if _path.exists():
        load_dotenv(_path)
        break


# ---------------------------------------------------------------------------
# Public config values
# ---------------------------------------------------------------------------

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

HOTKEY: str = os.getenv("HOTKEY", "KEY_LEFTSHIFT+KEY_RIGHTSHIFT")

PILL_POSITION: str = os.getenv("PILL_POSITION", "top-center")

MIC_DEVICE: str | int = os.getenv("MIC_DEVICE", "default")
if str(MIC_DEVICE).isdigit():
    MIC_DEVICE = int(MIC_DEVICE)

LANGUAGE: str = os.getenv("LANGUAGE", "en")

TRANSCRIPTION_PROMPT: str = os.getenv(
    "TRANSCRIPTION_PROMPT",
    "Flinx, dictation, voice-to-text, Wayland, Linux."
)

LLM_CLEAN: bool = os.getenv("LLM_CLEAN", "false").lower() in ("true", "1", "yes")
LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")

SOUND_FEEDBACK: bool = os.getenv("SOUND_FEEDBACK", "true").lower() in ("true", "1", "yes")

SHOW_PILL: bool = os.getenv("SHOW_PILL", "true").lower() in ("true", "1", "yes")

MIN_RECORDING_DURATION: float = float(os.getenv("MIN_RECORDING_DURATION", "0.3"))

# Audio settings (not user-configurable; Whisper prefers 16kHz mono)
SAMPLE_RATE: int = 16_000
CHANNELS: int = 1

# Unique temp file for recorded audio avoiding collisions
_UID = os.getuid() if hasattr(os, "getuid") else 1000
TEMP_AUDIO_PATH: str = str(Path(tempfile.gettempdir()) / f"flinx_recording_{_UID}.wav")


# ---------------------------------------------------------------------------
# Reloading & Validation
# ---------------------------------------------------------------------------

def reload() -> None:
    """Reload settings from disk into global variables."""
    global GROQ_API_KEY, HOTKEY, PILL_POSITION, MIC_DEVICE, LANGUAGE
    global TRANSCRIPTION_PROMPT, LLM_CLEAN, LLM_MODEL, SOUND_FEEDBACK
    global SHOW_PILL, MIN_RECORDING_DURATION

    for p in _CONFIG_PATHS:
        if p.exists():
            load_dotenv(p, override=True)
            break

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    HOTKEY = os.getenv("HOTKEY", "KEY_LEFTSHIFT+KEY_RIGHTSHIFT")
    PILL_POSITION = os.getenv("PILL_POSITION", "top-center")
    mic = os.getenv("MIC_DEVICE", "default")
    MIC_DEVICE = int(mic) if mic.isdigit() else mic
    LANGUAGE = os.getenv("LANGUAGE", "en")
    TRANSCRIPTION_PROMPT = os.getenv("TRANSCRIPTION_PROMPT", "Flinx, dictation, voice-to-text, Wayland, Linux.")
    LLM_CLEAN = os.getenv("LLM_CLEAN", "false").lower() in ("true", "1", "yes")
    LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    SOUND_FEEDBACK = os.getenv("SOUND_FEEDBACK", "true").lower() in ("true", "1", "yes")
    SHOW_PILL = os.getenv("SHOW_PILL", "true").lower() in ("true", "1", "yes")
    MIN_RECORDING_DURATION = float(os.getenv("MIN_RECORDING_DURATION", "0.3"))

    try:
        from flinx import transcriber
        transcriber.reset_client()
    except Exception:
        pass


def save_config(updates: dict[str, str | bool | float | int]) -> Path:
    """
    Save dictionary of settings to ~/.config/flinx/.env and reload in-memory globals.
    """
    _FLINX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing content if file exists
    lines = []
    if _FLINX_CONFIG.exists():
        with open(_FLINX_CONFIG, "r", encoding="utf-8") as f:
            lines = f.readlines()
    elif (_REPO_ROOT / ".env.example").exists():
        with open(_REPO_ROOT / ".env.example", "r", encoding="utf-8") as f:
            lines = f.readlines()

    # Process updates
    keys_written = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                val = updates[k]
                if isinstance(val, bool):
                    val = "true" if val else "false"
                new_lines.append(f"{k}={val}\n")
                keys_written.add(k)
                continue
        new_lines.append(line)

    # Append any keys that weren't already in file
    for k, val in updates.items():
        if k not in keys_written:
            if isinstance(val, bool):
                val = "true" if val else "false"
            new_lines.append(f"{k}={val}\n")

    with open(_FLINX_CONFIG, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    reload()
    return _FLINX_CONFIG


def validate() -> list[str]:
    """Return a list of validation error strings (empty = all good)."""
    errors = []
    if not GROQ_API_KEY:
        errors.append(
            "GROQ_API_KEY is not set. "
            "Add it to ~/.config/flinx/.env (see .env.example)."
        )
    return errors

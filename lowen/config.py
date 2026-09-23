"""
lowen/config.py — Configuration loader

Reads from (in priority order):
  1. ~/.config/lowen/.env
  2. ~/lowen/.env  (dev convenience)
  3. Built-in defaults
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Locate and load .env file
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATHS = [
    Path.home() / ".config" / "lowen" / ".env",
    _REPO_ROOT / ".env",
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

HOTKEY: str = os.getenv("HOTKEY", "KEY_RIGHTALT")

PILL_POSITION: str = os.getenv("PILL_POSITION", "top-center")

MIC_DEVICE: str | int = os.getenv("MIC_DEVICE", "default")
if str(MIC_DEVICE).isdigit():
    MIC_DEVICE = int(MIC_DEVICE)

LANGUAGE: str = os.getenv("LANGUAGE", "en")

TRANSCRIPTION_PROMPT: str = os.getenv(
    "TRANSCRIPTION_PROMPT",
    "Lowen, dictation, voice-to-text, Wayland, KDE."
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
TEMP_AUDIO_PATH: str = str(Path(tempfile.gettempdir()) / f"lowen_recording_{_UID}.wav")


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
    HOTKEY = os.getenv("HOTKEY", "KEY_RIGHTALT")
    PILL_POSITION = os.getenv("PILL_POSITION", "top-center")
    mic = os.getenv("MIC_DEVICE", "default")
    MIC_DEVICE = int(mic) if mic.isdigit() else mic
    LANGUAGE = os.getenv("LANGUAGE", "en")
    TRANSCRIPTION_PROMPT = os.getenv("TRANSCRIPTION_PROMPT", "Lowen, dictation, voice-to-text, Wayland, KDE.")
    LLM_CLEAN = os.getenv("LLM_CLEAN", "false").lower() in ("true", "1", "yes")
    LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    SOUND_FEEDBACK = os.getenv("SOUND_FEEDBACK", "true").lower() in ("true", "1", "yes")
    SHOW_PILL = os.getenv("SHOW_PILL", "true").lower() in ("true", "1", "yes")
    MIN_RECORDING_DURATION = float(os.getenv("MIN_RECORDING_DURATION", "0.3"))


def validate() -> list[str]:
    """Return a list of validation error strings (empty = all good)."""
    errors = []
    if not GROQ_API_KEY:
        errors.append(
            "GROQ_API_KEY is not set. "
            "Add it to ~/.config/lowen/.env (see .env.example)."
        )
    return errors

"""
flinx/core.py — App state machine and orchestrator

States:
    IDLE        → waiting for hotkey
    RECORDING   → mic is live
    PROCESSING  → audio sent to Groq, waiting for response
    PASTING     → text received, pasting into focused window
    ERROR       → something went wrong (auto-recovers to IDLE after 2.5s)

Communicates with UI components using PyQt6 signals.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from enum import Enum, auto
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from flinx import config, transcriber, clipboard
from flinx.recorder import Recorder

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"


class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    PASTING = auto()
    ERROR = auto()


class FlinxCore(QObject):
    """
    State machine orchestrator for Flinx.
    Runs sound recording and Groq Whisper transcription asynchronously.
    """
    state_changed = pyqtSignal(State, str)  # (State, status_message)
    rms_level_updated = pyqtSignal(float)   # RMS level [0.0, 1.0]
    transcription_completed = pyqtSignal(str)  # Full transcribed text for tray/history

    def __init__(self) -> None:
        super().__init__()
        self._state = State.IDLE
        self._lock = threading.Lock()
        
        # Instantiate recorder with a callback that forwards the RMS level to our signal
        self.recorder = Recorder(level_callback=self._handle_rms_level)
        
        # Auto-ensure custom sounds are generated
        self._ensure_custom_sounds()

    def _ensure_custom_sounds(self) -> None:
        sounds_dir = RESOURCES_DIR / "sounds"
        start_wav = sounds_dir / "start.wav"
        stop_wav = sounds_dir / "stop.wav"
        if not (start_wav.exists() and stop_wav.exists()):
            try:
                from flinx.generate_sounds import main as gen_main
                gen_main()
            except Exception as e:
                print(f"[flinx] Warning: Failed to auto-generate sounds: {e}")

    @property
    def state(self) -> State:
        return self._state

    def _set_state(self, new_state: State, message: str = "") -> None:
        with self._lock:
            self._state = new_state
        self.state_changed.emit(new_state, message)

    def _handle_rms_level(self, level: float) -> None:
        if self._state == State.RECORDING:
            self.rms_level_updated.emit(level)

    def _auto_recover_idle(self, delay: float = 2.0) -> None:
        """Helper to ensure state machine returns to IDLE after delay."""
        time.sleep(delay)
        with self._lock:
            if self._state != State.RECORDING:
                self._state = State.IDLE
                self.state_changed.emit(State.IDLE, "")

    @pyqtSlot()
    def start_recording(self) -> None:
        """Called when hotkey is pressed down."""
        with self._lock:
            # If already actively recording, ignore duplicate triggers
            if self._state == State.RECORDING:
                return

            # If previous recording is still transcribing, avoid overlapping capture
            if self._state == State.PROCESSING:
                print("[flinx] Hotkey pressed while previous recording is processing — ignoring", flush=True)
                return

            # Self-healing: if state was ERROR or PASTING or IDLE, transition directly to RECORDING!
            self._state = State.RECORDING

        print("[flinx] Hotkey pressed — starting recording", flush=True)
        self._play_sound("start")
        self.state_changed.emit(State.RECORDING, "Listening...")

        try:
            self.recorder.start()
        except Exception as e:
            print(f"[flinx] Error starting audio recorder: {e}", flush=True)
            self._set_state(State.ERROR, f"Mic error: {e}")
            threading.Thread(target=self._auto_recover_idle, args=(2.0,), daemon=True).start()

    @pyqtSlot()
    def stop_recording(self) -> None:
        """Called when hotkey is released."""
        with self._lock:
            if self._state != State.RECORDING:
                return

        print("[flinx] Hotkey released — stopping recording", flush=True)
        self._play_sound("stop")

        try:
            wav_path = self.recorder.stop()
        except Exception as e:
            print(f"[flinx] Error stopping audio recorder: {e}", flush=True)
            wav_path = None

        if wav_path is None:
            print("[flinx] Recording too short or empty — discarded", flush=True)
            self._set_state(State.IDLE, "")
            return

        # Start background processing thread so we don't block the UI thread
        self._set_state(State.PROCESSING, "Processing audio...")
        threading.Thread(target=self._process, args=(wav_path,), daemon=True).start()

    def cancel_recording(self) -> None:
        """Abort recording without saving or transcribing."""
        with self._lock:
            was_recording = (self._state == State.RECORDING)
            self._state = State.IDLE

        if was_recording:
            try:
                self.recorder.cancel()
            except Exception:
                pass
            self.state_changed.emit(State.IDLE, "")

    def _process(self, wav_path: str) -> None:
        """Background thread worker for transcription and clipboard paste with guaranteed recovery."""
        print("[flinx] Transcribing...", flush=True)
        try:
            try:
                text = transcriber.transcribe(wav_path)
            except Exception as exc:  # noqa: BLE001
                print(f"[flinx] Transcription error: {exc}", flush=True)
                self._set_state(State.ERROR, f"Transcription failed: {exc}")
                time.sleep(2.0)
                return

            print(f"[flinx] Transcribed: {text!r}", flush=True)
            if not text or not text.strip():
                self._set_state(State.ERROR, "No speech detected")
                time.sleep(1.4)
                return

            self.transcription_completed.emit(text)

            # Show pasting status in pill HUD
            self._set_state(State.PASTING, "Pasting...")
            print("[flinx] Injecting via clipboard...", flush=True)

            try:
                clipboard.paste_text(text)
            except Exception as exc:  # noqa: BLE001
                print(f"[flinx] Paste error: {exc}", flush=True)
                self._set_state(State.ERROR, f"Failed to paste: {exc}")
                time.sleep(2.0)
                return

            self._set_state(State.PASTING, "Pasted!")
            time.sleep(0.9)

        finally:
            # Clean up temporary audio file
            try:
                if wav_path and os.path.exists(wav_path):
                    os.remove(wav_path)
            except Exception:
                pass

            # Guaranteed self-healing reset: always return to IDLE if not actively recording
            with self._lock:
                if self._state != State.RECORDING:
                    self._state = State.IDLE
                    self.state_changed.emit(State.IDLE, "")

    def _play_sound(self, action: str) -> None:
        """Plays start/stop feedback click sound."""
        if not config.SOUND_FEEDBACK:
            return
            
        # We'll execute sound play asynchronously in a separate thread so it doesn't block
        threading.Thread(target=self._play_sound_worker, args=(action,), daemon=True).start()

    def _play_sound_worker(self, action: str) -> None:
        # Check local resources directory first
        local_path = RESOURCES_DIR / "sounds" / f"{action}.wav"
        if local_path.exists():
            sound_path = str(local_path)
        else:
            # Fallback to standard system sounds
            sound_paths = {
                "start": "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga",
                "stop": "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga"
            }
            sound_path = sound_paths.get(action)
            
        if not sound_path or not os.path.exists(sound_path):
            return

        # Simple cross-platform terminal audio player
        for player in ["paplay", "aplay", "pw-play"]:
            if shutil.which(player):
                try:
                    subprocess.run([player, sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except Exception:
                    pass

    def test_pipeline(self, duration: float = 5.0) -> str | None:
        """
        Record for `duration` seconds, transcribe, return text (no paste).
        Blocks the calling thread. Used for CLI testing.
        """
        print(f"[flinx] Recording for {duration}s… speak now!")
        self.recorder.start()
        time.sleep(duration)
        wav_path = self.recorder.stop()

        if wav_path is None:
            print("[flinx] Recording too short — discarded")
            return None

        print("[flinx] Transcribing…")
        return transcriber.transcribe(wav_path)

    def test_paste(self, text: str = "hello from flinx") -> None:
        """Paste a hardcoded string. Used for CLI testing."""
        print(f"[flinx] Pasting: {text!r}")
        clipboard.paste_text(text)
        print("[flinx] Done")

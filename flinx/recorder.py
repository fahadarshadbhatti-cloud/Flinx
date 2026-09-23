"""
flinx/recorder.py — Microphone capture using sounddevice

Records audio into a numpy buffer while the hotkey is held,
then writes a WAV file to disk when stopped.

Usage:
    recorder = Recorder()
    recorder.start()
    # ... user speaks ...
    wav_path = recorder.stop()   # None if recording was too short
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wavfile

from flinx import config


class Recorder:
    """Thread-safe, push-to-talk audio recorder."""

    def __init__(
        self,
        level_callback: Callable[[float], None] | None = None,
    ) -> None:
        """
        Args:
            level_callback: Called ~10× per second with an RMS amplitude
                            float in [0.0, 1.0] so the UI can animate
                            waveform bars. Optional.
        """
        self._lock = threading.Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._start_time: float | None = None
        self._recording = False
        self._level_callback = level_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin capturing microphone audio."""
        with self._lock:
            if self._recording:
                return

            self._frames = []
            self._start_time = time.monotonic()
            self._recording = True

            device = None if config.MIC_DEVICE == "default" else config.MIC_DEVICE

            self._stream = sd.InputStream(
                samplerate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
                dtype="int16",
                device=device,
                blocksize=1024,
                callback=self._audio_callback,
            )
            self._stream.start()

    def stop(self) -> str | None:
        """
        Stop recording and write WAV file.

        Returns:
            Path to the WAV file, or None if the recording was too short
            (< MIN_RECORDING_DURATION seconds) and should be discarded.
        """
        with self._lock:
            if not self._recording:
                return None

            self._recording = False
            duration = time.monotonic() - self._start_time  # type: ignore[operator]

            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            if duration < config.MIN_RECORDING_DURATION:
                self._frames = []
                return None

            if not self._frames:
                return None

            audio = np.concatenate(self._frames, axis=0)
            wav_path = config.TEMP_AUDIO_PATH
            wavfile.write(wav_path, config.SAMPLE_RATE, audio)
            return wav_path

    def cancel(self) -> None:
        """Abort recording without saving."""
        with self._lock:
            self._recording = False
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._frames = []

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,  # noqa: ANN001
        status: sd.CallbackFlags,
    ) -> None:
        """Called by sounddevice for each audio block."""
        if not self._recording:
            return

        chunk = indata.copy()
        self._frames.append(chunk)

        # Emit a normalised RMS level for waveform animation
        if self._level_callback is not None:
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            # int16 max is 32768; clamp to [0, 1]
            normalised = min(rms / 32768.0 * 6.0, 1.0)
            self._level_callback(normalised)

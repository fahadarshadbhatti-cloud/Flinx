#!/usr/bin/env python3
"""
flinx/generate_sounds.py — Audio click generator for Flinx

Generates extremely clean, soft, decaying sine-wave clicks for start and stop
events, preventing dependancy on external OS sounds and matching Vowen's premium UX.
"""

from __future__ import annotations

import os
import numpy as np
from scipy.io import wavfile


def make_click(filename: str, freq: float, duration: float = 0.020, sample_rate: int = 44100) -> None:
    """Generate a clean, exponentially-decaying sine-wave click."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Sine wave
    wave = np.sin(2 * np.pi * freq * t)
    
    # Exponential decay envelope to make it smooth and prevent hard popping
    envelope = np.exp(-t * 250)
    
    # Combine and scale volume (subtle, quiet amplitude)
    audio = wave * envelope * 0.12
    
    # Convert to 16-bit integer PCM format
    audio_int16 = (audio * 32767).astype(np.int16)
    
    # Save file
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    wavfile.write(filename, sample_rate, audio_int16)
    print(f"Generated subtle click: {filename} ({freq}Hz, {duration*1000:.0f}ms)")


from pathlib import Path


def main() -> None:
    resources_dir = Path(__file__).resolve().parent.parent / "resources" / "sounds"
    make_click(str(resources_dir / "start.wav"), freq=750.0, duration=0.018)
    make_click(str(resources_dir / "stop.wav"), freq=550.0, duration=0.018)


if __name__ == "__main__":
    main()

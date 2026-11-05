"""Cinematic BGM Music Director: Generates and textures thematic musical beds."""

import logging
import math
from pathlib import Path
import struct
from typing import Optional
import wave

logger = logging.getLogger(__name__)


class MusicDirector:
    """Provides cinematic background music aligned with mood and intensity curves."""

    def __init__(self, music_dir: Optional[Path] = None, sample_rate: int = 44100):
        self.music_dir = music_dir or Path("storage/assets/music")
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.sample_rate = sample_rate

    def get_or_synthesize_bgm(
        self,
        music_mood: str,
        total_duration_sec: float,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Resolve background music bed for the given mood and duration."""
        clean_mood = music_mood.strip().lower().replace(" ", "_")
        if output_path is None:
            output_path = self.music_dir / f"bgm_{clean_mood}_{int(total_duration_sec)}s.wav"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and output_path.stat().st_size > 1000:
            return output_path

        # Procedural cinematic drone/harmony synthesis
        self._synthesize_bgm_track(clean_mood, total_duration_sec, output_path)
        return output_path

    def _synthesize_bgm_track(self, mood: str, duration_sec: float, output_path: Path) -> Path:
        """Generate high-aesthetic cinematic atmospheric soundtrack offline."""
        total_frames = int(duration_sec * self.sample_rate)
        raw_samples = bytearray()

        # Define root chord frequencies based on mood
        if "dark" in mood or "omen" in mood or "shadow" in mood:
            # D Minor triad / cinematic drone (D2=73.4Hz, A2=110Hz, F3=174.6Hz)
            chord = [73.4, 110.0, 174.6, 220.0]
        elif "cosmic" in mood or "space" in mood or "misterio" in mood:
            # Suspended 4th ethereal chord (C#2=69.3Hz, G#2=103.8Hz, F#3=185Hz)
            chord = [69.3, 103.8, 185.0, 277.2]
        elif "triumph" in mood or "epic" in mood or "climax" in mood:
            # Low epic brass drone (E2=82.4Hz, B2=123.5Hz, E3=164.8Hz)
            chord = [82.4, 123.5, 164.8, 329.6]
        else:
            # Neutral cinematic atmospheric bed (A2=110Hz, E3=164.8Hz, B3=246.9Hz)
            chord = [110.0, 164.8, 246.9]

        for i in range(total_frames):
            t = float(i) / self.sample_rate
            # 2.0s fade in and 3.0s fade out
            fade_in = min(t / 2.0, 1.0)
            fade_out = min((duration_sec - t) / 3.0, 1.0)
            envelope = fade_in * fade_out

            # Slow pulsing modulation
            pulse = 0.85 + 0.15 * math.sin(2.0 * math.pi * 0.25 * t)

            sample_sum = 0.0
            for idx, freq in enumerate(chord):
                # Subtle detuning per voice for wide chorused sound
                detune = math.sin(2.0 * math.pi * 0.1 * t * (idx + 1)) * 0.4
                sample_sum += math.sin(2.0 * math.pi * (freq + detune) * t)

            sample_avg = (sample_sum / len(chord)) * envelope * pulse
            val = int(32767 * 0.35 * sample_avg)
            val = max(min(val, 32767), -32768)
            raw_samples.extend(struct.pack("<h", val))

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(raw_samples)

        return output_path

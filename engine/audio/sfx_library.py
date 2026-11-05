"""Procedural & Local SFX Library for cinematic sound effects.

Generates or loads audio assets for tags like:
- sword_unsheathe / sword_blade_ring
- thunder_crack / lightning_strike
- monster_screech / spectral_wail
- cinematic_whoosh / wind_howl
- heartbeat_tension
"""

import logging
import math
from pathlib import Path
import random
import struct
from typing import Optional
import wave

logger = logging.getLogger(__name__)


class SfxLibrary:
    """Provides high-quality sound effects from disk or procedural acoustic synthesis."""

    def __init__(self, sfx_dir: Optional[Path] = None, sample_rate: int = 44100):
        self.sfx_dir = sfx_dir or Path("storage/assets/sfx")
        self.sfx_dir.mkdir(parents=True, exist_ok=True)
        self.sample_rate = sample_rate

    def get_or_synthesize_sfx(self, sound_tag: str, duration_sec: float = 2.0) -> Path:
        """Resolve an SFX file for a sound_tag, synthesizing a procedural cue if needed."""
        clean_tag = sound_tag.strip().lower().replace(" ", "_")
        target_path = self.sfx_dir / f"{clean_tag}.wav"

        if target_path.exists() and target_path.stat().st_size > 44:
            return target_path

        # Procedurally synthesize realistic acoustic cues
        self._synthesize_sfx(clean_tag, duration_sec, target_path)
        return target_path

    def _synthesize_sfx(self, tag: str, duration_sec: float, output_path: Path) -> Path:
        """Synthesize specialized sound waveforms based on audio tag categories."""
        total_frames = int(duration_sec * self.sample_rate)
        raw_samples = bytearray()

        if "sword" in tag or "blade" in tag or "metal" in tag:
            # High resonant metallic ring with FM modulation and gradual decay
            base_freq = 1200.0
            mod_freq = 430.0
            for i in range(total_frames):
                t = float(i) / self.sample_rate
                decay = math.exp(-3.5 * t)
                carrier = math.sin(2.0 * math.pi * base_freq * t + 1.2 * math.sin(2.0 * math.pi * mod_freq * t))
                val = int(32767 * 0.45 * decay * carrier)
                val = max(min(val, 32767), -32768)
                raw_samples.extend(struct.pack("<h", val))

        elif "thunder" in tag or "lightning" in tag or "blast" in tag or "explosion" in tag:
            # Low-frequency rumble with exponential white noise crack and long sub-bass tail
            rng = random.Random(42)
            for i in range(total_frames):
                t = float(i) / self.sample_rate
                impact = math.exp(-7.0 * t) if t < 0.3 else math.exp(-1.5 * t) * 0.4
                noise = rng.uniform(-1.0, 1.0)
                sub_rumble = math.sin(2.0 * math.pi * (55.0 - 15.0 * t) * t)
                sample_float = 0.6 * impact * noise + 0.4 * math.exp(-1.0 * t) * sub_rumble
                val = int(32767 * 0.6 * sample_float)
                val = max(min(val, 32767), -32768)
                raw_samples.extend(struct.pack("<h", val))

        elif "screech" in tag or "ghost" in tag or "wail" in tag or "soul" in tag or "alma" in tag:
            # Eerie dissonance with multi-voice pitch detuning and vibrato
            for i in range(total_frames):
                t = float(i) / self.sample_rate
                vibrato = math.sin(2.0 * math.pi * 6.0 * t) * 25.0
                f1 = 660.0 + vibrato
                f2 = 666.0 + vibrato
                f3 = 880.0
                envelope = math.sin(math.pi * (i / total_frames))
                sample_float = (
                    0.4 * math.sin(2.0 * math.pi * f1 * t)
                    + 0.4 * math.sin(2.0 * math.pi * f2 * t)
                    + 0.2 * math.sin(2.0 * math.pi * f3 * t)
                ) * envelope
                val = int(32767 * 0.4 * sample_float)
                val = max(min(val, 32767), -32768)
                raw_samples.extend(struct.pack("<h", val))

        elif "whoosh" in tag or "wind" in tag or "breath" in tag:
            # Frequency sweeping filtered band noise
            rng = random.Random(101)
            for i in range(total_frames):
                t = float(i) / self.sample_rate
                envelope = math.sin(math.pi * (i / total_frames)) ** 2
                noise = rng.uniform(-1.0, 1.0)
                val = int(32767 * 0.35 * envelope * noise)
                val = max(min(val, 32767), -32768)
                raw_samples.extend(struct.pack("<h", val))

        else:
            # Generic punchy cinematic transient
            for i in range(total_frames):
                t = float(i) / self.sample_rate
                envelope = math.exp(-4.0 * t)
                freq = max(350.0 - (200.0 * t), 50.0)
                wave_val = math.sin(2.0 * math.pi * freq * t)
                val = int(32767 * 0.4 * envelope * wave_val)
                val = max(min(val, 32767), -32768)
                raw_samples.extend(struct.pack("<h", val))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(raw_samples)

        return output_path

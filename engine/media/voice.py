"""Voice synthesis implementations: deterministic dummy and Edge-TTS provider."""

import math
from pathlib import Path
import struct
import wave
from engine.media.base import AudioResult, VoiceProvider


class DummyVoiceProvider(VoiceProvider):
    """Generates deterministic, valid PCM WAV audio offline without any external service."""

    def __init__(self, words_per_minute: int = 140, sample_rate: int = 24000):
        self.words_per_minute = words_per_minute
        self.sample_rate = sample_rate

    def generate_audio(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> AudioResult:
        """Create a clean, modulated acoustic audio track matching text word count."""
        words = text.strip().split()
        word_count = max(len(words), 1)

        # Duration derived from words per minute
        seconds_per_word = 60.0 / self.words_per_minute
        duration = max(word_count * seconds_per_word, 2.0)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        total_frames = int(duration * self.sample_rate)
        # Generate a gentle multi-tone acoustic waveform with micro-pauses
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.sample_rate)

            raw_data = bytearray()
            freq_base = 220.0  # A3 note
            for i in range(total_frames):
                t = float(i) / self.sample_rate
                # Modulate slightly to simulate speech cadence
                cadence = 0.5 * (1.0 + math.sin(2.0 * math.pi * 3.5 * t))
                envelope = 0.5 * (1.0 - math.cos(2.0 * math.pi * (i / total_frames)))
                sample_val = int(
                    32767 * 0.3 * envelope * cadence * math.sin(2.0 * math.pi * freq_base * t)
                )
                sample_val = max(min(sample_val, 32767), -32768)
                raw_data.extend(struct.pack("<h", sample_val))

            wav_file.writeframes(raw_data)

        return AudioResult(
            file_path=output_path,
            duration_seconds=round(duration, 2),
            voice_id=voice_id,
            provider="DummyVoiceProvider",
            sample_rate=self.sample_rate,
        )


class EdgeTTSVoiceProvider(VoiceProvider):
    """Real Text-to-Speech provider using Microsoft Edge neural voices."""

    def __init__(self, default_voice: str = "es-ES-AlvaroNeural"):
        self.default_voice = default_voice

    def generate_audio(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> AudioResult:
        """Synthesize natural voice using edge-tts."""
        try:
            import asyncio
            import edge_tts
        except ImportError:
            raise ImportError(
                "edge-tts is not installed. Run `pip install edge-tts` or use DummyVoiceProvider for offline execution."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        chosen_voice = voice_id or self.default_voice

        async def _synthesize() -> None:
            communicate = edge_tts.Communicate(text, chosen_voice, rate=rate, pitch=pitch)
            await communicate.save(str(output_path))

        asyncio.run(_synthesize())

        # Determine audio duration via wave or mutagen / ffprobe
        # For MP3/WAV, we can inspect with ffprobe or estimate
        import subprocess
        import json

        duration = 5.0
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(output_path),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(res.stdout)
            duration = float(info["format"]["duration"])
        except Exception:
            pass

        return AudioResult(
            file_path=output_path,
            duration_seconds=round(duration, 2),
            voice_id=chosen_voice,
            provider="EdgeTTSVoiceProvider",
            sample_rate=24000,
        )

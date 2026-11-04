"""Voice synthesis implementations: deterministic dummy, Edge-TTS, and OpenAI TTS providers."""

import json
import logging
import math
import os
from pathlib import Path
import struct
import subprocess
from typing import Optional
import urllib.request
import wave

from engine.media.base import AudioResult, VoiceProvider

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        default_voice: str = "es-ES-AlvaroNeural",
        fallback_provider: Optional[VoiceProvider] = None,
    ):
        self.default_voice = default_voice
        self.fallback_provider = fallback_provider or DummyVoiceProvider()

    def generate_audio(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> AudioResult:
        """Synthesize natural voice using edge-tts with automatic fallback."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            import asyncio
            import edge_tts
        except ImportError:
            logger.warning("edge-tts no está instalado. Usando fallback acústico.")
            return self.fallback_provider.generate_audio(text, voice_id, output_path, rate, pitch)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Robust voice selection: if voice_id is generic ('default_offline', etc.), use default_voice
        if not voice_id or voice_id.startswith("default"):
            chosen_voice = self.default_voice
        else:
            chosen_voice = voice_id

        import subprocess
        import json

        # Honest container handling: Edge-TTS outputs an MP3 stream.
        # If the target path is .wav, transcode via ffmpeg to genuine PCM WAV (16-bit, 24kHz mono).
        is_wav_requested = output_path.suffix.lower() == ".wav"
        synth_dest = output_path.with_suffix(".temp.mp3") if is_wav_requested else output_path

        async def _synthesize() -> None:
            communicate = edge_tts.Communicate(text, chosen_voice, rate=rate, pitch=pitch)
            await communicate.save(str(synth_dest))

        try:
            asyncio.run(_synthesize())
        except Exception as e:
            logger.warning(f"Fallo en síntesis Edge-TTS ({e}). Aplicando fallback acústico.")
            if is_wav_requested and synth_dest.exists():
                synth_dest.unlink(missing_ok=True)
            return self.fallback_provider.generate_audio(text, chosen_voice, output_path, rate, pitch)

        if is_wav_requested:
            # Transcode temp MP3 to genuine RIFF PCM WAV
            conv_cmd = [
                "ffmpeg", "-y",
                "-i", str(synth_dest),
                "-c:a", "pcm_s16le",
                "-ar", "24000",
                "-ac", "1",
                str(output_path),
            ]
            conv_res = subprocess.run(conv_cmd, capture_output=True, text=True)
            synth_dest.unlink(missing_ok=True)
            if conv_res.returncode != 0:
                logger.warning(f"Error transcodificando MP3 a WAV: {conv_res.stderr}. Usando fallback acústico.")
                return self.fallback_provider.generate_audio(text, chosen_voice, output_path, rate, pitch)

        # Determine audio duration via ffprobe
        duration = None
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
        except Exception as e:
            logger.error(f"Error obteniendo duración de audio para {output_path}: {e}")

        if duration is None or duration <= 0:
            raise RuntimeError(f"No se pudo determinar la duración real del audio en {output_path}")

        return AudioResult(
            file_path=output_path,
            duration_seconds=round(duration, 2),
            voice_id=chosen_voice,
            provider="EdgeTTSVoiceProvider",
            sample_rate=24000,
        )


class OpenAIVoiceProvider(VoiceProvider):
    """Voice provider utilizing OpenAI's Text-to-Speech API (tts-1 / tts-1-hd) with acoustic fallback."""

    OPENAI_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "tts-1",
        default_voice: str = "alloy",
        fallback_provider: Optional[VoiceProvider] = None,
    ):
        import os
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.default_voice = default_voice
        self.fallback_provider = fallback_provider or DummyVoiceProvider()

    def generate_audio(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> AudioResult:
        """Synthesize natural neural audio using OpenAI TTS API."""
        if not self.api_key:
            logger.info("OPENAI_API_KEY no configurada. Delegando al fallback provider.")
            return self.fallback_provider.generate_audio(
                text=text,
                voice_id=voice_id,
                output_path=output_path,
                rate=rate,
                pitch=pitch,
            )

        chosen_voice = voice_id if voice_id in self.OPENAI_VOICES else self.default_voice
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model": self.model,
            "input": text,
            "voice": chosen_voice,
            "response_format": "mp3",
        }

        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ValiantRamanStudio/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                content = resp.read()
                with open(output_path, "wb") as f:
                    f.write(content)
        except Exception as e:
            logger.warning(f"OpenAI TTS synthesis failed: {e}. Falling back to acoustic provider.")
            return self.fallback_provider.generate_audio(
                text=text,
                voice_id=voice_id,
                output_path=output_path,
                rate=rate,
                pitch=pitch,
            )

        # Probe duration via ffprobe
        duration = None
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
        except Exception as e:
            logger.error(f"Error midiendo duración de audio OpenAI para {output_path}: {e}")

        if duration is None or duration <= 0:
            return self.fallback_provider.generate_audio(
                text=text,
                voice_id=voice_id,
                output_path=output_path,
                rate=rate,
                pitch=pitch,
            )

        return AudioResult(
            file_path=output_path,
            duration_seconds=round(duration, 2),
            voice_id=chosen_voice,
            provider="OpenAIVoiceProvider",
            sample_rate=24000,
        )


def get_default_voice_provider() -> VoiceProvider:
    """Resolve optimal voice provider based on configuration and installed libraries."""
    import os
    provider_type = os.getenv("VOICE_PROVIDER", "edge_tts").lower()
    default_voice = os.getenv("VOICE_NAME", "es-ES-AlvaroNeural")

    if provider_type == "dummy":
        return DummyVoiceProvider()

    if provider_type in ("openai", "openai_tts"):
        return OpenAIVoiceProvider(
            fallback_provider=EdgeTTSVoiceProvider(default_voice=default_voice, fallback_provider=DummyVoiceProvider())
        )

    try:
        import edge_tts
        return EdgeTTSVoiceProvider(default_voice=default_voice, fallback_provider=DummyVoiceProvider())
    except ImportError:
        return DummyVoiceProvider()

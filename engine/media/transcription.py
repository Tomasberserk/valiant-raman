"""Transcription provider module: deterministic offline alignment and Whisper integration."""

from pathlib import Path
from typing import List, Optional
import wave

from engine.media.base import TranscriptionProvider, WordTimestamp


class DummyTranscriptionProvider(TranscriptionProvider):
    """Generates deterministic word-level timestamps without needing speech recognition models."""

    def transcribe(
        self,
        audio_path: Path,
        reference_text: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> List[WordTimestamp]:
        """Compute proportional word timestamps aligned with the actual audio duration."""
        if not reference_text or not reference_text.strip():
            reference_text = "Demostración de contenido audiovisual original y reproducible."

        words = reference_text.strip().split()
        if not words:
            return []

        # Determine real duration: Priority 1: duration_seconds argument
        total_duration = duration_seconds if (duration_seconds and duration_seconds > 0) else None

        # Priority 2: Inspect WAV file via wave module
        if total_duration is None:
            try:
                with wave.open(str(audio_path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        total_duration = float(frames) / rate
            except Exception:
                pass

        # Priority 3: Inspect via ffprobe (supports MP3, AAC, WAV, etc.)
        if total_duration is None:
            import subprocess
            import json
            try:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "json", str(audio_path)
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                info = json.loads(res.stdout)
                total_duration = float(info["format"]["duration"])
            except Exception:
                pass

        # If completely unable to determine duration, fail explicitly
        if total_duration is None or total_duration <= 0:
            raise RuntimeError(f"No se pudo determinar la duración del audio en {audio_path}")

        # Distribute time across words with small natural speech spacing
        active_time = total_duration * 0.90
        pause_budget = total_duration * 0.10
        time_per_word = active_time / len(words)
        pause_per_word = pause_budget / len(words)

        timestamps: List[WordTimestamp] = []
        current_time = 0.05  # small leading silence

        for word in words:
            start = round(current_time, 3)
            end = round(start + time_per_word, 3)
            timestamps.append(WordTimestamp(word=word, start=start, end=end))
            current_time = end + pause_per_word

        return timestamps


class WhisperTranscriptionProvider(TranscriptionProvider):
    """Transcription provider wrapping local Whisper."""

    def __init__(self, model_name: str = "base"):
        self.model_name = model_name

    def transcribe(
        self,
        audio_path: Path,
        reference_text: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> List[WordTimestamp]:
        """Transcribe audio using Whisper model."""
        # Stub for dynamic invocation of whisper library or ffmpeg whisper filter
        try:
            import whisper
            model = whisper.load_model(self.model_name)
            result = model.transcribe(str(audio_path), word_timestamps=True)
            timestamps: List[WordTimestamp] = []
            for segment in result.get("segments", []):
                for w in segment.get("words", []):
                    timestamps.append(
                        WordTimestamp(
                            word=w["word"].strip(),
                            start=round(w["start"], 3),
                            end=round(w["end"], 3),
                        )
                    )
            return timestamps
        except ImportError:
            # Fallback to Dummy alignment if whisper library is not directly imported
            fallback = DummyTranscriptionProvider()
            return fallback.transcribe(audio_path, reference_text, duration_seconds)

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
    ) -> List[WordTimestamp]:
        """Compute proportional word timestamps aligned with the actual audio duration."""
        if not reference_text or not reference_text.strip():
            reference_text = "Demostración de contenido audiovisual original y reproducible."

        words = reference_text.strip().split()
        if not words:
            return []

        # Read actual audio duration from WAV if possible
        total_duration = 5.0
        try:
            with wave.open(str(audio_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    total_duration = float(frames) / rate
        except Exception:
            pass

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
            return fallback.transcribe(audio_path, reference_text)

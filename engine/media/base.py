"""Abstract media interfaces and data models for audio, transcription, and composition."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


class AudioResult(BaseModel):
    """Metadata resulting from voice synthesis."""

    file_path: Path
    duration_seconds: float = Field(gt=0)
    voice_id: str
    provider: str
    sample_rate: int = 44100


class WordTimestamp(BaseModel):
    """Individual word timing within an audio track."""

    word: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class VoiceProvider(ABC):
    """Interface for text-to-speech engines."""

    @abstractmethod
    def generate_audio(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> AudioResult:
        """Synthesize text into an audio file."""
        pass


class TranscriptionProvider(ABC):
    """Interface for transcribing audio and generating word-level timestamps."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        reference_text: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> List[WordTimestamp]:
        """Produce word timestamps for the given audio."""
        pass


class Compositor(ABC):
    """Interface for audiovisual composition and rendering."""

    @abstractmethod
    def compose_video(
        self,
        background_path: Path,
        audio_path: Path,
        subtitles_path: Optional[Path],
        output_path: Path,
        duration_seconds: float,
        bgm_path: Optional[Path] = None,
        bgm_volume: float = 0.12,
    ) -> Path:
        """Combine background visual, audio narration, and subtitles into a final video file."""
        pass

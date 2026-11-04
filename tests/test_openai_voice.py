"""Tests for OpenAIVoiceProvider with fallback support."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from engine.media.base import AudioResult
from engine.media.voice import OpenAIVoiceProvider, DummyVoiceProvider


def test_openai_voice_provider_offline_fallback_without_key(tmp_path: Path):
    """When OPENAI_API_KEY is missing, OpenAIVoiceProvider seamlessly falls back."""
    mock_fallback = MagicMock(spec=DummyVoiceProvider)
    fallback_out = tmp_path / "dummy.wav"
    mock_fallback.generate_audio.return_value = AudioResult(
        file_path=fallback_out,
        duration_seconds=3.0,
        voice_id="dummy",
        provider="DummyVoiceProvider",
    )

    provider = OpenAIVoiceProvider(
        api_key=None,
        fallback_provider=mock_fallback,
    )

    out_file = tmp_path / "speech.mp3"
    result = provider.generate_audio(
        text="Este es un test de OpenAI TTS.",
        voice_id="alloy",
        output_path=out_file,
    )

    assert result.provider == "DummyVoiceProvider"
    mock_fallback.generate_audio.assert_called_once()


def test_openai_voice_provider_synthesis_mock(tmp_path: Path):
    """Test successful OpenAI TTS request and MP4/MP3 output parsing."""
    out_file = tmp_path / "speech.mp3"

    provider = OpenAIVoiceProvider(
        api_key="sk-test-key-12345",
        default_voice="alloy",
    )

    fake_mp3_data = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf58.29.100" + b"\x00" * 2000

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("subprocess.run") as mock_subprocess:

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_mp3_data
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        # Mock ffprobe duration return
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"format": {"duration": "4.25"}}),
            stderr="",
        )

        res = provider.generate_audio(
            text="Prueba de síntesis de voz neuronal de alta fidelidad.",
            voice_id="nova",
            output_path=out_file,
        )

        assert res.provider == "OpenAIVoiceProvider"
        assert res.duration_seconds == 4.25
        assert res.voice_id == "nova"
        assert out_file.exists()


def test_openai_voice_provider_error_fallback(tmp_path: Path):
    """When API returns 429 or 500, fallback provider handles the audio generation."""
    mock_fallback = MagicMock(spec=DummyVoiceProvider)
    mock_fallback.generate_audio.return_value = AudioResult(
        file_path=tmp_path / "fallback.wav",
        duration_seconds=2.5,
        voice_id="dummy",
        provider="DummyVoiceProvider",
    )

    provider = OpenAIVoiceProvider(
        api_key="sk-test-failing-key",
        fallback_provider=mock_fallback,
    )

    with patch("urllib.request.urlopen", side_effect=Exception("HTTP 429 Too Many Requests")):
        out_file = tmp_path / "speech_failed.mp3"
        res = provider.generate_audio(
            text="Texto de prueba.",
            voice_id="alloy",
            output_path=out_file,
        )

        assert res.provider == "DummyVoiceProvider"
        assert mock_fallback.generate_audio.called

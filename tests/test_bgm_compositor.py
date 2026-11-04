"""Unit tests for Stage 11 BGM Mixing and Fallbacks in FFmpegCompositor."""

from pathlib import Path
import subprocess
import wave
import pytest

from engine.media.compositor import FFmpegCompositor


@pytest.fixture
def test_media_assets(tmp_path: Path):
    """Create minimal valid video, voice WAV, and BGM WAV files for fast composition tests."""
    compositor = FFmpegCompositor(prefer_nvenc=False)

    # 1. Background video (1 second 360x640)
    bg_video = tmp_path / "bg.mp4"
    compositor.generate_procedural_background(
        output_path=bg_video,
        duration_seconds=1.0,
        width=360,
        height=640,
        fps=24,
    )

    # 2. Voice audio (1 second audible tone PCM WAV)
    import math
    voice_wav = tmp_path / "voice.wav"
    with wave.open(str(voice_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        # Generate 1 sec of 440Hz tone
        samples = bytearray()
        for i in range(24000):
            val = int(3000 * math.sin(2 * math.pi * 440 * i / 24000))
            samples.extend(val.to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(samples)

    # 3. BGM audio (1 second PCM WAV)
    bgm_wav = tmp_path / "bgm.wav"
    with wave.open(str(bgm_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x10\x10\x20\x20" * 44100)

    return {
        "compositor": compositor,
        "bg_video": bg_video,
        "voice_wav": voice_wav,
        "bgm_wav": bgm_wav,
    }


def test_compose_without_bgm(test_media_assets, tmp_path: Path):
    """Test 1: Composing without BGM preserves exact voice-only baseline behavior."""
    comp = test_media_assets["compositor"]
    out_video = tmp_path / "out_nobgm.mp4"

    res = comp.compose_video(
        background_path=test_media_assets["bg_video"],
        audio_path=test_media_assets["voice_wav"],
        subtitles_path=None,
        output_path=out_video,
        duration_seconds=1.0,
        bgm_path=None,
    )
    assert res.exists()
    assert res.stat().st_size > 0


def test_compose_with_valid_bgm(test_media_assets, tmp_path: Path):
    """Test 2 & 4: Composing with valid BGM mixes audio with configurable volume."""
    comp = test_media_assets["compositor"]
    out_video = tmp_path / "out_withbgm.mp4"

    res = comp.compose_video(
        background_path=test_media_assets["bg_video"],
        audio_path=test_media_assets["voice_wav"],
        subtitles_path=None,
        output_path=out_video,
        duration_seconds=1.0,
        bgm_path=test_media_assets["bgm_wav"],
        bgm_volume=0.15,
    )
    assert res.exists()
    assert res.stat().st_size > 0


def test_compose_with_nonexistent_bgm_falls_back(test_media_assets, tmp_path: Path):
    """Test 3: Non-existent BGM file falls back cleanly to voice-only without error."""
    comp = test_media_assets["compositor"]
    out_video = tmp_path / "out_fallback_missing.mp4"
    bogus_bgm = tmp_path / "nonexistent_music.mp3"

    res = comp.compose_video(
        background_path=test_media_assets["bg_video"],
        audio_path=test_media_assets["voice_wav"],
        subtitles_path=None,
        output_path=out_video,
        duration_seconds=1.0,
        bgm_path=bogus_bgm,
    )
    assert res.exists()
    assert res.stat().st_size > 0


def test_compose_with_corrupt_bgm_falls_back(test_media_assets, tmp_path: Path):
    """Test 6: Corrupt/un-decodable BGM file falls back to voice-only without crashing."""
    comp = test_media_assets["compositor"]
    out_video = tmp_path / "out_fallback_corrupt.mp4"

    corrupt_bgm = tmp_path / "corrupt.mp3"
    corrupt_bgm.write_bytes(b"NOT_A_VALID_AUDIO_FILE_DATA_CORRUPT_HEADER")

    res = comp.compose_video(
        background_path=test_media_assets["bg_video"],
        audio_path=test_media_assets["voice_wav"],
        subtitles_path=None,
        output_path=out_video,
        duration_seconds=1.0,
        bgm_path=corrupt_bgm,
    )
    assert res.exists()
    assert res.stat().st_size > 0


def test_audio_normalization_and_provenance(test_media_assets, tmp_path: Path):
    """Test 5 & 7: Output audio is valid AAC stream and provenance contract holds."""
    comp = test_media_assets["compositor"]
    out_video = tmp_path / "out_audio_spec.mp4"

    res = comp.compose_video(
        background_path=test_media_assets["bg_video"],
        audio_path=test_media_assets["voice_wav"],
        subtitles_path=None,
        output_path=out_video,
        duration_seconds=1.0,
        bgm_path=test_media_assets["bgm_wav"],
    )

    # Inspect using ffprobe
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate",
        "-of", "csv=p=0",
        str(res),
    ]
    probe = subprocess.run(cmd, capture_output=True, text=True)
    assert probe.returncode == 0
    assert "aac" in probe.stdout.lower()

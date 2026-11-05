"""Tests for Phase 3 Audio Director, SFX Library, and Music Synthesis."""

from pathlib import Path
import subprocess
import wave

from engine.audio.audio_director import AudioDirector
from engine.audio.music_director import MusicDirector
from engine.audio.sfx_library import SfxLibrary
from engine.story.storyboard_planner import StoryboardPlanner


def test_sfx_library_synthesizes_valid_audio_cues(tmp_path: Path):
    library = SfxLibrary(sfx_dir=tmp_path / "sfx")

    for tag in ["sword_blade_ring", "thunder_crack", "monster_screech", "cinematic_whoosh"]:
        wav_file = library.get_or_synthesize_sfx(tag, duration_sec=1.5)
        assert wav_file.exists()
        assert wav_file.stat().st_size > 1000

        with wave.open(str(wav_file), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 44100
            assert wf.getsampwidth() == 2


def test_music_director_synthesizes_bgm(tmp_path: Path):
    director = MusicDirector(music_dir=tmp_path / "music")
    bgm_file = director.get_or_synthesize_bgm(
        music_mood="dark_epic",
        total_duration_sec=4.0,
        output_path=tmp_path / "music/test_bgm.wav",
    )

    assert bgm_file.exists()
    assert bgm_file.stat().st_size > 5000
    with wave.open(str(bgm_file), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 44100


def test_audio_director_multitrack_mixing(tmp_path: Path):
    director = AudioDirector(
        sfx_library=SfxLibrary(sfx_dir=tmp_path / "sfx"),
        music_director=MusicDirector(music_dir=tmp_path / "music"),
    )

    planner = StoryboardPlanner()
    storyboard = planner.plan_storyboard(
        raw_prompt="un chico encuentra una espada sagrada en un bosque oscuro y relámpagos",
        target_duration_sec=25.0,
    )

    master_audio = tmp_path / "master_audio.wav"
    res = director.mix_storyboard_audio(storyboard, master_audio)

    assert res.exists()
    assert res.stat().st_size > 10000

    # Probe with ffprobe
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=channels:stream=sample_rate:stream=duration",
        "-of", "default=noprint_wrappers=1",
        str(res),
    ]
    probe_raw = subprocess.check_output(probe_cmd, text=True)
    probe_dict = dict(line.split("=") for line in probe_raw.strip().splitlines() if "=" in line)
    
    assert int(probe_dict.get("channels", 0)) == 2  # Stereo
    assert int(probe_dict.get("sample_rate", 0)) == 48000  # 48kHz
    assert float(probe_dict.get("duration", 0.0)) >= 20.0  # Target ~25s

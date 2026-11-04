"""Tests for real providers: SemanticScriptProvider, Gemini fallback, EdgeTTSVoiceProvider, and VisualProvider."""

from pathlib import Path
import pytest

from engine.media.base import AudioResult
from engine.media.visuals import LocalAssetVisualProvider, ProceduralVisualProvider, get_default_visual_provider
from engine.media.voice import EdgeTTSVoiceProvider, get_default_voice_provider
from engine.scripting.schema import HookType, StructuredScript, VariantPlan
from engine.scripting.scriptwriter import GeminiScriptProvider, SemanticScriptProvider, get_default_script_provider


def test_semantic_script_provider():
    """Verify SemanticScriptProvider generates high-quality natural Spanish scripts."""
    provider = SemanticScriptProvider()
    plan = VariantPlan(
        variant_code="A",
        hook_type=HookType.QUESTION,
        target_duration_sec=25.0,
        topic="la computación cuántica",
        angle="revolución tecnológica",
        parameters={"hook_text": "¿Sabías que la computación cuántica resolverá problemas en segundos?"},
    )

    script = provider.generate_script("Hipótesis sobre retención", plan)
    assert isinstance(script, StructuredScript)
    assert script.hook_type == HookType.QUESTION
    assert script.hook == "¿Sabías que la computación cuántica resolverá problemas en segundos?"
    assert len(script.segments) == 2
    assert script.segments[0].order == 1
    assert script.segments[1].order == 2
    assert "cuántica" in script.full_text().lower()
    assert script.target_duration_sec >= 25.0


def test_gemini_script_provider_fallback_without_key():
    """Verify GeminiScriptProvider falls back to SemanticScriptProvider when no API key is present."""
    provider = GeminiScriptProvider(api_key=None, fallback_provider=SemanticScriptProvider())
    plan = VariantPlan(
        variant_code="B",
        hook_type=HookType.STATEMENT,
        target_duration_sec=30.0,
        topic="la exploración de Marte",
        angle="misterios del planeta rojo",
    )

    script = provider.generate_script("Test statement", plan)
    assert isinstance(script, StructuredScript)
    assert script.hook_type == HookType.STATEMENT
    assert len(script.segments) >= 1
    assert "marte" in script.full_text().lower()


def test_edge_tts_voice_provider(tmp_path: Path):
    """Verify EdgeTTSVoiceProvider generates real natural neural audio."""
    provider = EdgeTTSVoiceProvider(default_voice="es-ES-AlvaroNeural")
    out_file = tmp_path / "voice_test.mp3"

    result = provider.generate_audio(
        text="Este es un test de voz neuronal en español.",
        voice_id="default_offline",
        output_path=out_file,
    )

    assert isinstance(result, AudioResult)
    assert out_file.exists()
    assert out_file.stat().st_size > 1000
    assert result.duration_seconds > 0.5
    assert result.provider == "EdgeTTSVoiceProvider"


def test_edge_tts_fallback_on_error(tmp_path: Path):
    """Verify EdgeTTSVoiceProvider falls back to DummyVoiceProvider if an unresolvable error occurs."""
    # Use invalid voice name to trigger fallback
    provider = EdgeTTSVoiceProvider(default_voice="non_existent_voice_xyz_123")
    out_file = tmp_path / "voice_fallback.wav"

    result = provider.generate_audio(
        text="Prueba de fallback acústico.",
        voice_id="non_existent_voice_xyz_123",
        output_path=out_file,
    )

    assert isinstance(result, AudioResult)
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_procedural_visual_provider(tmp_path: Path):
    """Verify ProceduralVisualProvider generates high-definition vertical video background."""
    provider = ProceduralVisualProvider()
    out_video = tmp_path / "bg_science.mp4"

    # Generate 1.0s video
    res_path = provider.generate_background(
        output_path=out_video,
        duration_seconds=1.0,
        topic="el telescopio espacial y el cosmos",
        width=720,  # Fast resolution for test
        height=1280,
        fps=24,
    )

    assert res_path.exists()
    assert res_path.stat().st_size > 1000


def test_local_asset_visual_provider_fallback(tmp_path: Path):
    """Verify LocalAssetVisualProvider falls back to procedural generator when no local assets exist."""
    empty_assets = tmp_path / "no_assets"
    provider = LocalAssetVisualProvider(assets_dir=empty_assets)
    out_video = tmp_path / "bg_fallback.mp4"

    res_path = provider.generate_background(
        output_path=out_video,
        duration_seconds=1.0,
        topic="inteligencia artificial",
        width=720,
        height=1280,
        fps=24,
    )

    assert res_path.exists()
    assert res_path.stat().st_size > 1000


def test_provider_factories():
    """Verify factory functions resolve valid providers."""
    script_p = get_default_script_provider()
    assert script_p is not None
    voice_p = get_default_voice_provider()
    assert voice_p is not None
    visual_p = get_default_visual_provider()
    assert visual_p is not None


def test_stage9_subtitles_duration_integrity(tmp_path: Path):
    """Verify subtitles span full audio duration and do not collapse into 5.0 seconds."""
    from engine.media.transcription import DummyTranscriptionProvider

    provider = DummyTranscriptionProvider()
    dummy_wav = tmp_path / "audio_dummy.wav"

    # Create a small valid PCM WAV file of 20 seconds
    import wave
    with wave.open(str(dummy_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * (24000 * 20))

    text = "Este es un guion de prueba para verificar que la duración de los subtítulos coincide con el audio total."
    timestamps = provider.transcribe(audio_path=dummy_wav, reference_text=text, duration_seconds=20.0)

    assert len(timestamps) > 5
    assert timestamps[0].start >= 0.0
    # Final subtitle must be close to 20s (not 5s!)
    assert timestamps[-1].end > 17.0
    assert timestamps[-1].end <= 20.5


def test_stage9_word_budget_enforcement():
    """Verify SemanticScriptProvider enforces strict word budget for <30s short videos."""
    provider = SemanticScriptProvider()
    plan = VariantPlan(
        variant_code="A",
        hook_type=HookType.QUESTION,
        target_duration_sec=24.0,  # 24s target
        topic="tecnología",
        angle="curiosidad histórica",
    )

    script = provider.generate_script("Statement", plan)
    total_words = len(script.full_text().split())
    # Word budget for 24s is max 55 words (~2.1 wps)
    assert total_words <= 55, f"Word count {total_words} exceeded max 55 words budget"
    assert total_words >= 30, f"Word count {total_words} is too short"


def test_stage9_knowledge_bank_retrieval():
    """Verify prompt is not contaminated and factual capsule is retrieved from KnowledgeBank."""
    from engine.creative.knowledge import KnowledgeBank
    from engine.creative.interpreter import CreativeInterpreter

    interpreter = CreativeInterpreter()
    prompt = "Un dato curioso sobre tecnologia que sorprenda a alguien en menos de 30 segundos."
    result = interpreter.interpret(prompt)

    # Theme should be clean, not contaminated
    assert "menos de 30" not in result.theme.lower()
    assert "sorprenda a alguien" not in result.theme.lower()
    # Concepts should have real hooks
    for c in result.concepts:
        assert "un dato curioso sobre tecnologia" not in c.hook_text.lower()
        assert len(c.hook_text) > 15
        assert c.target_duration_seconds <= 24.0  # Constraint detected!


def test_stage9_select_concept_with_custom_hook(tmp_path: Path):
    """Verify select_concept supports updating custom hook text."""
    from engine.experiments.repository import ExperimentRepository
    from engine.creative.service import CreativeService

    db_path = tmp_path / "test_stage9.db"
    repo = ExperimentRepository(f"sqlite:///{db_path}")
    repo.init_db()
    service = CreativeService(repository=repo)

    idea = service.capture_idea("Un hecho científico sobre el agua caliente y el hielo")
    concepts = service.analyze_idea(idea.id)
    first_concept = concepts[0]

    edited_hook = "Este es un gancho completamente personalizado por el creador."
    updated = service.select_concept(first_concept.id, custom_hook=edited_hook)

    assert updated.status == "selected"
    assert updated.hook_text == edited_hook


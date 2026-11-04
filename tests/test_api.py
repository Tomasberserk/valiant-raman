"""Tests for Stage 5: FastAPI Backend Adapter, endpoint contracts, polling resilience, and media security."""

from pathlib import Path
import time
from typing import List, Optional
import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from engine.creative.run_dispatcher import LocalRunDispatcher
from engine.creative.service import CreativeService
from engine.experiments.models import ExperimentRun, Render
from engine.experiments.repository import ExperimentRepository
from engine.media.base import AudioResult, Compositor, TranscriptionProvider, VoiceProvider, WordTimestamp
from engine.pipeline import ContentEnginePipeline
from engine.qa.validator import MediaValidator, QAReport
from engine.scripting.scriptwriter import DummyScriptProvider
from web.app import create_app


# --- Test Helpers & Fast Providers ---

class FastDummyVoiceProvider(VoiceProvider):
    def generate_audio(self, text: str, voice_id: str, output_path: Path, rate: str = "+0%", pitch: str = "+0Hz") -> AudioResult:
        output_path.write_bytes(b"RIFF_FAST_AUDIO")
        return AudioResult(file_path=output_path, duration_seconds=1.0, voice_id=voice_id, provider="dummy")


class FastDummyTranscriptionProvider(TranscriptionProvider):
    def transcribe(self, audio_path: Path, reference_text: Optional[str] = None) -> List[WordTimestamp]:
        return [WordTimestamp(word="test", start=0.0, end=1.0)]


class FastDummyCompositor(Compositor):
    def compose_video(self, background_path: Path, audio_path: Path, subtitles_path: Optional[Path], output_path: Path, duration_seconds: float) -> Path:
        output_path.write_bytes(b"FAKE_MP4_HEADER_AND_VIDEO_STREAM")
        return output_path


class FastDummyValidator(MediaValidator):
    def validate_render(self, file_path: Path, expected_duration_sec: float, subtitles_path: Optional[Path] = None) -> QAReport:
        return QAReport(file_path=str(file_path), passed=True, checks=[], metadata={"dummy": True})


@pytest.fixture
def api_client(tmp_path: Path):
    """Set up an isolated test client with fast background execution."""
    db_file = tmp_path / "test_api.db"
    repo = ExperimentRepository(db_url=f"sqlite:///{db_file.as_posix()}")
    repo.init_db()

    pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=DummyScriptProvider(),
        voice_provider=FastDummyVoiceProvider(),
        transcription_provider=FastDummyTranscriptionProvider(),
        compositor=FastDummyCompositor(),
        validator=FastDummyValidator(),
    )

    dispatcher = LocalRunDispatcher(repository=repo, pipeline=pipeline, max_workers=1)
    service = CreativeService(repository=repo, dispatcher=dispatcher)

    app = create_app(repository=repo, dispatcher=dispatcher, service=service)

    with TestClient(app) as client:
        yield client, repo, dispatcher, service, tmp_path


# --- Integration Tests ---

def test_health_check(api_client):
    """Verify system health endpoint."""
    client, _, _, _, _ = api_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_studio_ui_routes(api_client):
    """Verify GET / and GET /studio return HTML UI with 200 OK."""
    client, _, _, _, _ = api_client
    for path in ["/", "/studio"]:
        resp = client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Creative Workspace" in resp.text
        assert "id=\"ideaInput\"" in resp.text


def test_post_idea_capture_and_analyze(api_client):
    """Verify POST /api/ideas captures and deterministically analyzes an idea returning 3 concepts."""
    client, _, _, _, _ = api_client
    payload = {
        "raw_text": "El telescopio espacial James Webb descubre galaxias primitivas masivas que desafían la cosmología estándar.",
        "input_type": "text",
    }
    resp = client.post("/api/ideas", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["id"] is not None
    assert data["theme"] != ""
    assert data["status"] == "analyzed"
    assert len(data["concepts"]) == 3

    # Canonical contrastive concepts
    for idx, c in enumerate(data["concepts"], start=1):
        assert c["concept_number"] == idx
        assert c["status"] == "proposed"
        assert c["hook_text"] != ""
        assert c["hook_type"] in ("QUESTION", "STATEMENT", "SURPRISE")


def test_post_idea_validation_error(api_client):
    """Verify that an idea shorter than 10 characters returns HTTP 400 Bad Request."""
    client, _, _, _, _ = api_client
    resp = client.post("/api/ideas", json={"raw_text": "demasiado"})
    # Pydantic schema enforces min_length=10 -> 422 Unprocessable Entity
    assert resp.status_code in (400, 422)


def test_get_idea_concepts(api_client):
    """Verify GET /api/ideas/{id}/concepts returns active concepts for a known idea."""
    client, _, _, service, _ = api_client
    idea = service.capture_idea("La física cuántica y el entrelazamiento de partículas a través del espacio.")
    service.analyze_idea(idea.id)

    resp = client.get(f"/api/ideas/{idea.id}/concepts")
    assert resp.status_code == 200
    concepts = resp.json()
    assert len(concepts) == 3


def test_get_idea_concepts_not_found(api_client):
    """Verify GET /api/ideas/{id}/concepts returns 404 for an unknown idea ID."""
    client, _, _, _, _ = api_client
    resp = client.get("/api/ideas/00000000-0000-0000-0000-000000000000/concepts")
    assert resp.status_code == 404


def test_select_concept_and_reject_siblings(api_client):
    """Verify POST /api/concepts/{id}/select selects the concept and marks siblings as rejected."""
    client, _, _, service, _ = api_client
    idea = service.capture_idea("El misterio del origen de las auroras boreales en planetas gigantes gaseosos.")
    concepts = service.analyze_idea(idea.id)
    c1, c2, c3 = concepts

    resp = client.post(f"/api/concepts/{c1.id}/select")
    assert resp.status_code == 200
    assert resp.json()["id"] == c1.id
    assert resp.json()["status"] == "selected"

    # Verify siblings became rejected
    assert service.get_concept(c2.id).status == "rejected"
    assert service.get_concept(c3.id).status == "rejected"


def test_reject_concept(api_client):
    """Verify POST /api/concepts/{id}/reject marks a concept as rejected."""
    client, _, _, service, _ = api_client
    idea = service.capture_idea("La evolución de la bioluminiscencia en organismos de fosas abisales.")
    concepts = service.analyze_idea(idea.id)
    c1 = concepts[0]

    resp = client.post(f"/api/concepts/{c1.id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert service.get_concept(c1.id).status == "rejected"


def test_launch_experiment_202_contract(api_client):
    """Verify POST /api/concepts/{id}/launch returns HTTP 202 with run_id and status='queued'."""
    client, _, _, service, _ = api_client
    idea = service.capture_idea("Descubrimiento de exoplanetas habitables mediante telescopios orbitales de nueva generación.")
    concepts = service.analyze_idea(idea.id)
    selected = service.select_concept(concepts[0].id)

    resp = client.post(f"/api/concepts/{selected.id}/launch")
    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "queued"
    assert len(data["run_id"]) == 36


def test_polling_status_lifecycle_and_dto_contract(api_client):
    """Verify GET /api/runs/{run_id}/status returns progress and renders with media_url and NO file_path."""
    client, repo, dispatcher, service, _ = api_client
    idea = service.capture_idea("La formación de agujeros negros supermasivos en el universo temprano.")
    concepts = service.analyze_idea(idea.id)
    selected = service.select_concept(concepts[0].id)

    # Launch experiment
    launch_resp = client.post(f"/api/concepts/{selected.id}/launch")
    assert launch_resp.status_code == 202
    run_id = launch_resp.json()["run_id"]

    # Wait for background completion
    max_wait = 10.0
    start = time.time()
    completed = False
    while time.time() - start < max_wait:
        status_resp = client.get(f"/api/runs/{run_id}/status")
        assert status_resp.status_code == 200
        data = status_resp.json()

        # CONTRACT CHECK: ensure file_path is NEVER leaked in the DTO
        assert "file_path" not in data

        if data["status"] == "completed":
            completed = True
            assert data["progress_percent"] == 100
            assert len(data["renders"]) == 3
            for r in data["renders"]:
                assert "media_url" in r
                assert "file_path" not in r
                assert r["media_url"].startswith(f"/api/media/{run_id}/")
            break
        time.sleep(0.1)

    assert completed is True, "Background execution did not finish in time."


def test_polling_fallback_to_sqlite_after_reboot(api_client):
    """Verify that when memory cache is empty, GET /api/runs/{run_id}/status loads state and renders from SQLite."""
    client, repo, dispatcher, service, _ = api_client
    idea = service.capture_idea("Simulación de colisiones de estrellas de neutrones y síntesis de oro.")
    concepts = service.analyze_idea(idea.id)
    selected = service.select_concept(concepts[0].id)

    launch_resp = client.post(f"/api/concepts/{selected.id}/launch")
    run_id = launch_resp.json()["run_id"]

    # Wait for completion
    for _ in range(50):
        prog = dispatcher.get_progress(run_id)
        if prog and prog.status == "completed":
            break
        time.sleep(0.1)

    # SIMULATE SERVER REBOOT: Clear memory cache completely
    with dispatcher._lock:
        dispatcher._latest_progress.clear()

    # Verify cache is empty
    assert dispatcher.get_progress(run_id) is None

    # Polling should transparently fall back to SQLite via service
    status_resp = client.get(f"/api/runs/{run_id}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["run_id"] == run_id
    assert data["status"] == "completed"
    assert data["progress_percent"] == 100
    assert len(data["renders"]) == 3
    for r in data["renders"]:
        assert r["media_url"].startswith(f"/api/media/{run_id}/")


def test_polling_not_found(api_client):
    """Verify polling an unknown run returns HTTP 404."""
    client, _, _, _, _ = api_client
    resp = client.get("/api/runs/00000000-0000-0000-0000-000000000000/status")
    assert resp.status_code == 404


def test_media_streaming_success(api_client):
    """Verify GET /api/media/{run_id}/{variant} streams existing video MP4 with correct headers."""
    client, repo, dispatcher, service, _ = api_client
    idea = service.capture_idea("El descubrimiento de agua líquida bajo la superficie de la luna Europa.")
    concepts = service.analyze_idea(idea.id)
    selected = service.select_concept(concepts[0].id)

    launch_resp = client.post(f"/api/concepts/{selected.id}/launch")
    run_id = launch_resp.json()["run_id"]

    # Wait for completion
    for _ in range(50):
        prog = dispatcher.get_progress(run_id)
        if prog and prog.status == "completed":
            break
        time.sleep(0.1)

    # Stream variant 'A'
    media_resp = client.get(f"/api/media/{run_id}/A")
    assert media_resp.status_code == 200
    assert "video/mp4" in media_resp.headers.get("content-type", "")
    assert len(media_resp.content) > 0


def test_media_invalid_variant_404(api_client):
    """Verify requesting a non-existent variant for an existing run returns HTTP 404."""
    client, repo, dispatcher, service, _ = api_client
    idea = service.capture_idea("Estudio de la atmósfera de Titán y sus lagos de metano líquido.")
    concepts = service.analyze_idea(idea.id)
    selected = service.select_concept(concepts[0].id)

    launch_resp = client.post(f"/api/concepts/{selected.id}/launch")
    run_id = launch_resp.json()["run_id"]

    for _ in range(50):
        prog = dispatcher.get_progress(run_id)
        if prog and prog.status == "completed":
            break
        time.sleep(0.1)

    # Variant Z does not exist
    resp = client.get(f"/api/media/{run_id}/Z")
    assert resp.status_code == 404


def test_media_anti_path_traversal_forbidden(api_client):
    """Verify that if a Render file path is outside settings.output_dir, the endpoint returns 403 Forbidden."""
    client, repo, _, service, tmp_path = api_client

    # 1. Create a dummy file outside settings.output_dir (e.g. in tmp_path)
    outside_file = tmp_path / "secret.mp4"
    outside_file.write_bytes(b"SECRET_DATA")

    # 2. Register an experiment, run, and rogue render pointing to outside_file
    exp = repo.create_experiment("Rogue Exp", "Testing security")
    hyp = repo.create_hypothesis(exp.id, "statement", "var", "metric", "crit", "base")
    v = repo.create_variant(hyp.id, "Variant Rogue", "R", "QUESTION")
    run = repo.create_run(exp.id, "1.0", "hash", status="completed")

    repo.register_render(
        experiment_run_id=run.id,
        variant_id=v.id,
        file_path=str(outside_file.resolve()),
        duration_seconds=1.0,
        width=1080,
        height=1920,
        fps=30.0,
        codec="libx264",
        file_size_bytes=len(outside_file.read_bytes()),
        render_time_seconds=0.1,
        qa_passed=True,
    )

    # 3. Attempt to stream via media endpoint
    resp = client.get(f"/api/media/{run.id}/R")
    assert resp.status_code == 403, f"Expected 403 Forbidden for path outside output_dir, got {resp.status_code}"


def test_blocked_endpoint(api_client):
    """Verify GET /api/blocked returns structured diagnostic report."""
    client, _, _, _, _ = api_client
    resp = client.get("/api/blocked")
    assert resp.status_code == 200
    data = resp.json()
    assert "fact" in data
    assert "opportunity" in data
    assert "hypothesis" in data
    assert len(data["fact"]) > 0

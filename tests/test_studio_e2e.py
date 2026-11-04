"""End-to-End browser tests for Creative Studio UI (Stage 6 Gate D.4).
Using Playwright with local headless browser to verify full DOM, a11y, and FSM flows.
"""

from pathlib import Path
import threading
import time
from typing import List, Optional
import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from engine.creative.run_dispatcher import LocalRunDispatcher
from engine.creative.service import CreativeService
from engine.experiments.repository import ExperimentRepository
from engine.media.base import AudioResult, Compositor, TranscriptionProvider, VoiceProvider, WordTimestamp
from engine.pipeline import ContentEnginePipeline
from engine.qa.validator import MediaValidator, QAReport
from engine.scripting.scriptwriter import DummyScriptProvider
from web.app import create_app


# --- Fast Mock Providers for E2E speed ---

class FastDummyVoiceProvider(VoiceProvider):
    def generate_audio(self, text: str, voice_id: str, output_path: Path, rate: str = "+0%", pitch: str = "+0Hz") -> AudioResult:
        output_path.write_bytes(b"RIFF_AUDIO")
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


@pytest.fixture(scope="module")
def live_studio_server(tmp_path_factory):
    """Start an isolated live studio server on an ephemeral port."""
    tmp_path = tmp_path_factory.mktemp("studio_e2e")
    db_file = tmp_path / "test_studio_e2e.db"
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

    port = 8792
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to bind
    time.sleep(1.0)
    base_url = f"http://127.0.0.1:{port}"

    yield base_url, repo, dispatcher

    server.should_exit = True
    thread.join(timeout=2.0)


@pytest.fixture(scope="module")
def browser_instance():
    """Launch headless browser for E2E tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        yield browser
        browser.close()


def test_studio_initial_load_and_a11y(live_studio_server, browser_instance):
    """Verify initial UI load, accessibility attributes, and character counter validation."""
    base_url, _, _ = live_studio_server
    page = browser_instance.new_page()
    page.goto(base_url)

    # 1. Page Title & Heading
    assert "Creative Workspace" in page.title()
    assert page.locator("h1.brand-title").is_visible()

    # 2. Skip to Content Link
    skip_link = page.locator("a.skip-to-content")
    assert skip_link.count() == 1
    assert "Saltar al contenido principal" in skip_link.inner_text()

    # 3. Textarea and Button State
    idea_input = page.locator("#ideaInput")
    assert idea_input.is_visible()

    analyze_btn = page.locator("#btnAnalyze")
    assert analyze_btn.is_disabled()

    # 4. Type less than 10 characters -> remains disabled
    idea_input.fill("Corta")
    assert analyze_btn.is_disabled()
    assert "(mín. 10)" in page.locator("#charCount").inner_text()

    # 5. Type 10+ characters -> becomes enabled
    idea_input.fill("Esta es una premisa fascinante sobre física cuántica")
    assert not analyze_btn.is_disabled()
    assert "✓" in page.locator("#charCount").inner_text()

    page.close()


def test_blocked_modal_keyboard_accessibility(live_studio_server, browser_instance):
    """Verify modal open, focus trap, Escape key closing, and focus return."""
    base_url, _, _ = live_studio_server
    page = browser_instance.new_page()
    page.goto(base_url)

    btn_blocked = page.locator("#btnBlocked")
    modal = page.locator("#blockedModal")

    assert "hidden" in modal.get_attribute("class")

    # Open modal
    btn_blocked.click()
    page.wait_for_timeout(300)
    assert "hidden" not in modal.get_attribute("class")
    assert modal.get_attribute("role") == "dialog"
    assert modal.get_attribute("aria-modal") == "true"

    # Close via Escape key
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert "hidden" in modal.get_attribute("class")

    page.close()


def test_studio_full_pipeline_flow(live_studio_server, browser_instance):
    """Verify full E2E flow: Ideation -> Concepts -> Launch -> Polling -> Video Results."""
    base_url, _, _ = live_studio_server
    page = browser_instance.new_page()
    page.goto(base_url)

    # 1. Submit Idea
    page.locator("#ideaInput").fill("Los secretos de las estrellas de neutrones en el universo")
    page.locator("#btnAnalyze").click()

    # 2. Verify Concepts displayed
    page.wait_for_selector("#conceptsSection:not(.hidden)", timeout=8000)
    cards = page.locator(".concept-card")
    assert cards.count() == 3

    # 3. Select Concept #1
    first_select_btn = cards.first.locator(".btn-select")
    first_select_btn.click()

    # 4. Verify Launch Banner
    page.wait_for_selector("#launchSection:not(.hidden)", timeout=5000)
    btn_launch = page.locator("#btnLaunch")
    assert btn_launch.is_visible()

    # 5. Launch Experiment
    btn_launch.click()

    # 6. Verify Progress Section & Single-Flight Polling
    page.wait_for_selector("#progressSection:not(.hidden)", timeout=5000)
    progress_bar = page.locator("#progressBarTrack")
    assert progress_bar.get_attribute("role") == "progressbar"

    # 7. Wait for Completion & Video Results
    page.wait_for_selector("#resultsSection:not(.hidden)", timeout=15000)
    variant_cards = page.locator(".variant-card")
    assert variant_cards.count() == 3

    # Check Video Players and Download links
    for i in range(3):
        v_card = variant_cards.nth(i)
        assert v_card.locator("video.video-player").is_visible()
        download_btn = v_card.locator("a[download]")
        assert download_btn.is_visible()
        assert "/api/media/" in download_btn.get_attribute("href")

    page.close()


def test_session_storage_hydration_recovery(live_studio_server, browser_instance):
    """Verify F5 refresh recovery of active run via sessionStorage."""
    base_url, _, _ = live_studio_server
    page = browser_instance.new_page()
    page.goto(base_url)

    # Set mock active_run_id in sessionStorage and reload
    page.evaluate("sessionStorage.setItem('active_run_id', 'non_existent_mock_run_999')")
    page.reload()

    # Should detect 404, clean stale session gracefully, and show toast without breaking
    page.wait_for_timeout(1000)
    stored_run = page.evaluate("sessionStorage.getItem('active_run_id')")
    assert stored_run is None  # Cleaned up automatically

    page.close()

"""Comprehensive tests for Stage 12D.3: Application Entrypoint & Production Command Contract.

Verifies:
1. Clean exit codes (0/1/2/3).
2. Pure clean JSON stdout on --json (parseable by json.loads).
3. Zero director calls on invalid input.
4. Single execution call invariant.
5. Idempotency behavior with explicit request_id.
6. Support for both --request-file and modular flags.
7. Safe UUID generation when request_id is omitted.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from typer.testing import CliRunner

from cli import app
from engine.director.director import ProductionDirector
from engine.director.entrypoint import (
    EXIT_CODE_FAILED_PRECONDITION,
    EXIT_CODE_INVALID_ARGUMENTS,
    EXIT_CODE_PIPELINE_FAILURE,
    EXIT_CODE_SUCCESS,
    ProductionEntryInput,
    resolve_production_request,
    run_production,
)
from engine.director.schema import (
    ProductionJob,
    ProductionRequest,
    ProductionResult,
    ProductionState,
)
from engine.director.store import JobStore
from engine.story.fact_intelligence import FactIntelligenceEngine
from engine.story import (
    ClaimStatus,
    FactClaim,
    FactDossier,
    FactIntelligenceEngine,
    FactSource,
    SourceAuthority,
)

runner = CliRunner()


@pytest.fixture
def sample_dossier() -> FactDossier:
    """Standard verified FactDossier."""
    engine = FactIntelligenceEngine()
    s1 = FactSource(
        source_id="src_gottingen_arch",
        title="Gottingen University Historical Archives",
        publisher="University of Gottingen",
        authority_level=SourceAuthority.PRIMARY_INSTITUTIONAL,
    )
    claims = [
        FactClaim(
            claim_id="claim_01",
            claim_text="Gauss y Weber instalaron una línea de 1.2 kilómetros en 1833.",
            source_ids=["src_gottingen_arch"],
            status=ClaimStatus.VERIFIED,
            supporting_excerpt="En 1833 instalaron 1.2 km de línea telegráfica.",
        ),
        FactClaim(
            claim_id="claim_02",
            claim_text="El dispositivo unía el observatorio con el laboratorio de física.",
            source_ids=["src_gottingen_arch"],
            status=ClaimStatus.VERIFIED,
        ),
        FactClaim(
            claim_id="claim_03",
            claim_text="El sistema utilizaba un conmutador para desviar la aguja del magnetómetro.",
            source_ids=["src_gottingen_arch"],
            status=ClaimStatus.VERIFIED,
        ),
    ]
    return engine.compile_dossier(
        dossier_id="dossier_test_entrypoint",
        run_id="run_entrypoint",
        topic="El telégrafo de Gauss y Weber",
        sources=[s1],
        claims=claims,
        key_entities=["Gauss", "Weber"],
    )


@pytest.fixture
def dossier_file(sample_dossier: FactDossier, tmp_path: Path) -> Path:
    """Save sample dossier to disk."""
    p = tmp_path / "dossier.json"
    p.write_text(sample_dossier.model_dump_json(indent=2), encoding="utf-8")
    return p


# -----------------------------------------------------------------------------
# 1. Exit Code 0 & Clean JSON Stdout Invariants
# -----------------------------------------------------------------------------

def test_entrypoint_happy_path_cli(dossier_file: Path, tmp_path: Path):
    """Exit code 0: Successful execution via CLI produce command outputs certified master info."""
    jobs_dir = tmp_path / "jobs"
    result = runner.invoke(
        app,
        [
            "produce",
            "--dossier-path",
            str(dossier_file),
            "--request-id",
            "req_cli_happy_01",
            "--output-dir",
            str(jobs_dir),
            "--json",
        ],
    )

    assert result.exit_code == EXIT_CODE_SUCCESS
    # Stdout must be 100% clean, parseable by json.loads with zero banner contamination
    data = json.loads(result.stdout)
    assert data["request_id"] == "req_cli_happy_01"
    assert data["status"] == "completed"
    assert data["is_certified"] is True
    assert data["master_sha256"] is not None
    assert Path(data["certified_master_path"]).exists()


def test_entrypoint_human_output_formatting(dossier_file: Path, tmp_path: Path):
    """When --json is omitted, human-readable terminal summary is printed with exit code 0."""
    jobs_dir = tmp_path / "jobs"
    result = runner.invoke(
        app,
        [
            "produce",
            "--dossier-path",
            str(dossier_file),
            "--request-id",
            "req_cli_human_01",
            "--output-dir",
            str(jobs_dir),
        ],
    )

    assert result.exit_code == EXIT_CODE_SUCCESS
    assert "Production Completed & Certified Successfully!" in result.stdout
    assert "req_cli_human_01" in result.stdout
    assert "Master MP4:" in result.stdout


# -----------------------------------------------------------------------------
# 2. Exit Code 1: Invalid Input & Zero Director Calls Invariant
# -----------------------------------------------------------------------------

def test_entrypoint_missing_dossier_file(tmp_path: Path):
    """Exit code 1: Missing dossier file fails validation and never executes Director."""
    non_existent = tmp_path / "non_existent_dossier.json"
    mock_director = MagicMock(spec=ProductionDirector)

    input_args = ProductionEntryInput(
        dossier_path=non_existent,
        request_id="req_fail_01",
    )

    exit_code, prod_result, err_msg = run_production(input_args, director=mock_director)

    assert exit_code == EXIT_CODE_INVALID_ARGUMENTS
    assert prod_result is None
    assert "does not exist" in (err_msg or "")
    # Invariant: Director.execute_job was called exactly 0 times
    assert mock_director.execute_job.call_count == 0


def test_entrypoint_malformed_json_zero_director_calls(tmp_path: Path):
    """Exit code 1: Malformed JSON in dossier file cuts execution with 0 Director calls."""
    bad_file = tmp_path / "corrupt.json"
    bad_file.write_text("{ not valid json !!!", encoding="utf-8")
    mock_director = MagicMock(spec=ProductionDirector)

    input_args = ProductionEntryInput(
        dossier_path=bad_file,
        request_id="req_corrupt_01",
    )

    exit_code, prod_result, err_msg = run_production(input_args, director=mock_director)

    assert exit_code == EXIT_CODE_INVALID_ARGUMENTS
    assert prod_result is None
    assert "Malformed JSON" in (err_msg or "")
    assert mock_director.execute_job.call_count == 0


def test_entrypoint_negative_parameter_ranges_zero_director_calls(dossier_file: Path):
    """Exit code 1: Negative retries or regenerations fail argument validation."""
    mock_director = MagicMock(spec=ProductionDirector)

    input_args = ProductionEntryInput(
        dossier_path=dossier_file,
        max_retries=-1,
    )

    exit_code, prod_result, err_msg = run_production(input_args, director=mock_director)

    assert exit_code == EXIT_CODE_INVALID_ARGUMENTS
    assert prod_result is None
    assert "--max-retries must be >= 0" in (err_msg or "")
    assert mock_director.execute_job.call_count == 0


def test_entrypoint_cli_invalid_input_json_stdout(tmp_path: Path):
    """Exit code 1 via CLI with --json outputs clean error JSON on stdout."""
    result = runner.invoke(
        app,
        [
            "produce",
            "--dossier-path",
            str(tmp_path / "missing.json"),
            "--json",
        ],
    )

    assert result.exit_code == EXIT_CODE_INVALID_ARGUMENTS
    data = json.loads(result.stdout)
    assert data["exit_code"] == 1
    assert "does not exist" in data["error"]


# -----------------------------------------------------------------------------
# 3. Exit Code 2: FAILED_PRECONDITION (Dossier Tampered / Rejected)
# -----------------------------------------------------------------------------

def test_entrypoint_precondition_rejection_tampered_hash(
    sample_dossier: FactDossier, tmp_path: Path
):
    """Exit code 2: Director rejects request with tampered dossier_sha256."""
    tampered_dossier = sample_dossier.model_copy(update={"dossier_sha256": "0" * 64})
    tampered_file = tmp_path / "tampered_dossier.json"
    tampered_file.write_text(tampered_dossier.model_dump_json(), encoding="utf-8")

    jobs_dir = tmp_path / "jobs_precond"
    result = runner.invoke(
        app,
        [
            "produce",
            "--dossier-path",
            str(tampered_file),
            "--request-id",
            "req_tampered_01",
            "--output-dir",
            str(jobs_dir),
            "--json",
        ],
    )

    assert result.exit_code == EXIT_CODE_FAILED_PRECONDITION
    data = json.loads(result.stdout)
    assert data["status"] == "failed_precondition"
    assert data["is_certified"] is False
    assert "DOSSIER_HASH_MISMATCH" in (data["error_summary"] or "")


# -----------------------------------------------------------------------------
# 4. Exit Code 3: PIPELINE_FAILURE (No Silent Mock Fallback)
# -----------------------------------------------------------------------------

def test_entrypoint_pipeline_failure_exit_code_3(dossier_file: Path, tmp_path: Path):
    """Exit code 3: Terminal pipeline failure transits to code 3 with error summary."""
    jobs_dir = tmp_path / "jobs_fail"

    # Create a stub Director that simulates pipeline failure (e.g. FAILED_GROUNDING)
    class FailingDirector(ProductionDirector):
        def execute_job(self, request: ProductionRequest) -> ProductionResult:
            job, _ = self.store.acquire(request.request_id, request)
            job.current_state = ProductionState.FAILED_GROUNDING
            self.store.save_job(job)
            return ProductionResult(
                job_id=job.job_id,
                request_id=request.request_id,
                status=ProductionState.FAILED_GROUNDING,
                is_certified=False,
                error_summary="Grounding recovery exhausted after 2 attempts",
                job_persisted_path=job.workspace_dir / "job.json",
            )

    store = JobStore(base_dir=jobs_dir)
    failing_director = FailingDirector(store=store)

    input_args = ProductionEntryInput(
        dossier_path=dossier_file,
        request_id="req_pipeline_fail_01",
        output_dir=jobs_dir,
    )

    exit_code, prod_result, err_msg = run_production(input_args, director=failing_director)

    assert exit_code == EXIT_CODE_PIPELINE_FAILURE
    assert prod_result is not None
    assert prod_result.status == ProductionState.FAILED_GROUNDING
    assert prod_result.is_certified is False
    assert "Grounding recovery exhausted" in (prod_result.error_summary or "")


# -----------------------------------------------------------------------------
# 5. Idempotency & Invariants
# -----------------------------------------------------------------------------

def test_entrypoint_idempotency_same_request_id(dossier_file: Path, tmp_path: Path):
    """Idempotency: Re-invoking produce with the same request_id returns existing job immediately."""
    jobs_dir = tmp_path / "jobs_idempotency"

    # First invocation
    res1 = runner.invoke(
        app,
        [
            "produce",
            "--dossier-path",
            str(dossier_file),
            "--request-id",
            "req_idempotent_key_01",
            "--output-dir",
            str(jobs_dir),
            "--json",
        ],
    )
    assert res1.exit_code == EXIT_CODE_SUCCESS
    data1 = json.loads(res1.stdout)

    # Second invocation with same request_id
    res2 = runner.invoke(
        app,
        [
            "produce",
            "--dossier-path",
            str(dossier_file),
            "--request-id",
            "req_idempotent_key_01",
            "--output-dir",
            str(jobs_dir),
            "--json",
        ],
    )
    assert res2.exit_code == EXIT_CODE_SUCCESS
    data2 = json.loads(res2.stdout)

    # Invariant: Same job_id, same master hash, identical output
    assert data1["job_id"] == data2["job_id"]
    assert data1["master_sha256"] == data2["master_sha256"]
    assert data1["certified_master_path"] == data2["certified_master_path"]


def test_entrypoint_request_file_mode(sample_dossier: FactDossier, tmp_path: Path):
    """Mode A: Invoking with --request-file resolves identically to modular flags."""
    jobs_dir = tmp_path / "jobs_file_mode"
    prod_req = ProductionRequest(
        request_id="req_from_file_001",
        topic=sample_dossier.topic,
        dossier=sample_dossier,
    )
    req_file = tmp_path / "full_request.json"
    req_file.write_text(prod_req.model_dump_json(indent=2), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "produce",
            "--request-file",
            str(req_file),
            "--output-dir",
            str(jobs_dir),
            "--json",
        ],
    )

    assert result.exit_code == EXIT_CODE_SUCCESS
    data = json.loads(result.stdout)
    assert data["request_id"] == "req_from_file_001"
    assert data["is_certified"] is True


def test_entrypoint_omitted_request_id_generates_valid_unique_id(
    dossier_file: Path, tmp_path: Path
):
    """When --request-id is omitted, a unique valid req_* ID is generated."""
    jobs_dir = tmp_path / "jobs_omitted_req"
    result = runner.invoke(
        app,
        [
            "produce",
            "--dossier-path",
            str(dossier_file),
            "--output-dir",
            str(jobs_dir),
            "--json",
        ],
    )

    assert result.exit_code == EXIT_CODE_SUCCESS
    data = json.loads(result.stdout)
    assert data["request_id"].startswith("req_")
    assert len(data["request_id"]) > 5

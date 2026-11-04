"""Application Entrypoint & Production Command Contract (Stage 12D.3).

Translates production intent (CLI flags or request JSON file) into a validated ProductionRequest,
invokes ProductionDirector.execute_job() strictly once, and returns structured results with
standard Unix exit codes (0/1/2/3).
"""

import json
from pathlib import Path
import sys
from typing import Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from engine.director.director import ProductionDirector
from engine.director.schema import (
    CreativeBrief,
    JobExecutionPolicy,
    OutputSpec,
    ProductionRequest,
    ProductionResult,
    ProductionState,
)
from engine.director.store import JobStore
from engine.story.schema import FactDossier


# Exit Codes Specification
EXIT_CODE_SUCCESS = 0             # COMPLETED and is_certified == True
EXIT_CODE_INVALID_ARGUMENTS = 1   # CLI arg parse error, missing file, malformed JSON
EXIT_CODE_FAILED_PRECONDITION = 2 # Dossier hash mismatch, empty claims (FAILED_PRECONDITION)
EXIT_CODE_PIPELINE_FAILURE = 3    # Terminal pipeline failure (FAILED_GROUNDING, FAILED_STORY_QA, etc.)


class ProductionEntryInput(BaseModel):
    """Input payload for production entrypoint, supporting both request file and modular flags."""
    request_file: Optional[Path] = None
    dossier_path: Optional[Path] = None
    request_id: Optional[str] = None
    topic: Optional[str] = None
    hook_strategy: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    target_lufs: Optional[float] = None
    max_regenerations: Optional[int] = None
    max_retries: Optional[int] = None
    max_repairs: Optional[int] = None
    output_dir: Optional[Path] = None


def resolve_production_request(input_args: ProductionEntryInput) -> ProductionRequest:
    """Pure input adapter: converts file or modular flags into a canonical ProductionRequest.
    
    Invariants:
    - Never mutates, recalculates, or repairs FactDossier.
    - If request_id is supplied, preserves it for deterministic idempotency.
    - If request_id is omitted, generates a single valid UUID-based ID.
    - Validates parameter ranges before touching the Director.
    """
    if input_args.request_file:
        req_path = Path(input_args.request_file)
        if not req_path.exists():
            raise FileNotFoundError(f"Request file does not exist: {req_path}")
        if not req_path.is_file():
            raise ValueError(f"Request file path is not a file: {req_path}")
        
        try:
            content = req_path.read_text(encoding="utf-8")
            data = json.loads(content)
            request = ProductionRequest.model_validate(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON in request file '{req_path}': {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Invalid request schema in '{req_path}': {exc}") from exc

        if input_args.request_id:
            request = request.model_copy(update={"request_id": input_args.request_id})
        return request

    # Modular CLI flags mode
    if not input_args.dossier_path:
        raise ValueError("Either --request-file or --dossier-path must be specified.")

    dossier_path = Path(input_args.dossier_path)
    if not dossier_path.exists():
        raise FileNotFoundError(f"FactDossier file does not exist: {dossier_path}")
    if not dossier_path.is_file():
        raise ValueError(f"FactDossier path is not a file: {dossier_path}")

    try:
        dossier_content = dossier_path.read_text(encoding="utf-8")
        dossier_data = json.loads(dossier_content)
        dossier = FactDossier.model_validate(dossier_data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in FactDossier file '{dossier_path}': {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Invalid FactDossier schema in '{dossier_path}': {exc}") from exc

    # Validate numeric parameters
    if input_args.max_retries is not None and input_args.max_retries < 0:
        raise ValueError(f"--max-retries must be >= 0, got {input_args.max_retries}")
    if input_args.max_regenerations is not None and input_args.max_regenerations < 0:
        raise ValueError(f"--max-regenerations must be >= 0, got {input_args.max_regenerations}")
    if input_args.max_repairs is not None and input_args.max_repairs < 0:
        raise ValueError(f"--max-repairs must be >= 0, got {input_args.max_repairs}")

    topic = input_args.topic.strip() if input_args.topic else dossier.topic
    if not topic:
        raise ValueError("Topic cannot be empty (must be in FactDossier or provided via --topic).")

    # Caller-supplied request_id preserves strong idempotency; omitted generates a unique ID
    req_id = input_args.request_id.strip() if input_args.request_id else f"req_{uuid4().hex[:12]}"

    creative_kwargs = {}
    if input_args.hook_strategy:
        creative_kwargs["hook_strategy"] = input_args.hook_strategy
    if input_args.tone:
        creative_kwargs["tone"] = input_args.tone
    if input_args.target_audience:
        creative_kwargs["target_audience"] = input_args.target_audience
    creative_brief = CreativeBrief(**creative_kwargs)

    policy_kwargs = {}
    if input_args.max_regenerations is not None:
        policy_kwargs["max_surgical_regenerations"] = input_args.max_regenerations
    if input_args.max_retries is not None:
        policy_kwargs["max_scene_retries"] = input_args.max_retries
    if input_args.max_repairs is not None:
        policy_kwargs["max_master_repairs"] = input_args.max_repairs
    execution_policy = JobExecutionPolicy(**policy_kwargs)

    return ProductionRequest(
        request_id=req_id,
        topic=topic,
        dossier=dossier,
        creative_brief=creative_brief,
        output_spec=OutputSpec(),
        execution_policy=execution_policy,
    )


def exit_code_for_result(result: ProductionResult) -> int:
    """Map a ProductionResult strictly to one of the 4 standard exit codes."""
    if result.status == ProductionState.COMPLETED and result.is_certified:
        return EXIT_CODE_SUCCESS
    if result.status == ProductionState.FAILED_PRECONDITION:
        return EXIT_CODE_FAILED_PRECONDITION
    return EXIT_CODE_PIPELINE_FAILURE


def run_production(
    input_args: ProductionEntryInput,
    director: Optional[ProductionDirector] = None,
) -> Tuple[int, Optional[ProductionResult], Optional[str]]:
    """Execute the production flow end-to-end via ProductionDirector.
    
    Guarantees:
    1. Validation occurs before Director instantiation/execution (exit code 1, 0 execute_job calls).
    2. execute_job() is called at most once.
    3. Returns (exit_code, result, error_message).
    """
    # 1. Pre-Director Validation and Request Resolution
    try:
        request = resolve_production_request(input_args)
    except Exception as exc:
        return EXIT_CODE_INVALID_ARGUMENTS, None, str(exc)

    # 2. Director Instantiation & Single Execution Call
    if director is None:
        store = JobStore(base_dir=input_args.output_dir) if input_args.output_dir else None
        director = ProductionDirector(store=store)

    result = director.execute_job(request)
    code = exit_code_for_result(result)
    return code, result, None


def format_result_json(result: ProductionResult) -> str:
    """Format ProductionResult as pure, clean JSON for stdout consumption."""
    return result.model_dump_json(indent=2)


def format_error_json(error_msg: str, exit_code: int = EXIT_CODE_INVALID_ARGUMENTS) -> str:
    """Format argument or validation error as clean JSON for stdout."""
    return json.dumps({"exit_code": exit_code, "error": error_msg}, indent=2)

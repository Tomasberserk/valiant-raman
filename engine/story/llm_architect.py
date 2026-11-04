"""LLM Story Architect (Stage 12C.2).

Orchestrates creative narrative synthesis from a FactDossier:
1. Translates FactDossier + CreativeBrief into a structured LLM prompt.
2. Generates a structured StoryDraft via decoupled LLMProvider.
3. Submits draft to ClaimGroundingGate for factual verification.
4. Executes automated surgical regeneration loop for any failing scene.
5. Converts approved StoryDraft into a production-ready Stage 12B StoryArc.
"""

from typing import Any, Dict, Optional, Tuple
from engine.story.grounding_gate import ClaimGroundingGate
from engine.story.llm_provider import LLMProvider
from engine.story.schema import (
    FactDossier,
    GroundingReport,
    StoryArc,
    StoryDraft,
)


class LLMStoryArchitect:
    """Orchestrator for grounded, claim-backed narrative generation."""

    def __init__(
        self,
        provider: LLMProvider,
        gate: Optional[ClaimGroundingGate] = None,
        max_retries: int = 3,
    ):
        self.provider = provider
        self.gate = gate or ClaimGroundingGate()
        self.max_retries = max_retries

    def architect_story(
        self,
        dossier: FactDossier,
        creative_brief: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[StoryArc], StoryDraft, GroundingReport]:
        """Synthesize a complete grounded StoryArc from the authoritative FactDossier."""
        brief = creative_brief or {}
        target_hook = brief.get("hook_strategy", "surprise")
        tone = brief.get("tone", "curious_informative")
        target_audience = brief.get("target_audience", "general")

        prompt = self._compose_architect_prompt(dossier, target_hook, tone, target_audience)

        # 1. Generate structured initial draft
        draft = self.provider.generate_structured(prompt, StoryDraft)

        # 2. Gate evaluation
        report = self.gate.evaluate_draft(draft, dossier)

        # 3. Surgical regeneration loop for failing scenes
        retry_count = 0
        while not report.passed and retry_count < self.max_retries:
            retry_count += 1
            failing_scene_ids = [sid for sid, passed in report.scene_status.items() if not passed]

            if not failing_scene_ids:
                # Failure is global (e.g. hash mismatch) and cannot be cured by scene regeneration
                break

            for sid in failing_scene_ids:
                scene_errors = [
                    f for f in report.findings if f.scene_id == sid and f.severity == "ERROR"
                ]
                remediation_hint = " | ".join(f.remediation for f in scene_errors)
                draft = self.gate.surgical_regenerate_scene(
                    draft=draft,
                    scene_id=sid,
                    dossier=dossier,
                    provider=self.provider,
                    remediation_hint=remediation_hint,
                )

            report = self.gate.evaluate_draft(draft, dossier)

        # 4. Final conversion if approved
        if report.passed:
            arc = self.gate.convert_draft_to_story_arc(draft, dossier)
            return arc, draft, report

        return None, draft, report

    def _compose_architect_prompt(
        self,
        dossier: FactDossier,
        hook_strategy: str,
        tone: str,
        target_audience: str,
    ) -> str:
        """Construct the prompt guiding the LLM to ground all facts strictly in the dossier."""
        claims_listing = []
        for cid, claim in dossier.claims.items():
            prohib = f" [Prohibited: {claim.prohibited_wording}]" if claim.prohibited_wording else ""
            claims_listing.append(f"- ID: {cid} | Text: \"{claim.claim_text}\" | Status: {claim.status.value}{prohib}")

        claims_str = "\n".join(claims_listing)
        entities_str = ", ".join(dossier.key_entities) if dossier.key_entities else "None"
        milestones_str = "\n".join(f"- {m}" for m in dossier.timeline_milestones) if dossier.timeline_milestones else "None"

        return (
            f"You are the Lead Story Architect. Create a short-form vertical video narrative.\n\n"
            f"TOPIC: {dossier.topic}\n"
            f"DOSSIER ID: {dossier.dossier_id}\n"
            f"DOSSIER SHA-256: {dossier.dossier_sha256}\n"
            f"KEY ENTITIES: {entities_str}\n"
            f"TIMELINE MILESTONES:\n{milestones_str}\n\n"
            f"FACTUAL EVIDENCE DOSSIER (MANDATORY TRUTH SOURCE):\n{claims_str}\n\n"
            f"CREATIVE REQUIREMENTS:\n"
            f"- Hook Strategy: {hook_strategy}\n"
            f"- Tone: {tone}\n"
            f"- Target Audience: {target_audience}\n"
            f"- Total Duration Target: ~78 seconds (split across 5 scenes: hook, origin_context, development_turning_point, transformation, payoff)\n"
            f"- Every statement MUST be decomposed into AssertionUnits.\n"
            f"- Any FACTUAL statement MUST include the exact claim_ids backing it.\n"
            f"- You have narrative freedom on NARRATIVE and TRANSITION statements (no claim_ids required).\n"
            f"- Strictly avoid prohibited wording or overclaiming superlatives.\n\n"
            f"Output the complete StoryDraft conforming to schema."
        )

"""Story QA Engine (Stage 12B.1).

Performs comprehensive cognitive and contract validation on StoryArc:
1. Duration policy check (hard minimum 61.0s, planning target 78.0s, soft maximum 90.0s).
2. Narrative coherence check (opening hook, resolution payoff, required entities, forbidden pitfalls).
3. Scene dependency validation (topological order, existence, no forward/self references).
4. Claim integrity validation (reject CONTRADICTED, require scope/wording_constraints on CONTEXT_REQUIRED, flag UNCERTAIN).
5. Visual brief integrity check (presence, prohibited_mismatches).
"""

from typing import Dict, List, Set

from engine.story.schema import (
    ClaimStatus,
    NarrativeRole,
    Scene,
    StoryArc,
    StoryQAFinding,
    StoryQAReport,
)


class StoryQAEngine:
    """Evaluates narrative contracts, claim integrity, and production readiness."""

    def evaluate(self, story: StoryArc) -> StoryQAReport:
        """Run all Story QA checks on the provided StoryArc."""
        findings: List[StoryQAFinding] = []
        checks: Dict[str, bool] = {}

        # 1. Duration policy validation
        dur_passed = self._validate_duration_policy(story, findings)
        checks["duration_policy"] = dur_passed

        # 2. Narrative coherence validation
        narrative_passed = self._validate_narrative_coherence(story, findings)
        checks["narrative_coherence"] = narrative_passed

        # 3. Scene dependencies validation
        deps_passed = self._validate_scene_dependencies(story, findings)
        checks["scene_dependencies"] = deps_passed

        # 4. Claim integrity validation
        claims_passed = self._validate_claim_integrity(story, findings)
        checks["claim_integrity"] = claims_passed

        # 5. Visual brief integrity validation
        visual_passed = self._validate_visual_briefs(story, findings)
        checks["visual_brief_integrity"] = visual_passed

        # Aggregate overall status
        has_error = any(f.severity == "ERROR" for f in findings)
        overall_passed = not has_error

        # Update StoryArc and Scene statuses
        story.status = "qa_passed" if overall_passed else "qa_failed"
        for scene in story.scenes:
            scene_errors = [
                f.message for f in findings if f.scene_id == scene.id and f.severity == "ERROR"
            ]
            scene.scene_qa_passed = len(scene_errors) == 0
            scene.scene_qa_failures = scene_errors

        return StoryQAReport(
            passed=overall_passed,
            total_estimated_duration_sec=story.total_estimated_duration_sec,
            findings=findings,
            checks=checks,
        )

    def _validate_duration_policy(self, story: StoryArc, findings: List[StoryQAFinding]) -> bool:
        """Enforce the 3-tier duration policy:

        < hard_minimum_sec (61.0s) -> ERROR
        > soft_maximum_sec (90.0s) -> WARNING (PASS WITH NOTE)
        """
        policy = story.contract.duration_policy
        total_dur = story.total_estimated_duration_sec

        if total_dur < policy.hard_minimum_sec:
            findings.append(
                StoryQAFinding(
                    rule="duration_policy_hard_minimum",
                    severity="ERROR",
                    message=(
                        f"Total estimated duration {total_dur:.1f}s is below the mandatory hard minimum "
                        f"of {policy.hard_minimum_sec:.1f}s required for monetizable vertical formats."
                    ),
                    remediation=(
                        f"Expand existing scenes or add another narrative scene to achieve at least "
                        f"{policy.hard_minimum_sec:.1f}s (planning target: {policy.planning_target_sec:.1f}s)."
                    ),
                )
            )
            return False

        if total_dur > policy.soft_maximum_sec:
            findings.append(
                StoryQAFinding(
                    rule="duration_policy_soft_maximum",
                    severity="WARNING",
                    message=(
                        f"Total estimated duration {total_dur:.1f}s exceeds soft maximum of "
                        f"{policy.soft_maximum_sec:.1f}s. This is permitted but may impact short-form pacing."
                    ),
                    remediation=(
                        f"Optionally trim narration to stay closer to target {policy.planning_target_sec:.1f}s "
                        f"if high audience retention is the primary objective."
                    ),
                )
            )

        return True

    def _validate_narrative_coherence(self, story: StoryArc, findings: List[StoryQAFinding]) -> bool:
        """Validate dramatic structure, required entities, and forbidden pitfalls."""
        has_error = False

        if not story.scenes:
            findings.append(
                StoryQAFinding(
                    rule="narrative_scenes_empty",
                    severity="ERROR",
                    message="StoryArc contains zero scenes.",
                    remediation="Generate at least 4 scenes conforming to the story arc.",
                )
            )
            return False

        # 1. Opening hook check
        first_scene = story.scenes[0]
        if first_scene.narrative_role != NarrativeRole.HOOK:
            findings.append(
                StoryQAFinding(
                    rule="narrative_opening_hook",
                    severity="ERROR",
                    scene_id=first_scene.id,
                    message=f"Story starts with role '{first_scene.narrative_role.value}' instead of mandatory 'hook'.",
                    remediation="Configure the opening scene with NarrativeRole.HOOK.",
                )
            )
            has_error = True

        # 2. Resolution payoff check
        has_resolution = any(
            s.narrative_role in (NarrativeRole.PAYOFF, NarrativeRole.LOOP, NarrativeRole.CTA)
            for s in story.scenes
        )
        if not has_resolution:
            findings.append(
                StoryQAFinding(
                    rule="narrative_resolution_role",
                    severity="ERROR",
                    message="Story lacks a resolution scene (PAYOFF, LOOP, or CTA) satisfying the narrative contract.",
                    remediation="Ensure terminal scene delivers payoff or loop matching the contract ending strategy.",
                )
            )
            has_error = True

        # 3. Required entities check
        full_text_lower = " ".join(s.script_text.lower() for s in story.scenes)
        for entity in story.contract.must_include_entities:
            if entity.lower() not in full_text_lower:
                findings.append(
                    StoryQAFinding(
                        rule="narrative_missing_entity",
                        severity="ERROR",
                        message=f"Required entity '{entity}' is absent from the story narration.",
                        remediation=f"Include entity '{entity}' in the appropriate scene script.",
                    )
                )
                has_error = True

        # 4. Prohibited pitfalls check
        for scene in story.scenes:
            scene_text_lower = scene.script_text.lower()
            for pitfall in story.contract.must_avoid_pitfalls:
                if pitfall.lower() in scene_text_lower:
                    findings.append(
                        StoryQAFinding(
                            rule="narrative_prohibited_pitfall",
                            severity="ERROR",
                            scene_id=scene.id,
                            message=f"Scene '{scene.id}' contains prohibited pitfall phrase: '{pitfall}'.",
                            remediation="Rephrase scene narration to remove or reframe the prohibited phrasing.",
                        )
                    )
                    has_error = True

        return not has_error

    def _validate_scene_dependencies(self, story: StoryArc, findings: List[StoryQAFinding]) -> bool:
        """Validate that all scene dependencies reference strictly preceding scenes."""
        has_error = False
        seen_scene_ids: Set[str] = set()

        for idx, scene in enumerate(story.scenes):
            for dep_id in scene.dependencies:
                if dep_id == scene.id:
                    findings.append(
                        StoryQAFinding(
                            rule="scene_dependency_self_reference",
                            severity="ERROR",
                            scene_id=scene.id,
                            message=f"Scene '{scene.id}' lists itself as a dependency.",
                            remediation="Remove self from scene dependencies.",
                        )
                    )
                    has_error = True
                elif dep_id not in seen_scene_ids:
                    # Check if it exists downstream in the story (forward reference)
                    future_ids = {s.id for s in story.scenes[idx + 1 :]}
                    if dep_id in future_ids:
                        findings.append(
                            StoryQAFinding(
                                rule="scene_dependency_forward_reference",
                                severity="ERROR",
                                scene_id=scene.id,
                                message=f"Scene '{scene.id}' has a forward dependency on '{dep_id}'.",
                                remediation="Dependencies must only reference strictly preceding scenes.",
                            )
                        )
                    else:
                        findings.append(
                            StoryQAFinding(
                                rule="scene_dependency_nonexistent",
                                severity="ERROR",
                                scene_id=scene.id,
                                message=f"Scene '{scene.id}' references nonexistent dependency '{dep_id}'.",
                                remediation=f"Fix dependency '{dep_id}' to a valid preceding scene ID.",
                            )
                        )
                    has_error = True

            seen_scene_ids.add(scene.id)

        return not has_error

    def _validate_claim_integrity(self, story: StoryArc, findings: List[StoryQAFinding]) -> bool:
        """Validate factual claim structural integrity.

        Rejects CONTRADICTED claims.
        Requires explicit scope and wording_constraints for CONTEXT_REQUIRED claims.
        Emits warnings for UNCERTAIN or NEEDS_SOURCE claims.
        """
        has_error = False

        for scene in story.scenes:
            for claim in scene.factual_claims:
                # 1. Contradicted claims are strict blockers
                if claim.status == ClaimStatus.CONTRADICTED:
                    findings.append(
                        StoryQAFinding(
                            rule="claim_integrity_contradicted",
                            severity="ERROR",
                            scene_id=scene.id,
                            message=f"Factual claim '{claim.claim_text}' is marked CONTRADICTED.",
                            remediation="Remove or replace contradicted assertion with verified historical/technical data.",
                        )
                    )
                    has_error = True

                # 2. Context required claims must specify scope and wording constraints
                elif claim.status == ClaimStatus.CONTEXT_REQUIRED:
                    if not claim.scope or not claim.wording_constraints:
                        findings.append(
                            StoryQAFinding(
                                rule="claim_integrity_missing_context",
                                severity="ERROR",
                                scene_id=scene.id,
                                message=(
                                    f"Claim '{claim.claim_text}' has status CONTEXT_REQUIRED but lacks "
                                    f"explicit 'scope' or 'wording_constraints'."
                                ),
                                remediation=(
                                    "Define bounding scope and phrasing constraints to prevent misleading assertions."
                                ),
                            )
                        )
                        has_error = True

                # 3. Uncertain or unverified claims generate actionable warnings
                elif claim.status in (ClaimStatus.UNCERTAIN, ClaimStatus.NEEDS_SOURCE):
                    findings.append(
                        StoryQAFinding(
                            rule="claim_integrity_verification_needed",
                            severity="WARNING",
                            scene_id=scene.id,
                            message=(
                                f"Claim '{claim.claim_text}' has status '{claim.status.value}' and has not "
                                f"been independently verified with an authoritative source reference."
                            ),
                            remediation="Provide verified source reference or confirm claim before publishing.",
                        )
                    )

        return not has_error

    def _validate_visual_briefs(self, story: StoryArc, findings: List[StoryQAFinding]) -> bool:
        """Validate presence of visual briefs and prohibited mismatches."""
        has_error = False

        for scene in story.scenes:
            if scene.visual_brief is None:
                findings.append(
                    StoryQAFinding(
                        rule="visual_brief_missing",
                        severity="ERROR",
                        scene_id=scene.id,
                        message=f"Scene '{scene.id}' is missing a decoupled VisualBrief.",
                        remediation="Attach a VisualBrief detailing subject, era, environment, action, and prohibited_mismatches.",
                    )
                )
                has_error = True
            else:
                brief = scene.visual_brief
                if not brief.prohibited_mismatches:
                    findings.append(
                        StoryQAFinding(
                            rule="visual_brief_no_prohibited_mismatches",
                            severity="WARNING",
                            scene_id=scene.id,
                            message=f"VisualBrief for scene '{scene.id}' has no prohibited_mismatches defined.",
                            remediation="Add explicit prohibited_mismatches to guide asset matching and discard anachronisms.",
                        )
                    )

        return not has_error

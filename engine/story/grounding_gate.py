"""Claim Grounding Gate (Stage 12C.2).

Deterministic security and verification boundary between LLM narrative synthesis
and the Stage 12B production pipeline.

Enforces:
1. Rejection of ungrounded factual assertions (orphan claims).
2. Rejection of fabricated claim IDs not present in FactDossier.
3. Rejection of contradicted claim assertions.
4. Strict enforcement of prohibited wording bounds.
5. Detection and rejection of overclaiming and uncalibrated absolute superlatives.
6. Surgical scene regeneration preserving unmodified approved scenes.
7. Clean contractual conversion of approved drafts to Stage 12B StoryArc.
"""

from typing import Any, Dict, List, Optional
from engine.story.llm_provider import LLMProvider
from engine.story.schema import (
    ClaimStatus,
    FactClaim,
    FactDossier,
    GroundingFinding,
    GroundingReport,
    NarrativeRole,
    Scene,
    SceneDraft,
    StatementType,
    StoryArc,
    StoryContract,
    StoryDraft,
    VisualBrief,
)


class ClaimGroundingGate:
    """Evaluates narrative assertions against the immutable FactDossier."""

    # Absolute superlatives that trigger overclaiming checks when evidence is qualified
    ABSOLUTE_SUPERLATIVES = [
        "el primer ",
        "el primero de la historia",
        "la primera persona",
        "el primer viaje de larga distancia de la historia",
        "primer viaje de larga distancia de la historia",
        "the first ever",
        "el único",
        "el unico",
        "la única",
        "la unica",
        "el mas rapido de todos",
        "el más rápido de todos",
        "todos los",
        "primer ser humano",
        "primera persona de la historia",
        "inventó por completo",
        "invento por completo",
        "revolucionó para siempre",
        "revoluciono para siempre",
    ]

    NUANCED_INDICATORS = [
        "uno de los primeros",
        "one of the first",
        "aproximadamente",
        "considerado",
        "posiblemente",
        "atribuido",
        "entre los pioneros",
    ]

    def evaluate_draft(self, draft: StoryDraft, dossier: FactDossier) -> GroundingReport:
        """Audit a complete StoryDraft against the authoritative FactDossier."""
        findings: List[GroundingFinding] = []
        scene_status: Dict[str, bool] = {s.scene_id: True for s in draft.scenes}

        # 1. Dossier Cryptographic Integrity Check
        if draft.dossier_sha256 != dossier.dossier_sha256:
            findings.append(
                GroundingFinding(
                    rule="DOSSIER_HASH_MISMATCH",
                    severity="ERROR",
                    scene_id="global",
                    assertion_text="",
                    claim_id=None,
                    message=(
                        f"Draft references dossier hash '{draft.dossier_sha256[:12]}...', "
                        f"but canonical FactDossier hash is '{dossier.dossier_sha256[:12]}...'."
                    ),
                    remediation="Regenerate story draft using the exact current FactDossier revision.",
                )
            )

        if draft.dossier_id != dossier.dossier_id:
            findings.append(
                GroundingFinding(
                    rule="DOSSIER_ID_MISMATCH",
                    severity="ERROR",
                    scene_id="global",
                    assertion_text="",
                    claim_id=None,
                    message=(
                        f"Draft references dossier ID '{draft.dossier_id}', "
                        f"but expected dossier ID is '{dossier.dossier_id}'."
                    ),
                    remediation="Align draft dossier ID with authoritative FactDossier.",
                )
            )

        # Metrics counters
        total_assertions = 0
        factual_assertions = 0
        grounded_assertions = 0
        orphan_assertions = 0
        fabricated_claim_ids = 0
        overclaiming_assertions = 0

        # 2. Scene-by-Scene Assertion Inspection
        for scene in draft.scenes:
            for assertion in scene.assertions:
                total_assertions += 1
                stype = assertion.statement_type
                text_lower = assertion.text.lower()

                if stype == StatementType.FACTUAL:
                    factual_assertions += 1
                    assertion_has_error = False

                    # Check for orphan factual assertions
                    if not assertion.claim_ids:
                        orphan_assertions += 1
                        assertion_has_error = True
                        scene_status[scene.scene_id] = False
                        findings.append(
                            GroundingFinding(
                                rule="UNGROUNDED_FACTUAL_ASSERTION",
                                severity="ERROR",
                                scene_id=scene.scene_id,
                                assertion_text=assertion.text,
                                claim_id=None,
                                message="Factual assertion lacks backing claim_ids from FactDossier.",
                                remediation=(
                                    "Assign valid claim_ids from FactDossier or reclassify statement "
                                    "as NARRATIVE or INTERPRETIVE."
                                ),
                            )
                        )
                    else:
                        for cid in assertion.claim_ids:
                            if cid not in dossier.claims:
                                fabricated_claim_ids += 1
                                assertion_has_error = True
                                scene_status[scene.scene_id] = False
                                findings.append(
                                    GroundingFinding(
                                        rule="FABRICATED_CLAIM_ID",
                                        severity="ERROR",
                                        scene_id=scene.scene_id,
                                        assertion_text=assertion.text,
                                        claim_id=cid,
                                        message=f"Claim ID '{cid}' does not exist in FactDossier '{dossier.dossier_id}'.",
                                        remediation="Reference only valid claim IDs present in the FactDossier.",
                                    )
                                )
                            else:
                                claim = dossier.claims[cid]

                                # Contradicted claim rejection
                                if claim.status == ClaimStatus.CONTRADICTED:
                                    assertion_has_error = True
                                    scene_status[scene.scene_id] = False
                                    findings.append(
                                        GroundingFinding(
                                            rule="CONTRADICTED_CLAIM_USAGE",
                                            severity="ERROR",
                                            scene_id=scene.scene_id,
                                            assertion_text=assertion.text,
                                            claim_id=cid,
                                            message=f"Assertion references contradicted claim '{cid}'.",
                                            remediation="Do not assert contradicted claims as factual truth in narration.",
                                        )
                                    )

                                # Unverified / Uncertain claim rejection
                                elif claim.status in (ClaimStatus.NEEDS_SOURCE, ClaimStatus.UNCERTAIN, ClaimStatus.OPINION_OR_RHETORIC):
                                    assertion_has_error = True
                                    scene_status[scene.scene_id] = False
                                    findings.append(
                                        GroundingFinding(
                                            rule="UNVERIFIED_CLAIM_USAGE",
                                            severity="ERROR",
                                            scene_id=scene.scene_id,
                                            assertion_text=assertion.text,
                                            claim_id=cid,
                                            message=(
                                                f"Assertion references claim '{cid}' with unverified status '{claim.status.value}'. "
                                                "Claims requiring sources, uncertain claims, or opinions cannot back certified factual assertions."
                                            ),
                                            remediation="Only claims with status VERIFIED or CONTEXT_REQUIRED may back factual assertions.",
                                        )
                                    )

                                # Prohibited wording & legacy wording constraints check
                                all_prohibited = list(claim.prohibited_wording) + [
                                    wc for wc in getattr(claim, "wording_constraints", []) if wc not in claim.prohibited_wording
                                ]
                                for pw in all_prohibited:
                                    if pw.lower() in text_lower:
                                        assertion_has_error = True
                                        scene_status[scene.scene_id] = False
                                        findings.append(
                                            GroundingFinding(
                                                rule="PROHIBITED_WORDING_VIOLATION",
                                                severity="ERROR",
                                                scene_id=scene.scene_id,
                                                assertion_text=assertion.text,
                                                claim_id=cid,
                                                message=f"Assertion contains prohibited wording '{pw}' from claim '{cid}'.",
                                                remediation=f"Rewrite statement avoiding prohibited phrase '{pw}'.",
                                            )
                                        )

                                # Overclaiming / superlative detection
                                claim_source_text = f"{claim.supporting_excerpt or ''} {claim.claim_text or ''}".lower()
                                has_nuance = any(n in claim_source_text for n in self.NUANCED_INDICATORS)

                                is_superlative = any(s in text_lower for s in self.ABSOLUTE_SUPERLATIVES)

                                if has_nuance and is_superlative:
                                    allowed = False
                                    if claim.allowed_wording:
                                        allowed = any(s in claim.allowed_wording.lower() for s in self.ABSOLUTE_SUPERLATIVES)

                                    if not allowed:
                                        overclaiming_assertions += 1
                                        assertion_has_error = True
                                        scene_status[scene.scene_id] = False
                                        findings.append(
                                            GroundingFinding(
                                                rule="OVERCLAIMING_VIOLATION",
                                                severity="ERROR",
                                                scene_id=scene.scene_id,
                                                assertion_text=assertion.text,
                                                claim_id=cid,
                                                message=(
                                                    "Overclaiming detected: Source excerpt indicates qualified phrasing, "
                                                    f"but assertion '{assertion.text}' asserts an absolute superlative."
                                                ),
                                                remediation="Qualify the statement to match the nuanced historical evidence.",
                                            )
                                        )

                    if not assertion_has_error:
                        grounded_assertions += 1

                elif stype == StatementType.INTERPRETIVE:
                    # Interpretive assertions: check that any provided claim_ids exist and respect prohibited wording
                    if assertion.claim_ids:
                        for cid in assertion.claim_ids:
                            if cid not in dossier.claims:
                                fabricated_claim_ids += 1
                                scene_status[scene.scene_id] = False
                                findings.append(
                                    GroundingFinding(
                                        rule="FABRICATED_CLAIM_ID",
                                        severity="ERROR",
                                        scene_id=scene.scene_id,
                                        assertion_text=assertion.text,
                                        claim_id=cid,
                                        message=f"Claim ID '{cid}' does not exist in FactDossier.",
                                        remediation="Reference only valid claim IDs in interpretive assertions.",
                                    )
                                )
                            else:
                                claim = dossier.claims[cid]
                                all_prohibited = list(claim.prohibited_wording) + [
                                    wc for wc in getattr(claim, "wording_constraints", []) if wc not in claim.prohibited_wording
                                ]
                                for pw in all_prohibited:
                                    if pw.lower() in text_lower:
                                        scene_status[scene.scene_id] = False
                                        findings.append(
                                            GroundingFinding(
                                                rule="PROHIBITED_WORDING_VIOLATION",
                                                severity="ERROR",
                                                scene_id=scene.scene_id,
                                                assertion_text=assertion.text,
                                                claim_id=cid,
                                                message=f"Interpretive statement contains prohibited wording '{pw}'.",
                                                remediation=f"Rewrite avoiding '{pw}'.",
                                            )
                                        )
                    else:
                        # Ungrounded interpretive: check against factual masquerade (absolute superlatives)
                        if any(s in text_lower for s in self.ABSOLUTE_SUPERLATIVES):
                            scene_status[scene.scene_id] = False
                            findings.append(
                                GroundingFinding(
                                    rule="FACTUAL_MASQUERADE_VIOLATION",
                                    severity="ERROR",
                                    scene_id=scene.scene_id,
                                    assertion_text=assertion.text,
                                    claim_id=None,
                                    message=(
                                        f"Statement classified as 'interpretive' asserts an ungrounded absolute superlative "
                                        f"('{assertion.text}'). Historical primacy or exclusivity claims require FACTUAL grounding."
                                    ),
                                    remediation="Reclassify as FACTUAL and ground with a valid claim_id, or rephrase interpretively.",
                                )
                            )

                else:
                    # NARRATIVE and TRANSITION: creative prose, but CANNOT masquerade ungrounded factual superlatives
                    if not assertion.claim_ids:
                        if any(s in text_lower for s in self.ABSOLUTE_SUPERLATIVES):
                            scene_status[scene.scene_id] = False
                            findings.append(
                                GroundingFinding(
                                    rule="FACTUAL_MASQUERADE_VIOLATION",
                                    severity="ERROR",
                                    scene_id=scene.scene_id,
                                    assertion_text=assertion.text,
                                    claim_id=None,
                                    message=(
                                        f"Statement classified as '{stype.value}' asserts an ungrounded absolute superlative "
                                        f"or primacy claim ('{assertion.text}'). It cannot bypass factual grounding."
                                    ),
                                    remediation=(
                                        "Reclassify as FACTUAL and ground with a valid claim_id from FactDossier, "
                                        "or rephrase without ungrounded factual superlatives."
                                    ),
                                )
                            )
                    else:
                        # If claim_ids are supplied, verify they exist
                        for cid in assertion.claim_ids:
                            if cid not in dossier.claims:
                                fabricated_claim_ids += 1
                                scene_status[scene.scene_id] = False
                                findings.append(
                                    GroundingFinding(
                                        rule="FABRICATED_CLAIM_ID",
                                        severity="ERROR",
                                        scene_id=scene.scene_id,
                                        assertion_text=assertion.text,
                                        claim_id=cid,
                                        message=f"Claim ID '{cid}' does not exist in FactDossier.",
                                        remediation="Remove or correct invalid claim ID.",
                                    )
                                )

        has_errors = any(f.severity == "ERROR" for f in findings)
        return GroundingReport(
            passed=not has_errors,
            total_assertions=total_assertions,
            factual_assertions=factual_assertions,
            grounded_assertions=grounded_assertions,
            orphan_assertions=orphan_assertions,
            fabricated_claim_ids=fabricated_claim_ids,
            overclaiming_assertions=overclaiming_assertions,
            findings=findings,
            scene_status=scene_status,
        )

    def surgical_regenerate_scene(
        self,
        draft: StoryDraft,
        scene_id: str,
        dossier: FactDossier,
        provider: LLMProvider,
        remediation_hint: str,
    ) -> StoryDraft:
        """Regenerate exclusively the failing scene, keeping all approved scenes strictly identical."""
        target_idx = next((i for i, s in enumerate(draft.scenes) if s.scene_id == scene_id), None)
        if target_idx is None:
            raise ValueError(f"Scene '{scene_id}' not found in StoryDraft.")

        original_scene = draft.scenes[target_idx]

        # Compose surgical prompt
        claims_summary = "\n".join(
            f"- [{cid}] {c.claim_text} (Status: {c.status.value})"
            for cid, c in dossier.claims.items()
        )
        prompt = (
            f"You are a narrative architect. Re-author ONLY scene '{scene_id}' (index {target_idx}).\n"
            f"Role: {original_scene.narrative_role.value}\n"
            f"Previous Narration: \"{original_scene.narration}\"\n"
            f"Grounding Failure / Remediation Hint: {remediation_hint}\n\n"
            f"Available FactClaims from FactDossier '{dossier.dossier_id}':\n{claims_summary}\n\n"
            f"Generate a corrected SceneDraft conforming strictly to schema."
        )

        new_scene = provider.generate_structured(prompt, SceneDraft)
        new_scene.scene_id = scene_id
        new_scene.scene_index = target_idx

        # Replace exclusively the target scene
        updated_scenes = list(draft.scenes)
        updated_scenes[target_idx] = new_scene

        return draft.model_copy(update={"scenes": updated_scenes})

    def convert_draft_to_story_arc(self, draft: StoryDraft, dossier: FactDossier) -> StoryArc:
        """Convert a grounded, gate-approved StoryDraft into a Stage 12B StoryArc."""
        report = self.evaluate_draft(draft, dossier)
        if not report.passed:
            err_msgs = [f"{f.rule}: {f.message}" for f in report.findings if f.severity == "ERROR"]
            raise ValueError(f"Cannot convert ungrounded StoryDraft to StoryArc. Failures: {err_msgs}")

        converted_scenes: List[Scene] = []
        for s_draft in draft.scenes:
            # Deduplicate and attach authentic FactClaim instances from dossier
            scene_claim_ids = []
            for ast in s_draft.assertions:
                for cid in ast.claim_ids:
                    if cid in dossier.claims and cid not in scene_claim_ids:
                        scene_claim_ids.append(cid)

            real_claims = [dossier.claims[cid] for cid in scene_claim_ids]

            words = s_draft.narration.split()
            word_count = len(words)
            # Duration heuristic: ~2.3 words/sec (matches 12B planning heuristic)
            est_duration = max(3.0, round(word_count / 2.3, 2))

            v_brief = s_draft.visual_intent
            if v_brief is None:
                v_brief = VisualBrief(
                    subject=draft.topic,
                    era="historical",
                    environment="dramatic setting",
                    action="narration visualization",
                    mood="informative",
                )

            scene = Scene(
                id=s_draft.scene_id,
                scene_index=s_draft.scene_index,
                narrative_role=s_draft.narrative_role,
                dependencies=s_draft.dependencies,
                script_text=s_draft.narration,
                word_count=word_count,
                estimated_duration_sec=est_duration,
                visual_brief=v_brief,
                factual_claims=real_claims,
                scene_qa_passed=True,
                scene_qa_failures=[],
            )
            converted_scenes.append(scene)

        total_est_dur = round(sum(s.estimated_duration_sec for s in converted_scenes), 2)

        contract = StoryContract(
            id=f"contract_{draft.dossier_id}",
            title=draft.title,
            topic=draft.topic,
            core_question=draft.core_question,
            narrative_promise=draft.narrative_promise,
            target_audience=draft.target_audience,
            tone=draft.tone,
            must_include_entities=list(dossier.key_entities),
            must_avoid_pitfalls=[],
            ending_strategy=draft.ending_strategy,
        )

        return StoryArc(
            id=f"arc_{draft.dossier_id}",
            contract=contract,
            scenes=converted_scenes,
            target_duration_sec=total_est_dur,
            total_estimated_duration_sec=total_est_dur,
            status="grounded_draft",
        )

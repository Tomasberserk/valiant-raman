"""Fact Intelligence Engine (Stage 12C.1).

Provides the factual foundation for the Creative Production Engine:
1. Contextual Source Authority Evaluation.
2. Independence Grouping for genuine corroboration.
3. Overclaiming & Wording Boundaries Enforcement.
4. Strict Canonicalization Algorithm for deterministic dossier_sha256.
5. Immutable, versioned FactDossier management (v1 -> v2 revisions).
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple
import unicodedata
from pydantic import BaseModel, Field

from engine.story.schema import (
    ClaimStatus,
    EvidenceSnapshot,
    FactClaim,
    FactDossier,
    FactSource,
    SourceAuthority,
)


class ClaimVerificationResult(BaseModel):
    """Evaluation result for an atomic FactClaim against source catalog."""
    claim_id: Optional[str] = None
    passed: bool
    status: ClaimStatus
    independent_sources_count: int = 0
    has_contradiction: bool = False
    overclaiming_detected: bool = False
    findings: List[str] = Field(default_factory=list)
    remediation: Optional[str] = None


class FactIntelligenceEngine:
    """Core verification, canonicalization and dossier management engine."""

    # -------------------------------------------------------------------------
    # Canonicalization & Hashing
    # -------------------------------------------------------------------------

    @staticmethod
    def canonicalize_value(val: Any) -> Any:
        """Recursively canonicalize data structures for deterministic hashing."""
        if isinstance(val, dict):
            return {
                unicodedata.normalize("NFC", str(k)): FactIntelligenceEngine.canonicalize_value(v)
                for k, v in sorted(val.items(), key=lambda item: str(item[0]))
            }
        elif isinstance(val, list):
            # Canonicalize elements while preserving sequential order
            return [FactIntelligenceEngine.canonicalize_value(x) for x in val]
        elif isinstance(val, datetime):
            # ISO 8601 UTC representation: YYYY-MM-DDTHH:MM:SSZ
            utc_dt = val.astimezone(timezone.utc)
            return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(val, Enum):
            return val.value
        elif isinstance(val, BaseModel):
            return FactIntelligenceEngine.canonicalize_value(val.model_dump())
        elif isinstance(val, str):
            return unicodedata.normalize("NFC", val)
        elif isinstance(val, (int, float, bool)) or val is None:
            return val
        else:
            return unicodedata.normalize("NFC", str(val))

    @classmethod
    def compute_dossier_hash(cls, dossier_data: Dict[str, Any]) -> str:
        """Compute strict deterministic SHA-256 hash from dossier dictionary."""
        # Strip transient / computed fields
        payload = {k: v for k, v in dossier_data.items() if k not in ("dossier_sha256", "frozen")}
        canonical = cls.canonicalize_value(payload)
        canonical_json = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    # -------------------------------------------------------------------------
    # Claim Verification
    # -------------------------------------------------------------------------

    def verify_claim(
        self,
        claim: FactClaim,
        sources: Dict[str, FactSource],
        existing_claims: Optional[Dict[str, FactClaim]] = None,
    ) -> ClaimVerificationResult:
        """Evaluate factual grounding, corroboration, scope, and wording constraints."""
        findings: List[str] = []
        has_contradiction = False
        overclaiming = False

        # 1. Source existence check
        if not claim.source_ids:
            findings.append("Claim has no supporting sources assigned.")
            return ClaimVerificationResult(
                claim_id=claim.claim_id,
                passed=False,
                status=ClaimStatus.NEEDS_SOURCE,
                findings=findings,
                remediation="Attach at least one authoritative FactSource.",
            )

        supporting_sources: List[FactSource] = []
        for sid in claim.source_ids:
            if sid in sources:
                supporting_sources.append(sources[sid])
            else:
                findings.append(f"Referenced source_id '{sid}' not found in source catalog.")

        if not supporting_sources:
            findings.append("None of the referenced source_ids exist in the catalog.")
            return ClaimVerificationResult(
                claim_id=claim.claim_id,
                passed=False,
                status=ClaimStatus.NEEDS_SOURCE,
                findings=findings,
                remediation="Ensure referenced sources exist in FactDossier.",
            )

        # 2. Unverified source check
        if all(s.authority_level == SourceAuthority.UNVERIFIED for s in supporting_sources):
            findings.append("Claim is supported exclusively by UNVERIFIED sources.")
            return ClaimVerificationResult(
                claim_id=claim.claim_id,
                passed=False,
                status=ClaimStatus.UNCERTAIN,
                findings=findings,
                remediation="Corroborate with reputable or institutional sources.",
            )

        # 3. Independent Corroboration via independence_group
        independence_groups: Set[str] = set()
        for s in supporting_sources:
            # If independence_group is set, use it; otherwise fallback to unique source_id
            group = s.independence_group or s.source_id
            independence_groups.add(group)
        independent_count = len(independence_groups)

        # Evaluate Contextual Authority:
        # A) Primary Institutional source is sufficient by itself for domain-specific claims
        has_primary = any(s.authority_level == SourceAuthority.PRIMARY_INSTITUTIONAL for s in supporting_sources)
        # B) Secondary academic or reputable journalism requires at least 2 independent groups
        has_corroborated_secondary = (
            independent_count >= 2
            and any(
                s.authority_level in (SourceAuthority.SECONDARY_ACADEMIC, SourceAuthority.REPUTABLE_JOURNALISM)
                for s in supporting_sources
            )
        )

        sufficient_authority = has_primary or has_corroborated_secondary

        if not sufficient_authority:
            if independent_count < 2 and not has_primary:
                findings.append(
                    f"Claim lacks sufficient corroboration: found {independent_count} independent source group(s). "
                    "Requires 1 primary or >=2 independent secondary sources."
                )

        # 4. Contradiction Detection
        if claim.status == ClaimStatus.CONTRADICTED:
            has_contradiction = True
            findings.append("Claim is explicitly flagged as CONTRADICTED.")

        if existing_claims:
            for ec_id, ec in existing_claims.items():
                if ec.claim_id != claim.claim_id:
                    # Check for direct contradictions on matching entity/topic
                    if (
                        ec.entity
                        and claim.entity
                        and ec.entity.lower() == claim.entity.lower()
                        and ec.status == ClaimStatus.VERIFIED
                        and ec.status != claim.status
                        and claim.status == ClaimStatus.CONTRADICTED
                    ):
                        has_contradiction = True
                        findings.append(f"Contradicts verified claim '{ec_id}'.")

        # 5. Scope Requirement for CONTEXT_REQUIRED
        if claim.status == ClaimStatus.CONTEXT_REQUIRED:
            if not claim.scope or not claim.scope.strip():
                findings.append("Claims with status CONTEXT_REQUIRED strictly require an explicit 'scope'.")

        # 6. Overclaiming & Wording Constraints Enforcement
        # Rule: prohibited_wording must not appear in claim_text
        text_lower = claim.claim_text.lower()
        for pw in claim.prohibited_wording:
            if pw.lower() in text_lower:
                overclaiming = True
                findings.append(f"Overclaiming detected: prohibited phrase '{pw}' found in claim text.")

        # Excerpt-based overclaiming check:
        # If supporting excerpt contains nuanced/mitigating phrasing and claim_text makes an absolute superlative
        if claim.supporting_excerpt:
            exc_lower = claim.supporting_excerpt.lower()
            if any(term in exc_lower for term in ["uno de los primeros", "one of the first", "aproximadamente", "considerado"]):
                if any(superlative in text_lower for superlative in ["el primer ", "el primero de la historia", "the first ever", "el único"]):
                    # Unless explicitly allowed by allowed_wording
                    if not claim.allowed_wording or "el primer" not in claim.allowed_wording.lower():
                        overclaiming = True
                        findings.append(
                            "Overclaiming detected: Source excerpt indicates qualified phrasing "
                            f"('{claim.supporting_excerpt[:50]}...'), but claim text asserts an absolute superlative."
                        )

        # Determine final status and pass/fail
        if has_contradiction:
            final_status = ClaimStatus.CONTRADICTED
            passed = False
        elif overclaiming:
            final_status = ClaimStatus.CONTEXT_REQUIRED
            passed = False
        elif not sufficient_authority:
            final_status = ClaimStatus.NEEDS_SOURCE
            passed = False
        elif claim.status == ClaimStatus.CONTEXT_REQUIRED and (not claim.scope or not claim.scope.strip()):
            final_status = ClaimStatus.CONTEXT_REQUIRED
            passed = False
        else:
            final_status = ClaimStatus.VERIFIED if claim.status in (ClaimStatus.VERIFIED, ClaimStatus.NEEDS_SOURCE) else claim.status
            passed = True

        remediation = "Fix findings and update claim text or source citations." if not passed else None

        return ClaimVerificationResult(
            claim_id=claim.claim_id,
            passed=passed,
            status=final_status,
            independent_sources_count=independent_count,
            has_contradiction=has_contradiction,
            overclaiming_detected=overclaiming,
            findings=findings,
            remediation=remediation,
        )

    # -------------------------------------------------------------------------
    # Dossier Compilation & Revisions
    # -------------------------------------------------------------------------

    def compile_dossier(
        self,
        topic: str,
        run_id: str,
        sources: List[FactSource],
        claims: List[FactClaim],
        snapshots: Optional[List[EvidenceSnapshot]] = None,
        timeline_milestones: Optional[List[str]] = None,
        key_entities: Optional[List[str]] = None,
        dossier_id: Optional[str] = None,
        version: int = 1,
    ) -> FactDossier:
        """Compile verified sources and claims into an immutable, versioned FactDossier."""
        d_id = dossier_id or f"dossier_{run_id}_v{version}"
        sources_dict = {s.source_id: s for s in sources}
        snapshots_dict = {sn.snapshot_id: sn for sn in (snapshots or [])}
        claims_dict = {c.claim_id or f"claim_{i+1:03d}": c for i, c in enumerate(claims)}

        # Populate claim_id if missing
        for cid, claim in claims_dict.items():
            if not claim.claim_id:
                claim.claim_id = cid

        raw_dict = {
            "dossier_id": d_id,
            "run_id": run_id,
            "version": version,
            "topic": topic,
            "created_at": datetime.now(timezone.utc),
            "sources": sources_dict,
            "snapshots": snapshots_dict,
            "claims": claims_dict,
            "timeline_milestones": timeline_milestones or [],
            "key_entities": key_entities or [],
        }

        # Compute canonical hash
        sha256_hash = self.compute_dossier_hash(raw_dict)

        dossier = FactDossier(
            dossier_id=d_id,
            run_id=run_id,
            version=version,
            topic=topic,
            created_at=raw_dict["created_at"],
            sources=sources_dict,
            snapshots=snapshots_dict,
            claims=claims_dict,
            timeline_milestones=timeline_milestones or [],
            key_entities=key_entities or [],
            dossier_sha256=sha256_hash,
            frozen=True,  # Lock dossier
        )

        return dossier

    def create_revision(
        self,
        base_dossier: FactDossier,
        added_sources: Optional[List[FactSource]] = None,
        added_claims: Optional[List[FactClaim]] = None,
        updated_claims: Optional[List[FactClaim]] = None,
        added_snapshots: Optional[List[EvidenceSnapshot]] = None,
    ) -> FactDossier:
        """Produce an incremental revision (v2, v3...) without mutating the base dossier."""
        new_version = base_dossier.version + 1
        new_dossier_id = f"{base_dossier.dossier_id.rsplit('_v', 1)[0]}_v{new_version}"

        # Deep copies of collections
        sources_dict = dict(base_dossier.sources)
        if added_sources:
            for s in added_sources:
                sources_dict[s.source_id] = s

        snapshots_dict = dict(base_dossier.snapshots)
        if added_snapshots:
            for sn in added_snapshots:
                snapshots_dict[sn.snapshot_id] = sn

        claims_dict = dict(base_dossier.claims)
        if added_claims:
            for c in added_claims:
                cid = c.claim_id or f"claim_rev_{len(claims_dict)+1:03d}"
                c.claim_id = cid
                claims_dict[cid] = c

        if updated_claims:
            for uc in updated_claims:
                if uc.claim_id:
                    claims_dict[uc.claim_id] = uc

        raw_dict = {
            "dossier_id": new_dossier_id,
            "run_id": base_dossier.run_id,
            "version": new_version,
            "topic": base_dossier.topic,
            "created_at": datetime.now(timezone.utc),
            "sources": sources_dict,
            "snapshots": snapshots_dict,
            "claims": claims_dict,
            "timeline_milestones": list(base_dossier.timeline_milestones),
            "key_entities": list(base_dossier.key_entities),
        }

        sha256_hash = self.compute_dossier_hash(raw_dict)

        new_dossier = FactDossier(
            dossier_id=new_dossier_id,
            run_id=base_dossier.run_id,
            version=new_version,
            topic=base_dossier.topic,
            created_at=raw_dict["created_at"],
            sources=sources_dict,
            snapshots=snapshots_dict,
            claims=claims_dict,
            timeline_milestones=list(base_dossier.timeline_milestones),
            key_entities=list(base_dossier.key_entities),
            dossier_sha256=sha256_hash,
            frozen=True,
        )

        return new_dossier

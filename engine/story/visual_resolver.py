"""Visual Resolver & Asset Ladder (Stage 12B.2).

Responsible for:
1. Managing local curated catalogs (AssetCatalog) with provenance and licensing.
2. Deterministic metadata matching (zero LLM / zero external dependencies).
3. Strict priority execution of prohibited_mismatches filter before scoring.
4. Asset Ladder traversal:
   - Tier 1: Exact Match (passthrough)
   - Tier 2: Thematic B-Roll (passthrough)
   - Tier 3: Kinetic Motion (ken_burns strategy on still image)
   - Tier 4: Decision for Styled Cinematic Fallback (styled_cinematic, asset_path=None)
5. Comprehensive audit trail of decisions, scores, and candidate rejection reasons.
"""

import json
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

from engine.story.schema import (
    ResolutionTier,
    Scene,
    StoryArc,
    VisualAssetMetadata,
    VisualBrief,
    VisualProductionStrategy,
    VisualResolutionResult,
)


class AssetCatalog:
    """In-memory index of available visual assets with provenance and metadata."""

    def __init__(self):
        self._assets: Dict[str, VisualAssetMetadata] = {}

    def add_asset(self, asset: VisualAssetMetadata) -> None:
        """Register an asset metadata record."""
        self._assets[asset.asset_id] = asset

    def get_asset(self, asset_id: str) -> Optional[VisualAssetMetadata]:
        """Retrieve asset metadata by ID."""
        return self._assets.get(asset_id)

    def list_assets(self) -> List[VisualAssetMetadata]:
        """Return all registered assets sorted deterministically by asset_id."""
        return sorted(self._assets.values(), key=lambda a: a.asset_id)

    def load_from_dict_list(self, data: List[dict]) -> None:
        """Load multiple asset records from a list of dicts."""
        for item in data:
            self.add_asset(VisualAssetMetadata(**item))

    def load_from_json(self, json_path: Path) -> None:
        """Load catalog from a JSON manifest file."""
        if not json_path.exists():
            raise FileNotFoundError(f"Catalog manifest not found: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            self.load_from_dict_list(data)
        elif isinstance(data, dict) and "assets" in data:
            self.load_from_dict_list(data["assets"])
        else:
            raise ValueError(f"Invalid catalog JSON format in: {json_path}")


def _normalize(text: str) -> str:
    """Normalize text for consistent comparison."""
    return re.sub(r"[^\w\s]", " ", text.lower()).strip()


def _extract_words(text: str) -> Set[str]:
    """Extract set of lowercase words from text."""
    return set(_normalize(text).split())


class VisualResolver:
    """Evaluates scenes against AssetCatalog and resolves quality tier and production strategy."""

    TIER1_SCORE_THRESHOLD: float = 0.75
    TIER2_TIER3_SCORE_THRESHOLD: float = 0.50

    def resolve_scene(self, scene: Scene, catalog: AssetCatalog) -> VisualResolutionResult:
        """Resolve the optimal visual asset and strategy for a single Scene."""
        if scene.visual_brief is None:
            res = VisualResolutionResult(
                scene_id=scene.id,
                tier=ResolutionTier.TIER4_STYLED_FALLBACK,
                asset_path=None,
                production_strategy=VisualProductionStrategy.STYLED_CINEMATIC.value,
                score=0.0,
                rationale="Scene lacks a VisualBrief; falling back to styled cinematic production.",
                rejected_candidates=[],
                rejection_reasons={},
            )
            scene.resolution_tier = res.tier.value
            scene.resolved_asset_path = None
            return res

        brief = scene.visual_brief
        candidates = catalog.list_assets()

        if not candidates:
            res = VisualResolutionResult(
                scene_id=scene.id,
                tier=ResolutionTier.TIER4_STYLED_FALLBACK,
                asset_path=None,
                production_strategy=VisualProductionStrategy.STYLED_CINEMATIC.value,
                score=0.0,
                rationale="AssetCatalog is empty; falling back to styled cinematic production.",
                rejected_candidates=[],
                rejection_reasons={},
            )
            scene.resolution_tier = res.tier.value
            scene.resolved_asset_path = None
            return res

        rejected_candidates: List[str] = []
        rejection_reasons: Dict[str, List[str]] = {}

        # -------------------------------------------------------------
        # Phase 0: Prohibited Mismatch Filter (PRIORIDAD ABSOLUTA)
        # Any prohibited mismatch triggers immediate unconditional rejection
        # -------------------------------------------------------------
        eligible_candidates: List[VisualAssetMetadata] = []
        for cand in candidates:
            prohibited_hits = self._check_prohibited_mismatches(cand, brief.prohibited_mismatches)
            if prohibited_hits:
                rejected_candidates.append(cand.asset_id)
                rejection_reasons[cand.asset_id] = [f"prohibited:{hit}" for hit in prohibited_hits]
            else:
                eligible_candidates.append(cand)

        if not eligible_candidates:
            res = VisualResolutionResult(
                scene_id=scene.id,
                tier=ResolutionTier.TIER4_STYLED_FALLBACK,
                asset_path=None,
                production_strategy=VisualProductionStrategy.STYLED_CINEMATIC.value,
                score=0.0,
                rationale=(
                    "All available candidates were rejected by the prohibited mismatches filter; "
                    "falling back to styled cinematic production."
                ),
                rejected_candidates=rejected_candidates,
                rejection_reasons=rejection_reasons,
            )
            scene.resolution_tier = res.tier.value
            scene.resolved_asset_path = None
            return res

        # -------------------------------------------------------------
        # Phase 1: Deterministic Metadata Scoring
        # -------------------------------------------------------------
        scored_candidates: List[Tuple[float, float, VisualAssetMetadata]] = []
        for cand in eligible_candidates:
            score, era_score = self._calculate_metadata_score(cand, brief)
            scored_candidates.append((score, era_score, cand))

        # Sort deterministically: score desc, video preference desc, asset_id asc
        scored_candidates.sort(
            key=lambda x: (
                x[0],
                1 if x[2].type == "video" else 0,
                -len(x[2].asset_id),
                x[2].asset_id,
            ),
            reverse=True,
        )

        # -------------------------------------------------------------
        # Phase 2: Asset Ladder Traversal (Hierarchical Priority)
        # -------------------------------------------------------------
        best_cand: Optional[VisualAssetMetadata] = None
        selected_tier: Optional[ResolutionTier] = None
        selected_strategy: Optional[str] = None
        selected_score: float = 0.0
        rationale: str = ""

        # Step 1: Look for Tier 1 Exact Match (curated video)
        tier1_candidates = [
            (score, cand)
            for score, era_score, cand in scored_candidates
            if cand.type == "video"
            and score >= self.TIER1_SCORE_THRESHOLD
            and era_score >= 0.80
            and self._is_exact_match(cand, brief)
        ]
        if tier1_candidates:
            selected_score, best_cand = tier1_candidates[0]
            selected_tier = ResolutionTier.TIER1_EXACT
            selected_strategy = VisualProductionStrategy.PASSTHROUGH.value
            rationale = (
                f"Tier 1 Exact Match: Video asset '{best_cand.asset_id}' curated for era '{best_cand.era}' "
                f"and subject '{brief.subject}' (score={selected_score:.2f})."
            )
        else:
            # Step 2: Look for Tier 2 Thematic B-Roll (video >= 0.50)
            tier2_candidates = [
                (score, cand)
                for score, era_score, cand in scored_candidates
                if cand.type == "video" and score >= self.TIER2_TIER3_SCORE_THRESHOLD
            ]
            if tier2_candidates:
                selected_score, best_cand = tier2_candidates[0]
                selected_tier = ResolutionTier.TIER2_THEMATIC
                selected_strategy = VisualProductionStrategy.PASSTHROUGH.value
                rationale = (
                    f"Tier 2 Thematic B-Roll: Video asset '{best_cand.asset_id}' provides compatible thematic footage "
                    f"for era '{brief.era}' (score={selected_score:.2f})."
                )
            else:
                # Step 3: Look for Tier 3 Kinetic Motion (still image + ken_burns >= 0.50)
                tier3_candidates = [
                    (score, cand)
                    for score, era_score, cand in scored_candidates
                    if cand.type == "image" and score >= self.TIER2_TIER3_SCORE_THRESHOLD
                ]
                if tier3_candidates:
                    selected_score, best_cand = tier3_candidates[0]
                    selected_tier = ResolutionTier.TIER3_KINETIC_MOTION
                    selected_strategy = VisualProductionStrategy.KEN_BURNS.value
                    rationale = (
                        f"Tier 3 Kinetic Motion: High-resolution image asset '{best_cand.asset_id}' resolved for "
                        f"motion treatment (score={selected_score:.2f}, strategy='ken_burns')."
                    )
                else:
                    # Step 4: Tier 4 Decision (Styled Cinematic Fallback)
                    selected_tier = ResolutionTier.TIER4_STYLED_FALLBACK
                    selected_strategy = VisualProductionStrategy.STYLED_CINEMATIC.value
                    selected_score = scored_candidates[0][0] if scored_candidates else 0.0
                    rationale = (
                        f"Tier 4 Styled Fallback: No candidate met the minimum quality threshold "
                        f"(best score={selected_score:.2f} < {self.TIER2_TIER3_SCORE_THRESHOLD:.2f}). "
                        f"Delegating to styled cinematic generation in 12B.3."
                    )
                    best_cand = None

        asset_path = best_cand.path if best_cand is not None else None

        # Record non-selected eligible candidates in rejection reasons
        for score, _, cand in scored_candidates:
            if best_cand is not None and cand.asset_id == best_cand.asset_id:
                continue
            rejected_candidates.append(cand.asset_id)
            if score < self.TIER2_TIER3_SCORE_THRESHOLD:
                rejection_reasons[cand.asset_id] = [
                    f"insufficient_score:{score:.2f}<{self.TIER2_TIER3_SCORE_THRESHOLD:.2f}"
                ]
            else:
                rejection_reasons[cand.asset_id] = [
                    f"lower_ranked_score:{score:.2f}<{selected_score:.2f}"
                ]

        res = VisualResolutionResult(
            scene_id=scene.id,
            tier=selected_tier,
            asset_path=asset_path,
            production_strategy=selected_strategy,
            score=round(selected_score, 3),
            rationale=rationale,
            rejected_candidates=sorted(rejected_candidates),
            rejection_reasons=rejection_reasons,
        )

        # Populate Scene fields
        scene.resolution_tier = res.tier.value
        scene.resolved_asset_path = res.asset_path

        return res

    def resolve_story(self, story: StoryArc, catalog: AssetCatalog) -> List[VisualResolutionResult]:
        """Resolve visual assets for all scenes in a StoryArc in sequence."""
        results: List[VisualResolutionResult] = []
        for scene in story.scenes:
            result = self.resolve_scene(scene, catalog)
            results.append(result)
        return results

    def _check_prohibited_mismatches(
        self, asset: VisualAssetMetadata, prohibited_mismatches: List[str]
    ) -> List[str]:
        """Check if any prohibited mismatch is present in asset tags, description, or content warnings."""
        detected: List[str] = []
        asset_text_lower = f"{' '.join(asset.tags)} {asset.description} {' '.join(asset.content_warnings)}".lower()

        for mismatch in prohibited_mismatches:
            clean_mismatch = _normalize(mismatch)
            if not clean_mismatch:
                continue

            # Exact phrase match or individual significant token match
            if clean_mismatch in asset_text_lower:
                detected.append(mismatch)
                continue

            # Check individual tokens if phrase is composite
            mismatch_words = clean_mismatch.split()
            if len(mismatch_words) > 1 and all(w in asset_text_lower for w in mismatch_words):
                detected.append(mismatch)

        return detected

    def _calculate_metadata_score(
        self, asset: VisualAssetMetadata, brief: VisualBrief
    ) -> Tuple[float, float]:
        """Calculate deterministic weighted metadata score (0.0 to 1.0).

        Returns:
            Tuple of (overall_score, era_score).
        """
        asset_tag_words = set()
        for t in asset.tags:
            asset_tag_words.update(_extract_words(t))
        asset_desc_words = _extract_words(asset.description)
        all_asset_words = asset_tag_words | asset_desc_words

        # 1. Keyword Score (weight: 0.40)
        if brief.search_keywords:
            matched_keywords = 0
            for kw in brief.search_keywords:
                kw_words = _extract_words(kw)
                if kw_words and (kw_words.issubset(all_asset_words) or any(w in all_asset_words for w in kw_words)):
                    matched_keywords += 1
            keyword_score = matched_keywords / len(brief.search_keywords)
        else:
            keyword_score = 0.50

        # 2. Era Score (weight: 0.30)
        norm_brief_era = _normalize(brief.era)
        norm_asset_era = _normalize(asset.era)
        if norm_brief_era and norm_asset_era:
            if norm_asset_era in norm_brief_era or norm_brief_era in norm_asset_era:
                era_score = 1.0
            else:
                # Look for 4-digit years in both
                brief_years = re.findall(r"\b(18\d{2}|19\d{2}|20\d{2})\b", brief.era)
                asset_years = re.findall(r"\b(18\d{2}|19\d{2}|20\d{2})\b", asset.era)
                if brief_years and asset_years and set(brief_years) & set(asset_years):
                    era_score = 1.0
                elif any("present" in e or "actual" in e or "modern" in e for e in (norm_brief_era, norm_asset_era)):
                    era_score = 0.8 if norm_brief_era == norm_asset_era else 0.1
                else:
                    era_score = 0.0
        else:
            era_score = 0.50

        # 3. Environment Score (weight: 0.15)
        brief_env_words = _extract_words(brief.environment)
        if brief_env_words:
            matched_env = len(brief_env_words & all_asset_words)
            env_score = min(1.0, matched_env / max(1, len(brief_env_words) * 0.5))
        else:
            env_score = 0.50

        # 4. Type Affinity (weight: 0.15)
        # Video preferred for dynamic short-form; image acceptable for Tier 3
        type_affinity = 1.0 if asset.type == "video" else 0.75

        total_score = round(
            0.40 * keyword_score + 0.30 * era_score + 0.15 * env_score + 0.15 * type_affinity,
            3,
        )
        return total_score, era_score

    def _is_exact_match(self, asset: VisualAssetMetadata, brief: VisualBrief) -> bool:
        """Determine if an asset qualifies as a Tier 1 Exact Match.

        Must have significant token intersection with brief.subject.
        """
        subject_words = _extract_words(brief.subject)
        asset_words = set()
        for t in asset.tags:
            asset_words.update(_extract_words(t))
        asset_words.update(_extract_words(asset.description))

        # Check if core subject tokens are present
        core_tokens = {w for w in subject_words if len(w) > 3}
        if not core_tokens:
            return False
        overlap = core_tokens & asset_words
        return len(overlap) >= max(1, len(core_tokens) * 0.4)

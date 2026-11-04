"""Core data contracts and schemas for the Story Engine (Stage 12B.1).

Defines the contract-driven models for StoryContract, Scene, FactClaim,
VisualBrief, StoryArc, MasterTimeline, and StoryQA reporting.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field



class EndingStrategy(str, Enum):
    PAYOFF = "payoff"
    LOOP = "loop"
    QUESTION = "question"
    CTA = "cta"
    OPEN_LOOP = "open_loop"
    CONCLUSION = "conclusion"


class NarrativeRole(str, Enum):
    HOOK = "hook"
    ORIGIN_CONTEXT = "origin_context"
    DEVELOPMENT_TURNING_POINT = "development_turning_point"
    TRANSFORMATION = "transformation"
    PAYOFF = "payoff"
    CTA = "cta"
    LOOP = "loop"


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    CONTEXT_REQUIRED = "context_required"
    NEEDS_SOURCE = "needs_source"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"
    OPINION_OR_RHETORIC = "opinion_or_rhetoric"


class DurationPolicy(BaseModel):
    hard_minimum_sec: float = Field(default=61.0, description="Strict minimum duration required for monetization")
    planning_target_sec: float = Field(default=78.0, description="Target duration for optimal pacing")
    soft_maximum_sec: float = Field(default=90.0, description="Soft maximum; durations above this trigger a note")


class ResolutionTier(str, Enum):
    TIER1_EXACT = "tier1_exact"
    TIER2_THEMATIC = "tier2_thematic"
    TIER3_KINETIC_MOTION = "tier3_kinetic_motion"
    TIER4_STYLED_FALLBACK = "tier4_styled_fallback"


class VisualProductionStrategy(str, Enum):
    PASSTHROUGH = "passthrough"
    KEN_BURNS = "ken_burns"
    STYLED_CINEMATIC = "styled_cinematic"


class SourceAuthority(str, Enum):
    """Authority tier of a factual evidence source."""
    PRIMARY_INSTITUTIONAL = "primary_institutional"    # National archives, museums, original manufacturers, patents
    SECONDARY_ACADEMIC = "secondary_academic"          # Peer-reviewed history, academic encyclopedias, scholarly papers
    REPUTABLE_JOURNALISM = "reputable_journalism"      # High-standard scientific or investigative journalism
    GENERAL_REFERENCE = "general_reference"            # Open encyclopedias with citations (e.g. Wikipedia)
    COMMERCIAL_OR_PR = "commercial_or_pr"              # Corporate press releases (requires independent corroboration)
    UNVERIFIED = "unverified"                          # Uncited blogs, forums (cannot certify a claim as VERIFIED)


class FactSource(BaseModel):
    """Cataloged evidence source with authority level and independence grouping."""
    source_id: str = Field(..., description="Unique source identifier")
    url: Optional[str] = Field(default=None, description="URL to online reference if available")
    title: str = Field(..., description="Source title or document name")
    publisher: str = Field(..., description="Publishing body, institution or author")
    source_type: str = Field(default="document", description="archive_document, academic_paper, encyclopedic_entry, news")
    authority_level: SourceAuthority = Field(default=SourceAuthority.GENERAL_REFERENCE, description="Assigned authority tier")
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when evidence was acquired")
    publication_date: Optional[datetime] = Field(default=None, description="Original publication date")
    license: Optional[str] = Field(default="Public Domain", description="License or copyright terms")
    independence_group: Optional[str] = Field(default=None, description="Corporate/publisher group for corroboration independence")
    content_hash_sha256: str = Field(default="", description="Cryptographic SHA-256 of raw snapshot content")


class EvidenceSnapshot(BaseModel):
    """Captured textual evidence excerpt with exact source locator."""
    snapshot_id: str = Field(..., description="Unique snapshot identifier")
    source_id: str = Field(..., description="Referenced FactSource ID")
    raw_text: str = Field(..., description="Raw excerpt or extracted document text")
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Capture timestamp")
    source_locator: Optional[str] = Field(default=None, description="Exact locator (e.g. p. 14, sec. 2, 02:15)")
    snapshot_sha256: str = Field(default="", description="SHA-256 of raw_text")


class FactClaim(BaseModel):
    """Atomic factual assertion with multi-source grounding, boundaries, and wording constraints."""
    claim_id: Optional[str] = Field(default=None, description="Unique claim identifier")
    claim_text: str = Field(..., description="Atomic factual assertion")
    source_ids: List[str] = Field(default_factory=list, description="IDs of supporting FactSources")
    entity: Optional[str] = Field(default=None, description="Primary entity or subject")
    date_or_era: Optional[str] = Field(default=None, description="Historical period or exact date")
    status: ClaimStatus = Field(default=ClaimStatus.NEEDS_SOURCE, description="Factual integrity status")
    scope: Optional[str] = Field(default=None, description="Scope or qualifiers that bound the assertion")
    supporting_excerpt: Optional[str] = Field(default=None, description="Textual quote backing the claim")
    source_locator: Optional[str] = Field(default=None, description="Exact locator within the source")
    verification_notes: Optional[str] = Field(default=None, description="Editorial or QA verification notes")
    allowed_wording: Optional[str] = Field(default=None, description="Permitted phrasing bounds")
    prohibited_wording: List[str] = Field(default_factory=list, description="Phrasing or exaggerations strictly prohibited")
    # Backwards compatibility fields for Stage 12B:
    source_reference: Optional[str] = Field(default=None, description="Legacy citation reference string")
    wording_constraints: List[str] = Field(default_factory=list, description="Legacy phrasing constraints")

    @property
    def certainty(self) -> ClaimStatus:
        """Alias for status to maintain semantic consistency across 12C modules."""
        return self.status


class FactDossier(BaseModel):
    """Immutable, versioned factual dossier acting as the sole authority of truth for a production run."""
    dossier_id: str = Field(..., description="Unique dossier identifier")
    run_id: str = Field(..., description="Production execution run ID")
    version: int = Field(default=1, description="Dossier version number (v1, v2, ...)")
    topic: str = Field(..., description="Researched core topic")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Compilation timestamp")
    sources: Dict[str, FactSource] = Field(default_factory=dict, description="Mapped sources by source_id")
    snapshots: Dict[str, EvidenceSnapshot] = Field(default_factory=dict, description="Evidence snapshots by snapshot_id")
    claims: Dict[str, FactClaim] = Field(default_factory=dict, description="Atomic claims by claim_id")
    timeline_milestones: List[str] = Field(default_factory=list, description="Ordered chronological milestones")
    key_entities: List[str] = Field(default_factory=list, description="Mandatory entities to be respected")
    dossier_sha256: str = Field(default="", description="Deterministic cryptographic SHA-256 hash")
    frozen: bool = Field(default=False, description="Whether dossier is locked for read-only use in execution")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "frozen", False) and name != "frozen":
            raise TypeError(f"FactDossier '{self.dossier_id}' is frozen and cannot be modified. Create a new revision.")
        super().__setattr__(name, value)




class ContinuityRequirement(BaseModel):
    visual_anchor: Optional[str] = Field(default=None, description="Recurring visual anchor to preserve continuity")
    era_progression: Optional[str] = Field(default=None, description="Era or chronological sequence marker")
    lighting_mood: Optional[str] = Field(default=None, description="Lighting tone consistency")


class VisualBrief(BaseModel):
    subject: str = Field(..., description="Primary subject of the scene")
    era: str = Field(..., description="Historical or temporal period")
    environment: str = Field(..., description="Physical or thematic setting")
    action: str = Field(..., description="Key visual action or dynamics")
    mood: str = Field(..., description="Visual tone or aesthetic feel")
    search_keywords: List[str] = Field(default_factory=list, description="Targeted keywords for visual matching")
    prohibited_mismatches: List[str] = Field(default_factory=list, description="Explicit visual elements forbidden in this scene")
    continuity: Optional[ContinuityRequirement] = Field(default=None, description="Continuity rules across scenes")


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    confidence: float = 1.0


class Scene(BaseModel):
    id: str = Field(..., description="Unique string identifier for the scene, e.g. scene_01")
    scene_index: int = Field(..., description="0-indexed sequence position in story")
    narrative_role: NarrativeRole = Field(..., description="Dramatic role in narrative arc")
    dependencies: List[str] = Field(default_factory=list, description="IDs of preceding scenes this scene depends on")
    script_text: str = Field(..., description="Narration script for this scene")
    word_count: int = Field(..., description="Count of words in script_text")
    estimated_duration_sec: float = Field(..., description="Planned duration based on planning heuristic")

    # Downstream media fields preserved for 12B.2 and 12B.3 (Optional / None in 12B.1)
    actual_duration_sec: Optional[float] = Field(default=None, description="Measured audio duration once synthesized")
    voice_audio_path: Optional[Path] = Field(default=None, description="Path to generated voiceover audio")
    word_timings: List[WordTimestamp] = Field(default_factory=list, description="Word-level timestamps from alignment")
    resolved_asset_path: Optional[Path] = Field(default=None, description="Path to selected visual asset")
    resolution_tier: Optional[str] = Field(default=None, description="Resolution tier (e.g. tier1_exact, tier2_thematic)")

    visual_brief: Optional[VisualBrief] = Field(default=None, description="Decoupled visual instructions")
    factual_claims: List[FactClaim] = Field(default_factory=list, description="Atomic claims asserted in this scene")
    scene_qa_passed: bool = Field(default=False, description="Whether scene passed atomic scene QA")
    scene_qa_failures: List[str] = Field(default_factory=list, description="List of failures if scene QA failed")


class StoryContract(BaseModel):
    id: str = Field(..., description="Contract identifier")
    title: str = Field(..., description="Working title")
    topic: str = Field(..., description="Core topic or concept")
    core_question: str = Field(..., description="Central narrative question being explored")
    narrative_promise: str = Field(..., description="Promise made to viewer in opening")
    target_audience: str = Field(default="general", description="Intended audience profile")
    tone: str = Field(default="curious_informative", description="Editorial tone")
    duration_policy: DurationPolicy = Field(default_factory=DurationPolicy, description="Duration thresholds")
    must_include_entities: List[str] = Field(default_factory=list, description="Entities/names required in story")
    must_avoid_pitfalls: List[str] = Field(default_factory=list, description="Phrases, tropes, or clichés forbidden")
    ending_strategy: EndingStrategy = Field(default=EndingStrategy.PAYOFF, description="How the narrative resolves")


class StoryArc(BaseModel):
    id: str = Field(..., description="Story arc identifier")
    contract: StoryContract = Field(..., description="Contract governing this story")
    scenes: List[Scene] = Field(default_factory=list, description="Sequential list of scenes")
    target_duration_sec: float = Field(default=78.0, description="Target planned duration")
    total_estimated_duration_sec: float = Field(default=0.0, description="Sum of estimated scene durations")
    status: str = Field(default="draft", description="Status: draft, qa_passed, qa_failed, ready_for_production")


class MasterTimeline(BaseModel):
    story_id: str = Field(..., description="Associated story ID")
    target_duration_sec: float = Field(..., description="Planned total duration")
    total_actual_duration_sec: float = Field(default=0.0, description="Sum of physical actual durations of scenes")
    scene_order: List[str] = Field(default_factory=list, description="Ordered list of scene IDs")
    scene_offsets: Dict[str, float] = Field(default_factory=dict, description="Cumulative start offset per scene ID")
    scene_durations: Dict[str, float] = Field(default_factory=dict, description="Physical duration per scene ID")
    video_tracks: List[Dict[str, Any]] = Field(default_factory=list, description="Sequence of visual track segments")
    voice_tracks: List[Dict[str, Any]] = Field(default_factory=list, description="Sequence of audio track segments")
    bgm_applied: bool = Field(default=False, description="Whether background music was mixed into master audio")
    master_video_path: Optional[Path] = Field(default=None, description="Path to assembled master MP4 video")
    master_audio_path: Optional[Path] = Field(default=None, description="Path to mastered continuous audio")
    master_subtitles_path: Optional[Path] = Field(default=None, description="Path to unified master subtitles (.ass)")
    caption_track_path: Optional[Path] = Field(default=None, description="Path to unified master subtitles (.ass)")
    bgm_track_path: Optional[Path] = Field(default=None, description="Path to background music file")
    global_audio_policy: Dict[str, Any] = Field(default_factory=dict, description="EBU R128 compliance targets")


class StoryQAFinding(BaseModel):
    rule: str = Field(..., description="QA rule name that generated the finding")
    severity: str = Field(..., description="ERROR, WARNING, or INFO")
    scene_id: Optional[str] = Field(default=None, description="Associated scene ID if applicable")
    message: str = Field(..., description="Detailed description of the issue or observation")
    remediation: str = Field(..., description="Actionable instruction on how to fix or address")


class StoryQAReport(BaseModel):
    passed: bool = Field(..., description="True if no ERROR severity findings exist")
    total_estimated_duration_sec: float = Field(..., description="Evaluated total estimated duration")
    findings: List[StoryQAFinding] = Field(default_factory=list, description="List of findings")
    checks: Dict[str, bool] = Field(default_factory=dict, description="Summary status of each evaluated check")


class VisualAssetMetadata(BaseModel):
    asset_id: str = Field(..., description="Unique identifier of asset")
    path: Path = Field(..., description="Local path to asset file")
    type: str = Field(..., description="Asset media type: 'video' or 'image'")
    era: str = Field(..., description="Historical era, e.g. '1886' or 'present'")
    visual_period: Optional[str] = Field(default=None, description="Broader period label")
    tags: List[str] = Field(default_factory=list, description="Descriptive and thematic tags")
    description: str = Field(..., description="Detailed description of visual content")
    aspect_ratio: str = Field(default="9:16", description="Aspect ratio, e.g. '9:16'")
    width: int = Field(default=1080, description="Pixel width")
    height: int = Field(default=1920, description="Pixel height")
    duration_sec: Optional[float] = Field(default=None, description="Video duration in seconds if video")
    source: str = Field(default="local_curated", description="Source or repository where acquired")
    license: str = Field(default="Royalty-Free", description="License identifier or terms")
    provenance: Optional[str] = Field(default=None, description="Provenance archive or collection citation")
    content_warnings: List[str] = Field(default_factory=list, description="Content warnings or tags")


class VisualResolutionResult(BaseModel):
    scene_id: str = Field(..., description="Target scene ID")
    tier: ResolutionTier = Field(..., description="Resolved quality tier in asset ladder")
    asset_path: Optional[Path] = Field(default=None, description="Resolved asset path (None for Tier 4)")
    production_strategy: str = Field(..., description="Production strategy for 12B.3: passthrough, ken_burns, styled_cinematic")
    score: float = Field(..., description="Deterministic metadata match score (0.0 to 1.0)")
    rationale: str = Field(..., description="Human-readable decision explanation")
    rejected_candidates: List[str] = Field(default_factory=list, description="List of candidate asset IDs considered but not chosen")
    rejection_reasons: Dict[str, List[str]] = Field(default_factory=dict, description="Reasons for rejection per asset ID")


class PublicationStatus(str, Enum):
    """Publication certification status for Master Timeline video."""
    CERTIFIED_FOR_PUBLICATION = "certified_for_publication"
    CERTIFIED_WITH_WARNINGS = "certified_with_warnings"
    REJECTED = "rejected"


class MediaQAFinding(BaseModel):
    """Atomic issue or diagnostic finding discovered during Final Media QA."""
    rule: str = Field(..., description="Audit rule identifier, e.g. 'container_format', 'loudness_ebur128'")
    severity: str = Field(..., description="ERROR, WARNING, or INFO")
    message: str = Field(..., description="Detailed diagnostic observation")
    remediation: str = Field(..., description="Actionable instruction on how to fix or address the issue")


class FinalMediaQAReport(BaseModel):
    """Comprehensive forensic report and publication certification for master story video."""
    story_id: str = Field(..., description="Associated story arc ID")
    master_video_path: Path = Field(..., description="Path to inspected master story MP4")
    status: PublicationStatus = Field(..., description="Certification verdict")
    passed: bool = Field(..., description="True if no ERROR severity findings exist")
    duration_sec: float = Field(default=0.0, description="Measured physical duration of master MP4 in seconds")
    scene_duration_sum_sec: float = Field(default=0.0, description="Sum of physical scene actual durations in seconds")
    duration_drift_sec: float = Field(default=0.0, description="Absolute difference between master and scene sum")
    video_metrics: Dict[str, Any] = Field(default_factory=dict, description="Video stream forensic metrics (codec, dims, fps, pix_fmt)")
    audio_metrics: Dict[str, Any] = Field(default_factory=dict, description="Audio stream forensic metrics (codec, sample_rate, lufs, true_peak)")
    subtitle_metrics: Dict[str, Any] = Field(default_factory=dict, description="Subtitle forensic metrics (events, spoken_coverage_pct, max_gap)")
    scenes: List[Dict[str, Any]] = Field(default_factory=list, description="Traceability list of scenes with physical durations and offsets")
    checks: Dict[str, bool] = Field(default_factory=dict, description="Binary pass/fail status per audit dimension")
    findings: List[MediaQAFinding] = Field(default_factory=list, description="List of granular audit findings")
    certified_output_path: Optional[Path] = Field(default=None, description="Export path if certified for publication")
    manifest_path: Optional[Path] = Field(default=None, description="Path to cryptographic manifest.json if certified")
    master_sha256: Optional[str] = Field(default=None, description="SHA-256 cryptographic hash of certified master video")


class StatementType(str, Enum):
    """Semantic classification of an assertion unit in narration."""
    FACTUAL = "factual"          # Atomic assertion about reality; MANDATORY grounding in FactDossier
    INTERPRETIVE = "interpretive"  # Thematic contextualization; bounded wording
    NARRATIVE = "narrative"        # Creative framing, hooks, rhetorical prose; free within StoryContract
    TRANSITION = "transition"      # Bridging phrases between thoughts or scenes; free


class AssertionUnit(BaseModel):
    """Granular narrative or factual statement within a scene narration."""
    text: str = Field(..., description="Sentence or clause uttered in narration")
    statement_type: StatementType = Field(..., description="Classification: factual, interpretive, narrative, transition")
    claim_ids: List[str] = Field(default_factory=list, description="IDs of FactClaims in FactDossier backing this statement if factual")


class SceneDraft(BaseModel):
    """Draft representation of a scene generated by LLM before grounding validation."""
    scene_id: str = Field(..., description="Scene identifier (e.g. scene_01)")
    scene_index: int = Field(..., description="0-indexed order")
    narrative_role: NarrativeRole = Field(..., description="Dramatic role")
    narration: str = Field(..., description="Complete narration text for the scene")
    assertions: List[AssertionUnit] = Field(default_factory=list, description="Decomposed statement units for claim verification")
    visual_intent: Optional[VisualBrief] = Field(default=None, description="Visual description, era, and prohibited mismatches")
    dependencies: List[str] = Field(default_factory=list, description="Preceding scene dependencies")


class StoryDraft(BaseModel):
    """Structured proposal generated by LLM from a FactDossier and CreativeBrief."""
    title: str = Field(..., description="Story title")
    topic: str = Field(..., description="Core subject matter")
    core_question: str = Field(..., description="Central narrative question explored")
    narrative_promise: str = Field(..., description="Promise made to the viewer")
    hook_strategy: str = Field(default="surprise", description="contradiction, surprise, question, cold_open, etc.")
    scenes: List[SceneDraft] = Field(default_factory=list, description="Sequential scene drafts")
    ending_strategy: EndingStrategy = Field(default=EndingStrategy.PAYOFF, description="Resolution strategy")
    target_audience: str = Field(default="general", description="Audience profile")
    tone: str = Field(default="curious_informative", description="Editorial tone")
    dossier_id: str = Field(..., description="ID of FactDossier this story was synthesized from")
    dossier_sha256: str = Field(..., description="SHA-256 of FactDossier ensuring grounding integrity")


class GroundingFinding(BaseModel):
    """Finding generated by ClaimGroundingGate during validation."""
    rule: str = Field(..., description="Violated rule: UNGROUNDED_FACTUAL_ASSERTION, FABRICATED_CLAIM_ID, etc.")
    severity: str = Field(..., description="ERROR or WARNING")
    scene_id: str = Field(..., description="Target scene ID")
    assertion_text: str = Field(..., description="Offending assertion text")
    claim_id: Optional[str] = Field(default=None, description="Associated claim ID if relevant")
    message: str = Field(..., description="Detailed explanation of the issue")
    remediation: str = Field(..., description="Actionable instruction on how to fix the issue")


class GroundingReport(BaseModel):
    """Evaluation report generated by ClaimGroundingGate."""
    passed: bool = Field(..., description="True if no ERROR severity findings exist")
    total_assertions: int = Field(default=0, description="Total count of evaluated assertions")
    factual_assertions: int = Field(default=0, description="Count of assertions classified as FACTUAL")
    grounded_assertions: int = Field(default=0, description="Count of factual assertions properly grounded")
    orphan_assertions: int = Field(default=0, description="Count of factual assertions with no claim_ids")
    fabricated_claim_ids: int = Field(default=0, description="Count of invalid claim IDs not in dossier")
    overclaiming_assertions: int = Field(default=0, description="Count of assertions violating wording boundaries")
    findings: List[GroundingFinding] = Field(default_factory=list, description="List of granular audit findings")
    scene_status: Dict[str, bool] = Field(default_factory=dict, description="Pass/fail status per scene_id")



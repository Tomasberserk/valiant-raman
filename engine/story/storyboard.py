"""Canonical Storyboard Contracts & Data Models (Pydantic v2).

Audited and approved by Claude 3.5 Sonnet & ChatGPT o1.
Enforces:
- VisualShot as atomic production unit with dedicated duration_sec.
- Separation between creative plan (VisualShot) and rendered artifact (ShotRenderResult).
- Strict timing validation: Scene duration equals sum of shot durations.
- Global Storyboard music_mood with per-scene intensity and dip windows.
- SfxCue timings relative to Scene, strictly bounded by Scene duration.
- Preserved EvidenceReference for factual mode integrity.
"""

from enum import Enum
import re
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.creative.modes import ResolvedContentMode


class BeatRole(str, Enum):
    HOOK = "hook"
    INCIDENT = "incident"
    TURNING_POINT = "turning_point"
    ESCALATION = "escalation"
    CLIMAX = "climax"
    CLIFFHANGER = "cliffhanger"


class CameraMove(str, Enum):
    STATIC = "static"
    PUSH_IN = "push_in"
    PULL_OUT = "pull_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"


class TransitionType(str, Enum):
    CUT = "cut"
    FLASH_WHITE = "flash_white"
    GLITCH = "glitch"
    ZOOM_IN = "zoom_in"
    DIP_TO_BLACK = "dip_to_black"


class RenderTier(str, Enum):
    PROCEDURAL = "procedural"
    STOCK = "stock"
    IMAGE_MOTION = "image_motion"
    I2V = "i2v"


class CharacterAnchor(BaseModel):
    """Immutable visual description of a character to ensure consistency across shots."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: str
    visual_anchor: str = Field(
        min_length=15,
        description="Literal physical descriptor injected into all prompts (e.g. 'a 19yo male warrior, messy black hair, dark leather tunic, scarred eyebrow')",
    )
    reference_image_path: Optional[str] = None
    seed: Optional[int] = None


class StyleBible(BaseModel):
    """Global aesthetic identity for the storyboard."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    art_style: str = Field(default="dark fantasy anime, cel-shaded, cinematic lighting, Unreal Engine 5 render style")
    color_palette: List[str] = Field(default_factory=lambda: ["#07090E", "#7C3AED", "#06B6D4"])
    negative_global: str = "blurry, low quality, deformed, extra limbs, bad anatomy, text, watermark"
    aspect_ratio: str = "9:16"


class VisualShot(BaseModel):
    """The atomic creative unit of video production."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    shot_id: str
    duration_sec: float = Field(ge=2.0, le=6.0, description="Exact planned duration for this shot in seconds")
    action_prompt_en: str = Field(
        min_length=10,
        description="Core physical action and framing in English (e.g. 'close-up of hands pulling ancient glowing sword from roots')",
    )
    framing: str = Field(default="medium shot", description="Framing type (e.g. 'extreme close-up', 'low-angle wide shot')")
    lighting: str = Field(default="cinematic dark fantasy, stormy skies, high contrast rim light")
    camera_move: CameraMove = CameraMove.PUSH_IN
    characters_present: List[str] = Field(default_factory=list)
    preferred_tier: RenderTier = RenderTier.IMAGE_MOTION

    def compose_full_prompt(self, style_bible: StyleBible, characters: List[CharacterAnchor]) -> str:
        """Compose final prompt by stitching style, character anchors, and specific shot action."""
        anchors = []
        for char_id in self.characters_present:
            for c in characters:
                if c.character_id == char_id:
                    anchors.append(c.visual_anchor)

        parts = [self.action_prompt_en]
        if anchors:
            parts.append(f"featuring {', '.join(anchors)}")
        parts.append(f"Style: {style_bible.art_style}")
        parts.append(f"Lighting: {self.lighting}")
        parts.append(f"Framing: {self.framing}")
        return ", ".join(parts)


class SfxCue(BaseModel):
    """Sound effect event precisely timed within a Scene."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    sound_tag: str = Field(description="Normalized tag corresponding to SFX asset library (e.g. 'thunder_strike', 'sword_drawn')")
    at_sec: float = Field(ge=0.0, description="Offset in seconds relative to the beginning of the Scene")
    volume_db: float = Field(default=0.0, ge=-30.0, le=6.0)
    duck_bgm: bool = Field(default=False, description="Set True only for massive peak impacts requiring BGM suppression")


class AudioTrackPlan(BaseModel):
    """Audio plan for a Scene."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    voiceover_text: Optional[str] = None
    music_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    music_dip_start: Optional[float] = None
    music_dip_end: Optional[float] = None
    sfx_cues: List[SfxCue] = Field(default_factory=list)


class Scene(BaseModel):
    """A dramatic narrative beat composed of one or more atomic shots."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: str
    role: BeatRole
    shots: List[VisualShot] = Field(min_length=1)
    audio_plan: AudioTrackPlan
    transition_out: TransitionType = TransitionType.CUT

    @property
    def duration_sec(self) -> float:
        """Computed exact duration derived directly from atomic shot durations."""
        return round(sum(s.duration_sec for s in self.shots), 2)

    @model_validator(mode="after")
    def validate_scene_integrity(self):
        # 1. Verify all SFX cues fall within scene duration
        scene_dur = self.duration_sec
        for cue in self.audio_plan.sfx_cues:
            if cue.at_sec > scene_dur:
                raise ValueError(
                    f"SfxCue '{cue.sound_tag}' at {cue.at_sec:.1f}s exceeds Scene '{self.scene_id}' duration of {scene_dur:.1f}s."
                )

        # 2. Verify dip windows
        dip_start = self.audio_plan.music_dip_start
        dip_end = self.audio_plan.music_dip_end
        if dip_start is not None and dip_end is not None:
            if dip_start >= dip_end:
                raise ValueError(f"music_dip_start ({dip_start}s) must be strictly less than music_dip_end ({dip_end}s).")
            if dip_end > scene_dur:
                raise ValueError(f"music_dip_end ({dip_end}s) exceeds scene duration ({scene_dur}s).")

        return self


class EvidenceReference(BaseModel):
    """Traceable citation record for factual/curiosity mode."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    source_title: str
    source_locator: Optional[str] = None


class Storyboard(BaseModel):
    """The complete, unified creative contract for audiovisual compilation."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ResolvedContentMode
    title: str = Field(min_length=3)
    target_duration_sec: float = Field(ge=8.0, le=90.0)
    style_bible: StyleBible
    music_mood: str = Field(default="epic_dark_cinematic_suspense", description="Global unified BGM soundtrack style")
    characters: List[CharacterAnchor] = Field(default_factory=list)
    scenes: List[Scene] = Field(min_length=3)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)

    @property
    def total_physical_duration(self) -> float:
        """Total duration computed across all scenes and shots."""
        return round(sum(s.duration_sec for s in self.scenes), 2)

    @property
    def total_duration_sec(self) -> float:
        """Alias for total_physical_duration."""
        return self.total_physical_duration

    @property
    def id(self) -> str:
        """Deterministic storyboard identifier derived from title and duration."""
        clean_title = re.sub(r"[^\w\s-]", "", self.title).strip().lower().replace(" ", "_")
        return f"sb_{clean_title[:24]}_{int(self.target_duration_sec)}s"

    @model_validator(mode="after")
    def validate_storyboard_budget_and_continuity(self):
        # 1. Validate total duration against target duration within ±15% tolerance
        actual_total = self.total_physical_duration
        target = self.target_duration_sec
        tolerance = target * 0.15
        if abs(actual_total - target) > tolerance:
            raise ValueError(
                f"Duración total del storyboard ({actual_total:.1f}s) fuera del presupuesto objetivo ({target:.1f}s ± {tolerance:.1f}s)."
            )

        # 2. Validate unique IDs across scenes and shots
        scene_ids = set()
        shot_ids = set()
        for sc in self.scenes:
            if sc.scene_id in scene_ids:
                raise ValueError(f"Identificador de escena duplicado: '{sc.scene_id}'.")
            scene_ids.add(sc.scene_id)
            for sh in sc.shots:
                if sh.shot_id in shot_ids:
                    raise ValueError(f"Identificador de toma duplicado: '{sh.shot_id}'.")
                shot_ids.add(sh.shot_id)

        # 3. Validate character references exist
        valid_char_ids = {c.character_id for c in self.characters}
        for sc in self.scenes:
            for sh in sc.shots:
                for cid in sh.characters_present:
                    if cid not in valid_char_ids:
                        raise ValueError(f"Personaje '{cid}' en toma '{sh.shot_id}' no está registrado en Storyboard.characters.")

        return self


class ShotRenderResult(BaseModel):
    """Physical artifact metadata produced by the VisualOrchestrator for a single VisualShot."""
    shot_id: str
    image_path: Optional[str] = None
    video_path: str
    duration_seconds: float
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    provider_name: str
    model_version: str
    render_tier: RenderTier
    seed: Optional[int] = None
    cache_hash: str
    qa_passed: bool = True

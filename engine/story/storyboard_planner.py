"""Storyboard Planner: Multi-beat dramatic director generating canonical Storyboards.

Follows the 3-step structured pipeline:
1. Story Bible (Protagonist character anchor + visual style + music mood)
2. Beat Sheet (Hook -> Incident -> Turn -> Escalation -> Climax -> Cliffhanger)
3. Shot List (Atomic shots 2.5s-5.0s, action prompts, camera moves, and timed SFX cues)
"""

import json
import logging
import os
import re
from typing import List, Optional

from engine.creative.modes import ContentModeRequest, ContentModeRouter, ResolvedContentMode
from engine.story.semantic_qa import SemanticAntiTemplateValidator
from engine.story.storyboard import (
    AudioTrackPlan,
    BeatRole,
    CameraMove,
    CharacterAnchor,
    EvidenceReference,
    RenderTier,
    Scene,
    SfxCue,
    Storyboard,
    StyleBible,
    TransitionType,
    VisualShot,
)

logger = logging.getLogger(__name__)


class StoryboardPlanner:
    """Orchestrates structured cinematic storyboarding for narrative fiction and factual content."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model

    def plan_storyboard(
        self,
        raw_prompt: str,
        target_duration_sec: float = 25.0,
        requested_mode: ContentModeRequest = ContentModeRequest.AUTO,
    ) -> Storyboard:
        """Create a complete, verified Storyboard from user brief."""
        cleaned = raw_prompt.strip()
        mode = ContentModeRouter.resolve_mode(cleaned, requested_mode=requested_mode)

        if mode == ResolvedContentMode.NARRATIVE_FICTION:
            return self._plan_narrative_storyboard(cleaned, target_duration_sec)
        else:
            return self._plan_factual_storyboard(cleaned, target_duration_sec)

    def _plan_narrative_storyboard(self, prompt: str, target_duration_sec: float) -> Storyboard:
        """Synthesize narrative fiction storyboard."""
        # Check if LLM is available
        if self.api_key:
            try:
                return self._call_gemini_storyboard(prompt, target_duration_sec)
            except Exception as e:
                logger.warning(f"Error calling Gemini for Storyboard ({e}). Falling back to deterministic narrative planner.")

        # Deterministic offline narrative synthesis
        return self._synthesize_deterministic_narrative(prompt, target_duration_sec)

    def _synthesize_deterministic_narrative(self, prompt: str, target_duration_sec: float) -> Storyboard:
        """Construct a high-retention cinematic narrative storyboard offline."""
        prompt_lower = prompt.lower()

        # 1. Story Bible
        protagonist = CharacterAnchor(
            character_id="hero_protagonist",
            visual_anchor="a 19yo male warrior, short messy black hair, scar over left eyebrow, dark weathered leather tunic",
        )

        style = StyleBible(
            art_style="dark fantasy anime, cel-shaded, cinematic atmosphere, Unreal Engine 5 render style",
            color_palette=["#07090E", "#7C3AED", "#06B6D4", "#F59E0B"],
        )

        # 2. Divide target duration into 6 discrete narrative beats
        # E.g. for 25s: [4.0, 4.0, 4.0, 4.0, 5.0, 4.0] = 25.0s
        dur_unit = round(target_duration_sec / 6.0, 1)
        durations = [dur_unit] * 5
        durations.append(round(target_duration_sec - sum(durations), 1))

        scenes = [
            Scene(
                scene_id="scene_01_hook",
                role=BeatRole.HOOK,
                shots=[
                    VisualShot(
                        shot_id="sh_01_discovery",
                        duration_sec=durations[0],
                        action_prompt_en="a young warrior kneels among giant mossy roots in a lost ancient forest, discovering an old sword half-buried in the soil",
                        framing="low-angle medium shot",
                        lighting="mystical dim forest canopy, soft volumetric morning light",
                        camera_move=CameraMove.PUSH_IN,
                        characters_present=["hero_protagonist"],
                        preferred_tier=RenderTier.IMAGE_MOTION,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text="En lo profundo de aquel bosque olvidado, una espada dormía entre las raíces milenarias.",
                    music_intensity=0.4,
                    sfx_cues=[
                        SfxCue(sound_tag="forest_wind_rustle", at_sec=0.5, volume_db=-6.0),
                    ],
                ),
                transition_out=TransitionType.CUT,
            ),
            Scene(
                scene_id="scene_02_incident",
                role=BeatRole.INCIDENT,
                shots=[
                    VisualShot(
                        shot_id="sh_02_touch",
                        duration_sec=durations[1],
                        action_prompt_en="extreme close-up of dirty hands firmly grasping the dark hilt of the ancient sword, ancient glowing blue runes suddenly igniting along the blade",
                        framing="extreme close-up",
                        lighting="vivid blue arcane glow reflecting on fingers and moss",
                        camera_move=CameraMove.PUSH_IN,
                        characters_present=["hero_protagonist"],
                        preferred_tier=RenderTier.I2V,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text="Al apretar la empuñadura, una vibración ancestral despertó desde el acero.",
                    music_intensity=0.6,
                    sfx_cues=[
                        SfxCue(sound_tag="rune_arcane_charge", at_sec=1.2, volume_db=-2.0),
                    ],
                ),
                transition_out=TransitionType.FLASH_WHITE,
            ),
            Scene(
                scene_id="scene_03_turn",
                role=BeatRole.TURNING_POINT,
                shots=[
                    VisualShot(
                        shot_id="sh_03_sky_shift",
                        duration_sec=durations[2],
                        action_prompt_en="wide shot of the sky instantly mutating from peaceful golden daylight into menacing obsidian clouds with violent purple lightning arcs",
                        framing="wide upward shot",
                        lighting="pitch dark stormy atmosphere torn by violent purple and white lightning flashes",
                        camera_move=CameraMove.TILT_UP,
                        characters_present=["hero_protagonist"],
                        preferred_tier=RenderTier.IMAGE_MOTION,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text="El cielo brillante se quebró en un instante, transformándose en una pesadilla de relámpagos.",
                    music_intensity=0.8,
                    music_dip_start=1.0,
                    music_dip_end=2.2,
                    sfx_cues=[
                        SfxCue(sound_tag="heavy_thunder_crack", at_sec=1.5, volume_db=2.0, duck_bgm=True),
                    ],
                ),
                transition_out=TransitionType.CUT,
            ),
            Scene(
                scene_id="scene_04_escalation",
                role=BeatRole.ESCALATION,
                shots=[
                    VisualShot(
                        shot_id="sh_04_threat",
                        duration_sec=durations[3],
                        action_prompt_en="menacing shadowy scavenger wraiths rising on the dark horizon above dead trees, spectral claws pointing directly at the young warrior to kill him",
                        framing="long shot with Dutch angle",
                        lighting="eerie glowing red spectral eyes through rain and lightning flashes",
                        camera_move=CameraMove.PUSH_IN,
                        characters_present=["hero_protagonist"],
                        preferred_tier=RenderTier.IMAGE_MOTION,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text="En el horizonte, sombras carroñeras emergieron entre la niebla, señalándolo con sed de muerte.",
                    music_intensity=0.9,
                    sfx_cues=[
                        SfxCue(sound_tag="spectral_wraith_shriek", at_sec=1.0, volume_db=-1.0),
                    ],
                ),
                transition_out=TransitionType.GLITCH,
            ),
            Scene(
                scene_id="scene_05_climax",
                role=BeatRole.CLIMAX,
                shots=[
                    VisualShot(
                        shot_id="sh_05_combat_parry",
                        duration_sec=durations[4],
                        action_prompt_en="the young warrior unsheathes the glowing sword in high speed combat stance, deflecting dark energy blast with a furious swing creating sparks",
                        framing="low-angle dynamic action shot",
                        lighting="intense lightning illumination, sparks and arcane explosion reflections",
                        camera_move=CameraMove.PUSH_IN,
                        characters_present=["hero_protagonist"],
                        preferred_tier=RenderTier.I2V,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text="No había escapatoria. Solo quedaba empuñar el poder prohibido y pelear por su vida.",
                    music_intensity=1.0,
                    sfx_cues=[
                        SfxCue(sound_tag="sword_deflection_impact", at_sec=1.8, volume_db=3.0, duck_bgm=True),
                    ],
                ),
                transition_out=TransitionType.CUT,
            ),
            Scene(
                scene_id="scene_06_cliffhanger",
                role=BeatRole.CLIFFHANGER,
                shots=[
                    VisualShot(
                        shot_id="sh_06_cliffhanger",
                        duration_sec=durations[5],
                        action_prompt_en="close-up of the warrior breathing heavily with eyes glowing with electric power, as a colossal shadow rises right behind him",
                        framing="tight close-up",
                        lighting="backlit silhouette with dramatic lightning rim light",
                        camera_move=CameraMove.PULL_OUT,
                        characters_present=["hero_protagonist"],
                        preferred_tier=RenderTier.IMAGE_MOTION,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text="La batalla apenas comenzaba... y el verdadero dueño de la espada acababa de despertar.",
                    music_intensity=0.85,
                    sfx_cues=[
                        SfxCue(sound_tag="monster_deep_roar", at_sec=1.5, volume_db=0.0),
                    ],
                ),
                transition_out=TransitionType.DIP_TO_BLACK,
            ),
        ]

        title = "La Espada de las Sombras" if "espada" in prompt_lower else "Crónica: El Despertar"
        storyboard = Storyboard(
            mode=ResolvedContentMode.NARRATIVE_FICTION,
            title=title,
            target_duration_sec=target_duration_sec,
            style_bible=style,
            music_mood="epic_dark_cinematic_suspense",
            characters=[protagonist],
            scenes=scenes,
        )

        # Validate semantic integrity (zero documentary clichés)
        full_narration = " ".join(s.audio_plan.voiceover_text for s in storyboard.scenes if s.audio_plan.voiceover_text)
        SemanticAntiTemplateValidator.validate_text(
            full_narration,
            mode=ResolvedContentMode.NARRATIVE_FICTION,
            raise_on_violation=True,
        )

        return storyboard

    def _plan_factual_storyboard(self, prompt: str, target_duration_sec: float) -> Storyboard:
        """Synthesize factual curiosity storyboard with grounded evidence references."""
        from engine.creative.knowledge import KnowledgeBank

        fact = KnowledgeBank.find_fact(prompt)
        dur_unit = round(target_duration_sec / 3.0, 1)
        durations = [dur_unit, dur_unit, round(target_duration_sec - (dur_unit * 2), 1)]

        style = StyleBible(
            art_style="clean editorial photography, 8k resolution, documentary style",
            color_palette=["#0B0F19", "#38BDF8", "#10B981"],
            aspect_ratio="9:16",
        )

        scenes = [
            Scene(
                scene_id="scene_01_hook",
                role=BeatRole.HOOK,
                shots=[
                    VisualShot(
                        shot_id="sh_f1_hook",
                        duration_sec=durations[0],
                        action_prompt_en=f"editorial cinematic macro view representing {fact.topic}",
                        framing="medium close-up",
                        lighting="studio softbox lighting",
                        camera_move=CameraMove.PUSH_IN,
                        preferred_tier=RenderTier.STOCK,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text=fact.hook_question,
                    music_intensity=0.5,
                ),
            ),
            Scene(
                scene_id="scene_02_body",
                role=BeatRole.INCIDENT,
                shots=[
                    VisualShot(
                        shot_id="sh_f2_body",
                        duration_sec=durations[1],
                        action_prompt_en=f"archival footage and detailed breakdown of {fact.topic}",
                        framing="wide shot",
                        lighting="natural documentary lighting",
                        camera_move=CameraMove.STATIC,
                        preferred_tier=RenderTier.STOCK,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text=f"{fact.body_segment_1} {fact.body_segment_2}",
                    music_intensity=0.6,
                ),
            ),
            Scene(
                scene_id="scene_03_payoff",
                role=BeatRole.CLIMAX,
                shots=[
                    VisualShot(
                        shot_id="sh_f3_cta",
                        duration_sec=durations[2],
                        action_prompt_en=f"closing keyframe illustrating key discovery of {fact.topic}",
                        framing="medium shot",
                        lighting="bright studio rim light",
                        camera_move=CameraMove.PULL_OUT,
                        preferred_tier=RenderTier.STOCK,
                    )
                ],
                audio_plan=AudioTrackPlan(
                    voiceover_text=fact.cta,
                    music_intensity=0.4,
                ),
            ),
        ]

        evidence = [
            EvidenceReference(
                claim_id="fact_claim_01",
                source_title=fact.source_note,
            )
        ]

        return Storyboard(
            mode=ResolvedContentMode.FACTUAL_CURIOSITY,
            title=f"Curiosidad: {fact.topic}",
            target_duration_sec=target_duration_sec,
            style_bible=style,
            music_mood="documentary_lofi_ambient",
            characters=[],
            scenes=scenes,
            evidence_references=evidence,
        )

    def _call_gemini_storyboard(self, prompt: str, target_duration_sec: float) -> Storyboard:
        """Call Gemini to generate a structured Storyboard obeying all schema constraints."""
        from google import genai

        client = genai.Client(api_key=self.api_key)
        system_instruction = (
            "You are an elite short-form cinematic director. "
            "Given a user story brief, decompose it into a dramatic 6-beat vertical 9:16 Storyboard. "
            "Strictly follow this structure:\n"
            "1. Beat 1 (HOOK): Initial visual intrigue and world establishment.\n"
            "2. Beat 2 (INCIDENT): Physical contact with artifact or danger.\n"
            "3. Beat 3 (TURNING_POINT): Sudden atmospheric shift, mutation, or revelation.\n"
            "4. Beat 4 (ESCALATION): Threat rises, enemies/monsters emerge on horizon.\n"
            "5. Beat 5 (CLIMAX): High-speed physical combat, defensive strike, explosive action.\n"
            "6. Beat 6 (CLIFFHANGER): Tense unresolved standoff.\n"
            "RULES:\n"
            "- Every shot must have duration_sec between 2.5 and 5.0.\n"
            "- Sum of shot durations MUST EQUAL target_duration_sec.\n"
            "- PROHIBITED: Any documentary phrasing ('¿Sabías que...', 'los expertos', etc.).\n"
            "- Output MUST be pure JSON conforming to the Storyboard schema."
        )

        user_content = (
            f"Story Brief: {prompt}\n"
            f"Target Duration: {target_duration_sec} seconds.\n"
            f"Generate the complete Storyboard JSON."
        )

        response = client.models.generate_content(
            model=self.model,
            contents=f"{system_instruction}\n\n{user_content}",
        )
        data = json.loads(response.text.strip().removeprefix("```json").removesuffix("```").strip())
        return Storyboard(**data)

"""Unit tests for Canonical Storyboard Pydantic v2 Contracts."""

import pytest
from pydantic import ValidationError

from engine.creative.modes import ResolvedContentMode
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


@pytest.fixture
def sample_character():
    return CharacterAnchor(
        character_id="char_warrior_01",
        visual_anchor="a 19yo male warrior with messy dark hair, a small scar over left eyebrow, and dark worn leather tunic",
    )


@pytest.fixture
def sample_style():
    return StyleBible(
        art_style="dark fantasy anime, high contrast cel-shading",
        color_palette=["#07090E", "#7C3AED", "#06B6D4"],
    )


def test_visual_shot_prompt_composition(sample_character, sample_style):
    """Verify compose_full_prompt stitches style, character anchor, and shot action cleanly."""
    shot = VisualShot(
        shot_id="shot_01",
        duration_sec=3.5,
        action_prompt_en="close-up of hands uncovering an ancient glowing sword buried beneath mossy roots",
        framing="extreme close-up",
        lighting="dim mystical forest, glowing blue runes",
        camera_move=CameraMove.PUSH_IN,
        characters_present=["char_warrior_01"],
    )

    full_prompt = shot.compose_full_prompt(sample_style, [sample_character])
    assert "close-up of hands uncovering" in full_prompt
    assert "messy dark hair" in full_prompt
    assert "dark fantasy anime" in full_prompt
    assert "extreme close-up" in full_prompt


def test_scene_duration_is_sum_of_shots():
    """Verify Scene.duration_sec dynamically sums atomic shot durations."""
    shot1 = VisualShot(
        shot_id="s1_sh1",
        duration_sec=3.0,
        action_prompt_en="wide shot of gloomy lost forest with ancient trees",
    )
    shot2 = VisualShot(
        shot_id="s1_sh2",
        duration_sec=2.5,
        action_prompt_en="protagonist discovers the sword in the ground",
    )

    scene = Scene(
        scene_id="scene_01",
        role=BeatRole.HOOK,
        shots=[shot1, shot2],
        audio_plan=AudioTrackPlan(
            voiceover_text="En lo profundo del bosque, un secreto milenario yacía enterrado.",
            sfx_cues=[SfxCue(sound_tag="forest_wind", at_sec=1.0)],
        ),
    )

    assert scene.duration_sec == 5.5


def test_scene_rejects_sfx_cue_out_of_bounds():
    """Verify Scene raises ValidationError if an SfxCue occurs after the Scene finishes."""
    shot = VisualShot(
        shot_id="s1_sh1",
        duration_sec=3.0,
        action_prompt_en="close-up of hands pulling the sword",
    )
    with pytest.raises(ValidationError, match="exceeds Scene"):
        Scene(
            scene_id="scene_01",
            role=BeatRole.HOOK,
            shots=[shot],
            audio_plan=AudioTrackPlan(
                sfx_cues=[SfxCue(sound_tag="thunder_strike", at_sec=4.5)],  # Exceeds 3.0s!
            ),
        )


def test_storyboard_budget_validation(sample_character, sample_style):
    """Verify Storyboard enforces ±15% duration tolerance against target_duration_sec."""
    # Target 10s, actual scenes sum to 5.0s -> out of tolerance!
    shot1 = VisualShot(
        shot_id="s1_sh1",
        duration_sec=5.0,
        action_prompt_en="a lone warrior standing in the dark misty forest",
    )
    shot2 = VisualShot(
        shot_id="s2_sh1",
        duration_sec=5.0,
        action_prompt_en="warrior takes the cursed sword from the roots",
    )
    shot3 = VisualShot(
        shot_id="s3_sh1",
        duration_sec=5.0,
        action_prompt_en="sky turns dark with lightning as creatures emerge",
    )
    scene = Scene(
        scene_id="sc_01",
        role=BeatRole.HOOK,
        shots=[shot1],
        audio_plan=AudioTrackPlan(),
    )
    # Minimum 3 scenes required
    scene2 = Scene(scene_id="sc_02", role=BeatRole.INCIDENT, shots=[shot2], audio_plan=AudioTrackPlan())
    scene3 = Scene(scene_id="sc_03", role=BeatRole.CLIMAX, shots=[shot3], audio_plan=AudioTrackPlan())

    # Total duration = 15.0s. If target is 30.0s -> Error!
    with pytest.raises(ValidationError, match="fuera del presupuesto objetivo"):
        Storyboard(
            mode=ResolvedContentMode.NARRATIVE_FICTION,
            title="The Cursed Sword",
            target_duration_sec=30.0,
            style_bible=sample_style,
            characters=[sample_character],
            scenes=[scene, scene2, scene3],
        )

    # Valid storyboard when target is 15.0s
    sb = Storyboard(
        mode=ResolvedContentMode.NARRATIVE_FICTION,
        title="The Cursed Sword",
        target_duration_sec=15.0,
        style_bible=sample_style,
        characters=[sample_character],
        scenes=[scene, scene2, scene3],
    )
    assert sb.total_physical_duration == 15.0


def test_storyboard_duplicate_id_detection(sample_style):
    """Verify Storyboard rejects duplicate scene or shot IDs."""
    shot = VisualShot(
        shot_id="duplicate_shot",
        duration_sec=3.0,
        action_prompt_en="warrior takes the sword",
    )
    sc1 = Scene(scene_id="sc_01", role=BeatRole.HOOK, shots=[shot], audio_plan=AudioTrackPlan())
    sc2 = Scene(scene_id="sc_02", role=BeatRole.INCIDENT, shots=[shot], audio_plan=AudioTrackPlan())
    sc3 = Scene(scene_id="sc_03", role=BeatRole.CLIMAX, shots=[shot], audio_plan=AudioTrackPlan())

    with pytest.raises(ValidationError, match="Identificador de toma duplicado"):
        Storyboard(
            mode=ResolvedContentMode.NARRATIVE_FICTION,
            title="Duplicate Test",
            target_duration_sec=9.0,
            style_bible=sample_style,
            scenes=[sc1, sc2, sc3],
        )


def test_storyboard_unknown_character_reference(sample_style):
    """Verify Storyboard rejects shots referencing characters not registered in Storyboard.characters."""
    shot = VisualShot(
        shot_id="sh_01",
        duration_sec=3.0,
        action_prompt_en="a shadowy creature emerges",
        characters_present=["unregistered_demon_king"],
    )
    sc1 = Scene(scene_id="sc_01", role=BeatRole.HOOK, shots=[shot], audio_plan=AudioTrackPlan())
    sc2 = Scene(scene_id="sc_02", role=BeatRole.INCIDENT, shots=[VisualShot(shot_id="sh_02", duration_sec=3.0, action_prompt_en="action prompt placeholder")], audio_plan=AudioTrackPlan())
    sc3 = Scene(scene_id="sc_03", role=BeatRole.CLIMAX, shots=[VisualShot(shot_id="sh_03", duration_sec=3.0, action_prompt_en="action prompt placeholder")], audio_plan=AudioTrackPlan())

    with pytest.raises(ValidationError, match="no está registrado"):
        Storyboard(
            mode=ResolvedContentMode.NARRATIVE_FICTION,
            title="Unknown Char Test",
            target_duration_sec=9.0,
            style_bible=sample_style,
            characters=[],
            scenes=[sc1, sc2, sc3],
        )

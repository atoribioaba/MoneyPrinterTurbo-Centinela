from app.models.cinematic_director import CinematicMood
from app.models.cinematic_infographics import CinematicInfographicsPlan
from app.models.sound_design import SoundDesignRequest, SoundCueType
from app.models.transition_director import TransitionDirectorPlan
from app.models.visual_story_graph import VisualStoryGraph, VisualStoryNode
from app.services.sound_design import build_sound_design

def fixture():
    nodes = [
        VisualStoryNode.model_construct(node_id="scene:1", scene_number=1, mood=CinematicMood.DISCOVERY, intensity=0.4),
        VisualStoryNode.model_construct(node_id="scene:2", scene_number=2, mood=CinematicMood.AWE, intensity=0.9),
    ]
    graph = VisualStoryGraph.model_construct(
        subject="Fixture", source_plan_context_hash="ctx", graph_hash="g",
        node_count=2, nodes=nodes,
    )
    info = CinematicInfographicsPlan.model_construct(
        source_plan_context_hash="ctx", scene_count=2, infographics_hash="i"
    )
    transitions = TransitionDirectorPlan.model_construct(
        source_plan_context_hash="ctx", source_story_graph_hash="g",
        transition_director_hash="t"
    )
    return SoundDesignRequest.model_construct(story_graph=graph, infographics=info, transitions=transitions)

def test_cues_have_no_assets_or_fake_licenses():
    result = build_sound_design(fixture())
    assert result.asset_count == 0
    assert all(cue.asset_selected is False for cue in result.cues)
    assert all(cue.license_status == "LICENCIA_NO_VERIFICADA" for cue in result.cues)
    assert all(cue.publication_eligible is False for cue in result.cues)

def test_no_diegetic_space_sound():
    result = build_sound_design(fixture())
    assert all(cue.diegetic_space_sound is False for cue in result.cues)

def test_climax_gets_one_restrained_accent():
    result = build_sound_design(fixture())
    accents = [cue for cue in result.cues if cue.cue_type == SoundCueType.CLIMAX_ACCENT]
    assert len(accents) == 1
    assert accents[0].scene_number == 2

def test_guardrails():
    result = build_sound_design(fixture())
    assert result.renders_audio is False
    assert result.generates_audio is False
    assert result.downloads_audio is False
    assert result.searches_audio is False
    assert result.auto_publication is False

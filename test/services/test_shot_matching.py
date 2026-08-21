from app.models.cinematic_director import CinematicMood
from app.models.color_science import ColorSciencePlan, ColorScienceScene, ColorScienceStatus
from app.models.shot_matching import ShotMatchingRequest, ShotMatchStatus
from app.models.shot_quality import ShotQualityPlan, ShotQualitySceneScore, ShotQualityStatus
from app.models.visual_story_graph import VisualStoryEdge, VisualStoryGraph, VisualStoryNode
from app.services.shot_matching import build_shot_matching

def fixture():
    n1 = VisualStoryNode.model_construct(node_id="scene:1", scene_number=1, placeholder=True, mood=CinematicMood.DISCOVERY)
    n2 = VisualStoryNode.model_construct(node_id="scene:2", scene_number=2, placeholder=True, mood=CinematicMood.AWE)
    edge = VisualStoryEdge.model_construct(edge_id="edge:1:2", source_scene_number=1, target_scene_number=2)
    graph = VisualStoryGraph.model_construct(
        subject="Fixture", source_plan_context_hash="ctx", graph_hash="g",
        edge_count=1, nodes=[n1,n2], edges=[edge],
    )
    q1 = ShotQualitySceneScore.model_construct(scene_number=1, status=ShotQualityStatus.NOT_SCORABLE)
    q2 = ShotQualitySceneScore.model_construct(scene_number=2, status=ShotQualityStatus.NOT_SCORABLE)
    quality = ShotQualityPlan.model_construct(
        source_plan_context_hash="ctx", source_story_graph_hash="g",
        quality_hash="q", scenes=[q1,q2],
    )
    c1 = ColorScienceScene.model_construct(scene_number=1, status=ColorScienceStatus.PLACEHOLDER_NOT_APPLICABLE)
    c2 = ColorScienceScene.model_construct(scene_number=2, status=ColorScienceStatus.PLACEHOLDER_NOT_APPLICABLE)
    color = ColorSciencePlan.model_construct(
        source_plan_context_hash="ctx", source_story_graph_hash="g",
        color_science_hash="c", scenes=[c1,c2],
    )
    return ShotMatchingRequest.model_construct(story_graph=graph, shot_quality=quality, color_science=color)

def test_placeholder_pair_noop():
    result = build_shot_matching(fixture())
    assert result.edge_count == 1
    assert result.placeholder_pair_count == 1
    assert result.edges[0].status == ShotMatchStatus.PLACEHOLDER_PAIR_NOT_APPLICABLE

def test_no_new_frame_analysis():
    result = build_shot_matching(fixture())
    assert result.analyzes_new_frames is False
    assert result.renders_video is False

def test_hash_deterministic():
    assert build_shot_matching(fixture()).shot_matching_hash == build_shot_matching(fixture()).shot_matching_hash

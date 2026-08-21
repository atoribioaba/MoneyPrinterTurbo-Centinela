from app.models.cinematic_director import CinematicMood
from app.models.color_science import ColorScienceRequest, ColorScienceStatus
from app.models.depth_parallax import DepthParallaxPlan, DepthParallaxScene, DepthParallaxStatus
from app.models.visual_story_graph import VisualStoryGraph, VisualStoryNode
from app.services.color_science import build_color_science

def fixture(placeholder=True):
    node = VisualStoryNode.model_construct(
        node_id="scene:1", scene_number=1, placeholder=placeholder,
        intensity=0.8, mood=CinematicMood.AWE,
    )
    graph = VisualStoryGraph.model_construct(
        subject="Fixture", source_plan_context_hash="ctx", graph_hash="g",
        version="visual-story-graph-v0.1", node_count=1, nodes=[node],
    )
    depth_scene = DepthParallaxScene.model_construct(scene_number=1)
    depth = DepthParallaxPlan.model_construct(
        source_plan_context_hash="ctx", source_story_graph_hash="g",
        depth_parallax_hash="d", scene_count=1, scenes=[depth_scene],
    )
    return ColorScienceRequest.model_construct(story_graph=graph, depth_parallax=depth)

def test_placeholder_noop():
    result = build_color_science(fixture(True))
    assert result.placeholder_count == 1
    assert result.scenes[0].status == ColorScienceStatus.PLACEHOLDER_NOT_APPLICABLE

def test_real_scene_has_conservative_plan():
    result = build_color_science(fixture(False))
    scene = result.scenes[0]
    assert scene.status == ColorScienceStatus.GRADE_PLAN_READY
    assert scene.preserve_astronomy_color is True
    assert scene.avoid_oversaturation is True
    assert scene.saturation_scale <= 1.0

def test_hash_deterministic():
    assert build_color_science(fixture()).color_science_hash == build_color_science(fixture()).color_science_hash

from app.models.astromedia import MediaType
from app.models.cinematic_director import CinematicMood
from app.models.depth_parallax import DepthMapHint, DepthParallaxRequest
from app.models.smart_ken_burns import KenBurnsScenePlan, KenBurnsSceneStatus, SmartKenBurnsPlan
from app.models.visual_story_graph import VisualStoryGraph, VisualStoryNode
from app.services.depth_parallax import build_depth_parallax

def fixture(placeholder=True, image=False, hint=False):
    node = VisualStoryNode.model_construct(
        node_id="scene:1", scene_number=1, placeholder=placeholder, intensity=0.5,
        mood=CinematicMood.DISCOVERY,
    )
    graph = VisualStoryGraph.model_construct(
        subject="Fixture", source_plan_context_hash="ctx", graph_hash="g",
        version="visual-story-graph-v0.1", node_count=1, nodes=[node],
    )
    scene = KenBurnsScenePlan.model_construct(
        scene_number=1, node_id="scene:1",
        selected_media_id="img-1" if image else None,
        media_type=MediaType.IMAGE if image else None,
        status=(
            KenBurnsSceneStatus.FIT_STATIC_HOLD
            if image else KenBurnsSceneStatus.PLACEHOLDER_NOT_APPLICABLE
        ),
        review_required=False,
    )
    ken = SmartKenBurnsPlan.model_construct(
        subject="Fixture", source_plan_context_hash="ctx",
        source_story_graph_hash="g", source_story_graph_version="visual-story-graph-v0.1",
        version="smart-ken-burns-v0.1", ken_burns_hash="k",
        scene_count=1, scenes=[scene],
    )
    hints = []
    if hint:
        hints = [DepthMapHint(scene_number=1, source_media_id="img-1", depth_map_path="C:/depth.png")]
    return DepthParallaxRequest.model_construct(story_graph=graph, ken_burns=ken, depth_maps=hints)

def test_placeholder_noop():
    result = build_depth_parallax(fixture())
    assert result.placeholder_count == 1
    assert result.runs_depth_model is False
    assert result.downloads_models is False

def test_image_requires_explicit_depth():
    result = build_depth_parallax(fixture(placeholder=False, image=True))
    assert result.depth_map_required_count == 1

def test_explicit_verified_depth_is_ready():
    result = build_depth_parallax(fixture(placeholder=False, image=True, hint=True))
    assert result.depth_map_ready_count == 1
    assert result.scenes[0].execution_ready is True
    assert result.scenes[0].max_parallax_shift_fraction <= 0.025

def test_hash_deterministic():
    a = build_depth_parallax(fixture())
    b = build_depth_parallax(fixture())
    assert a.depth_parallax_hash == b.depth_parallax_hash

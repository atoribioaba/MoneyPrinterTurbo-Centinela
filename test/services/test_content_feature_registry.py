from app.models.astronomy_director import AstronomyVideoPlan, ScenePlan
from app.models.content_feature_registry import (
    ContentBinding,
    ContentBindingStatus,
    ContentFeatureRegistryRequest,
)
from app.models.analytics_brain import AnalyticsPlatform
from app.models.visual_story_graph import VisualStoryGraph, VisualStoryNode
from app.services.content_feature_registry import build_content_feature_registry


def fixture(binding=None):
    scenes = [
        ScenePlan.model_construct(
            scene_number=1,
            duration_seconds=10,
            narration="abc",
            claims=[],
            ai_recreation_allowed=False,
            astronomy_objects=["Luna"],
        ),
        ScenePlan.model_construct(
            scene_number=2,
            duration_seconds=20,
            narration="defgh",
            claims=[],
            ai_recreation_allowed=True,
            astronomy_objects=["Luna", "Sol"],
        ),
    ]
    plan = AstronomyVideoPlan.model_construct(
        subject="Fixture",
        hook="Mira el cielo",
        context_hash="ctx",
        total_duration_seconds=30,
        scenes=scenes,
    )

    nodes = [
        VisualStoryNode.model_construct(
            node_id="n1",
            scene_number=1,
            intensity=0.2,
            placeholder=False,
        ),
        VisualStoryNode.model_construct(
            node_id="n2",
            scene_number=2,
            intensity=0.9,
            placeholder=False,
        ),
    ]
    graph = VisualStoryGraph.model_construct(
        source_plan_context_hash="ctx",
        graph_hash="graph",
        node_count=2,
        placeholder_count=0,
        climax_node_id="n2",
        nodes=nodes,
    )
    return ContentFeatureRegistryRequest.model_construct(
        plan=plan,
        story_graph=graph,
        binding=binding,
    )


def test_unbound_snapshot_waits():
    result = build_content_feature_registry(fixture())
    assert result.status == ContentBindingStatus.WAITING_FOR_CONTENT_BINDING
    assert result.bound_snapshot_count == 0


def test_bound_snapshot_keeps_platform_and_content_id():
    binding = ContentBinding(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id="video-1",
    )
    result = build_content_feature_registry(fixture(binding))
    snapshot = result.snapshots[0]
    assert result.status == ContentBindingStatus.BOUND_TO_CONTENT
    assert snapshot.platform == AnalyticsPlatform.YOUTUBE
    assert snapshot.content_id == "video-1"


def test_numeric_features_are_extracted():
    result = build_content_feature_registry(fixture())
    values = {item.feature_name: item.value for item in result.snapshots[0].features}
    assert values["TOTAL_DURATION_SECONDS"] == 30
    assert values["SCENE_COUNT"] == 2
    assert values["CLIMAX_INTENSITY"] == 0.9
    assert values["ASTRONOMY_OBJECT_DISTINCT_COUNT"] == 2


def test_does_not_store_creative_text():
    result = build_content_feature_registry(fixture())
    assert result.stores_creative_text is False
    serialized = result.model_dump_json()
    assert "Mira el cielo" not in serialized
    assert "defgh" not in serialized


def test_hash_is_deterministic():
    assert (
        build_content_feature_registry(fixture()).content_feature_registry_hash
        == build_content_feature_registry(fixture()).content_feature_registry_hash
    )

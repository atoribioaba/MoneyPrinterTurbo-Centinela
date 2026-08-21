from app.models.cinematic_director import TransitionIntent
from app.models.shot_matching import ShotMatchEdge, ShotMatchingPlan, ShotMatchStatus
from app.models.transition_director import TransitionDirectorRequest, TransitionStatus, TransitionType
from app.models.visual_story_graph import VisualStoryEdge, VisualStoryGraph
from app.services.transition_director import build_transition_director

def fixture():
    edge = VisualStoryEdge.model_construct(
        edge_id="edge:1:2", source_scene_number=1, target_scene_number=2,
        source_transition_intent=TransitionIntent.SOFT_CUT,
    )
    graph = VisualStoryGraph.model_construct(
        subject="Fixture", source_plan_context_hash="ctx", graph_hash="g",
        edge_count=1, edges=[edge],
    )
    match = ShotMatchEdge.model_construct(
        edge_id="edge:1:2", status=ShotMatchStatus.PLACEHOLDER_PAIR_NOT_APPLICABLE
    )
    matching = ShotMatchingPlan.model_construct(
        source_plan_context_hash="ctx", source_story_graph_hash="g",
        edge_count=1, edges=[match], shot_matching_hash="m",
    )
    return TransitionDirectorRequest.model_construct(story_graph=graph, shot_matching=matching)

def test_placeholder_transition_is_pending():
    result = build_transition_director(fixture())
    item = result.transitions[0]
    assert item.status == TransitionStatus.PLACEHOLDER_PENDING_MEDIA
    assert item.transition_type == TransitionType.SOFT_DISSOLVE
    assert item.execution_ready is False

def test_transition_is_restrained():
    result = build_transition_director(fixture())
    assert result.transitions[0].duration_seconds <= 0.40
    assert result.creates_flashy_transitions is False

def test_hash_deterministic():
    assert build_transition_director(fixture()).transition_director_hash == build_transition_director(fixture()).transition_director_hash

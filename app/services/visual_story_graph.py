from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from app.models.astronomy_director import NarrativeAct
from app.models.cinematic_director import CompositionIntent
from app.models.visual_story_graph import (
    VISUAL_STORY_GRAPH_VERSION,
    CompositionLinkType,
    NarrativeLinkType,
    StoryActSpan,
    StorySubjectThread,
    SubjectLinkType,
    VisualStoryEdge,
    VisualStoryGraph,
    VisualStoryGraphRequest,
    VisualStoryNode,
    VisualStoryStructuralChecks,
)


class VisualStoryGraphError(RuntimeError):
    pass


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).casefold().strip()


def _subject_key(value: str) -> str:
    folded = _fold(value)
    return " ".join(folded.split())


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest().upper()


def _unique_subjects(values) -> tuple[list[str], list[str]]:
    labels: list[str] = []
    keys: list[str] = []
    seen = set()

    for raw in values or []:
        label = str(raw or "").strip()
        key = _subject_key(label)
        if not label or not key or key in seen:
            continue
        seen.add(key)
        labels.append(label)
        keys.append(key)

    return labels, keys


def _validate_alignment(request: VisualStoryGraphRequest) -> None:
    plan = request.plan
    base = request.video_base
    direction = request.cinematic_direction

    if plan.context_hash != base.source_plan_context_hash:
        raise VisualStoryGraphError(
            "AstronomyVideoPlan context_hash does not match VideoBasePlan"
        )
    if plan.context_hash != direction.source_plan_context_hash:
        raise VisualStoryGraphError(
            "AstronomyVideoPlan context_hash does not match CinematicDirectionPlan"
        )
    if base.version != direction.source_video_base_version:
        raise VisualStoryGraphError(
            "VideoBasePlan version does not match CinematicDirectionPlan source"
        )
    if base.source_selector_version != direction.source_selector_version:
        raise VisualStoryGraphError(
            "selector version mismatch between F6 and F7"
        )

    if len(plan.scenes) != base.scene_count:
        raise VisualStoryGraphError("scene count mismatch between F3 and F6")
    if len(plan.scenes) != direction.scene_count:
        raise VisualStoryGraphError("scene count mismatch between F3 and F7")

    plan_numbers = [scene.scene_number for scene in plan.scenes]
    base_numbers = [scene.scene_number for scene in base.scenes]
    direction_numbers = [scene.scene_number for scene in direction.scenes]

    if len(plan_numbers) != len(set(plan_numbers)):
        raise VisualStoryGraphError("AstronomyVideoPlan has duplicate scene numbers")
    if len(base_numbers) != len(set(base_numbers)):
        raise VisualStoryGraphError("VideoBasePlan has duplicate scene numbers")
    if len(direction_numbers) != len(set(direction_numbers)):
        raise VisualStoryGraphError(
            "CinematicDirectionPlan has duplicate scene numbers"
        )
    if plan_numbers != base_numbers or plan_numbers != direction_numbers:
        raise VisualStoryGraphError(
            "scene order must be identical across F3, F6 and F7"
        )

    base_by_number = {scene.scene_number: scene for scene in base.scenes}
    direction_by_number = {
        scene.scene_number: scene for scene in direction.scenes
    }

    for source in plan.scenes:
        number = source.scene_number
        base_scene = base_by_number[number]
        direction_scene = direction_by_number[number]

        source_duration = float(source.duration_seconds)
        if abs(source_duration - float(base_scene.duration_seconds)) > 0.01:
            raise VisualStoryGraphError(
                f"duration mismatch F3/F6 at scene {number}"
            )
        if abs(source_duration - float(direction_scene.duration_seconds)) > 0.01:
            raise VisualStoryGraphError(
                f"duration mismatch F3/F7 at scene {number}"
            )
        if source.act != direction_scene.act:
            raise VisualStoryGraphError(
                f"act mismatch F3/F7 at scene {number}"
            )
        if bool(base_scene.placeholder) != bool(direction_scene.placeholder):
            raise VisualStoryGraphError(
                f"placeholder mismatch F6/F7 at scene {number}"
            )


def _narrative_link(source, target) -> NarrativeLinkType:
    if target.act == NarrativeAct.CLIMAX:
        return NarrativeLinkType.ENTER_CLIMAX
    if source.act == NarrativeAct.CLIMAX:
        return NarrativeLinkType.EXIT_CLIMAX
    if target.act == NarrativeAct.EPILOGUE:
        return NarrativeLinkType.ENTER_EPILOGUE
    if source.act == target.act:
        return NarrativeLinkType.CONTINUE_ACT
    return NarrativeLinkType.ACT_TRANSITION


def _subject_link(
    source_keys: set[str],
    target_keys: set[str],
) -> tuple[SubjectLinkType, list[str]]:
    if not source_keys and not target_keys:
        return SubjectLinkType.UNDEFINED, []

    shared = sorted(source_keys & target_keys)

    if shared and source_keys == target_keys:
        return SubjectLinkType.CONTINUE, shared
    if shared:
        return SubjectLinkType.PARTIAL_CONTINUITY, shared
    return SubjectLinkType.CHANGE, []


def _composition_link(
    source: CompositionIntent,
    target: CompositionIntent,
) -> CompositionLinkType:
    if source == target:
        return CompositionLinkType.HOLD

    contrast_pairs = {
        frozenset(
            {
                CompositionIntent.LAYERED_WIDE,
                CompositionIntent.SUBJECT_DOMINANT,
            }
        ),
        frozenset(
            {
                CompositionIntent.INFORMATIONAL_CLEAN,
                CompositionIntent.LAYERED_WIDE,
            }
        ),
        frozenset(
            {
                CompositionIntent.INFORMATIONAL_CLEAN,
                CompositionIntent.SUBJECT_DOMINANT,
            }
        ),
    }

    if frozenset({source, target}) in contrast_pairs:
        return CompositionLinkType.CONTRAST

    return CompositionLinkType.EVOLVE


def _edge_flags(
    *,
    source_node,
    target_node,
    narrative_link,
    subject_link,
) -> list[str]:
    result = []

    if source_node.placeholder:
        result.append("SOURCE_PLACEHOLDER")
    if target_node.placeholder:
        result.append("TARGET_PLACEHOLDER")
    if subject_link == SubjectLinkType.CHANGE:
        result.append("SUBJECT_THREAD_BREAK")
    if narrative_link == NarrativeLinkType.ENTER_CLIMAX:
        result.append("CLIMAX_ENTRY")
    if narrative_link == NarrativeLinkType.EXIT_CLIMAX:
        result.append("CLIMAX_RELEASE")
    if narrative_link == NarrativeLinkType.ENTER_EPILOGUE:
        result.append("EPILOGUE_ENTRY")

    return result


def _edge_future_hints(narrative_link, subject_link) -> list[str]:
    result = ["F21_TRANSITION_DIRECTOR_CONSUMER"]

    if subject_link in {
        SubjectLinkType.CONTINUE,
        SubjectLinkType.PARTIAL_CONTINUITY,
    }:
        result.append("F11_OBJECT_TRACKER_CONTINUITY_CONSUMER")
        result.append("F12_SMART_REFRAMING_CONTINUITY_CONSUMER")

    if narrative_link in {
        NarrativeLinkType.ENTER_CLIMAX,
        NarrativeLinkType.EXIT_CLIMAX,
    }:
        result.append("F20_SHOT_MATCHING_CLIMAX_CONSUMER")

    return result


def _build_subject_threads(nodes: list[VisualStoryNode]) -> list[StorySubjectThread]:
    labels: OrderedDict[str, str] = OrderedDict()
    scenes: dict[str, list[int]] = {}
    node_ids: dict[str, list[str]] = {}

    for node in nodes:
        for label, key in zip(node.astronomy_objects, node.subject_keys):
            labels.setdefault(key, label)
            scenes.setdefault(key, []).append(node.scene_number)
            node_ids.setdefault(key, []).append(node.node_id)

    return [
        StorySubjectThread(
            thread_id="subject:" + key,
            subject_key=key,
            display_label=labels[key],
            scene_numbers=scenes[key],
            node_ids=node_ids[key],
        )
        for key in sorted(labels)
    ]


def _build_act_spans(nodes: list[VisualStoryNode]) -> list[StoryActSpan]:
    spans: list[StoryActSpan] = []
    current_act = None
    current_nodes: list[VisualStoryNode] = []

    def flush():
        if not current_nodes:
            return
        spans.append(
            StoryActSpan(
                act=current_nodes[0].act,
                start_scene_number=current_nodes[0].scene_number,
                end_scene_number=current_nodes[-1].scene_number,
                scene_numbers=[node.scene_number for node in current_nodes],
                node_ids=[node.node_id for node in current_nodes],
                peak_intensity=max(node.intensity for node in current_nodes),
            )
        )

    for node in nodes:
        if current_act is None:
            current_act = node.act
        if node.act != current_act:
            flush()
            current_nodes = []
            current_act = node.act
        current_nodes.append(node)

    flush()
    return spans


class VisualStoryGraphBuilder:
    """F8: deterministic story/continuity graph.

    It transforms already validated F3/F6/F7 planning data into a graph.
    It never renders, searches assets, scores shot quality, tracks objects,
    invokes LLM/GPU workloads, applies effects, or publishes.
    """

    version = VISUAL_STORY_GRAPH_VERSION

    def build(self, request: VisualStoryGraphRequest) -> VisualStoryGraph:
        _validate_alignment(request)

        plan = request.plan
        base = request.video_base
        direction = request.cinematic_direction

        base_by_number = {scene.scene_number: scene for scene in base.scenes}
        direction_by_number = {
            scene.scene_number: scene for scene in direction.scenes
        }

        nodes: list[VisualStoryNode] = []

        for source_scene in plan.scenes:
            number = source_scene.scene_number
            base_scene = base_by_number[number]
            directed = direction_by_number[number]

            object_labels, subject_keys = _unique_subjects(
                source_scene.astronomy_objects
            )

            warnings = list(directed.warnings)
            if base_scene.placeholder and "F6_PLACEHOLDER_SOURCE" not in warnings:
                warnings.append("F6_PLACEHOLDER_SOURCE")

            nodes.append(
                VisualStoryNode(
                    node_id=f"scene:{number}",
                    scene_number=number,
                    act=source_scene.act,
                    duration_seconds=float(source_scene.duration_seconds),
                    narrative_role=directed.narrative_role,
                    pace=directed.pace,
                    intensity=directed.intensity,
                    mood=directed.mood,
                    composition_intent=directed.composition_intent,
                    motion_intent=directed.motion_intent,
                    transition_out_intent=directed.transition_out_intent,
                    visual_requirement=source_scene.visual_requirement,
                    astronomy_objects=object_labels,
                    subject_keys=subject_keys,
                    continuity_group=directed.continuity_group,
                    placeholder=base_scene.placeholder,
                    execution_ready=directed.execution_ready,
                    directives=list(directed.directives),
                    future_phase_hints=list(directed.future_phase_hints),
                    warnings=warnings,
                )
            )

        climax_node_id = f"scene:{direction.climax_scene_number}"

        edges: list[VisualStoryEdge] = []

        for index in range(len(nodes) - 1):
            source_node = nodes[index]
            target_node = nodes[index + 1]
            source_direction = direction_by_number[source_node.scene_number]

            narrative_link = _narrative_link(source_node, target_node)
            subject_link, shared = _subject_link(
                set(source_node.subject_keys),
                set(target_node.subject_keys),
            )
            composition_link = _composition_link(
                source_node.composition_intent,
                target_node.composition_intent,
            )

            edges.append(
                VisualStoryEdge(
                    edge_id=(
                        f"{source_node.node_id}->{target_node.node_id}"
                    ),
                    source_node_id=source_node.node_id,
                    target_node_id=target_node.node_id,
                    source_scene_number=source_node.scene_number,
                    target_scene_number=target_node.scene_number,
                    narrative_link=narrative_link,
                    subject_link=subject_link,
                    composition_link=composition_link,
                    shared_subject_keys=shared,
                    intensity_delta=round(
                        target_node.intensity - source_node.intensity,
                        3,
                    ),
                    source_transition_intent=(
                        source_node.transition_out_intent
                    ),
                    cut_motivation=source_direction.cut_motivation,
                    continuity_flags=_edge_flags(
                        source_node=source_node,
                        target_node=target_node,
                        narrative_link=narrative_link,
                        subject_link=subject_link,
                    ),
                    future_phase_hints=_edge_future_hints(
                        narrative_link,
                        subject_link,
                    ),
                )
            )

        subject_threads = _build_subject_threads(nodes)
        act_spans = _build_act_spans(nodes)
        node_ids = [node.node_id for node in nodes]

        sequential_chain = all(
            edge.source_node_id == node_ids[index]
            and edge.target_node_id == node_ids[index + 1]
            for index, edge in enumerate(edges)
        )

        climax_index = node_ids.index(climax_node_id)
        climax_connected = (
            len(nodes) == 1
            or (
                (climax_index == 0 or edges[climax_index - 1].target_node_id == climax_node_id)
                and (
                    climax_index == len(nodes) - 1
                    or edges[climax_index].source_node_id == climax_node_id
                )
            )
        )

        threads_valid = all(
            thread.scene_numbers
            == sorted(set(thread.scene_numbers))
            and len(thread.scene_numbers) == len(thread.node_ids)
            for thread in subject_threads
        )

        checks = VisualStoryStructuralChecks(
            source_alignment=True,
            sequential_chain=sequential_chain,
            entry_exit_valid=bool(nodes)
            and node_ids[0] == f"scene:{plan.scenes[0].scene_number}"
            and node_ids[-1] == f"scene:{plan.scenes[-1].scene_number}",
            climax_connected=climax_connected,
            placeholders_preserved=(
                sum(node.placeholder for node in nodes)
                == base.placeholder_count
                == direction.placeholder_count
            ),
            topological_order_valid=node_ids
            == [f"scene:{scene.scene_number}" for scene in plan.scenes],
            subject_threads_valid=threads_valid,
        )

        stable_payload = {
            "version": self.version,
            "subject": plan.subject,
            "source_plan_context_hash": plan.context_hash,
            "source_video_base_version": base.version,
            "source_selector_version": base.source_selector_version,
            "source_cinematic_director_version": direction.version,
            "source_cinematic_direction_hash": direction.direction_hash,
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
            "subject_threads": [
                thread.model_dump(mode="json") for thread in subject_threads
            ],
            "act_spans": [
                span.model_dump(mode="json") for span in act_spans
            ],
        }

        return VisualStoryGraph(
            subject=plan.subject,
            source_plan_context_hash=plan.context_hash,
            source_video_base_version=base.version,
            source_selector_version=base.source_selector_version,
            source_cinematic_director_version=direction.version,
            source_cinematic_direction_hash=direction.direction_hash,
            node_count=len(nodes),
            edge_count=len(edges),
            placeholder_count=sum(node.placeholder for node in nodes),
            entry_node_id=node_ids[0],
            climax_node_id=climax_node_id,
            exit_node_id=node_ids[-1],
            topological_order=node_ids,
            nodes=nodes,
            edges=edges,
            subject_threads=subject_threads,
            act_spans=act_spans,
            structural_checks=checks,
            graph_hash=_hash_json(stable_payload),
            generated_at_utc=datetime.now(timezone.utc),
        )

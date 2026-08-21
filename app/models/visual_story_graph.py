from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy_director import AstronomyVideoPlan, NarrativeAct
from app.models.cinematic_director import (
    CinematicDirectionPlan,
    CinematicMood,
    CinematicNarrativeRole,
    CinematicPace,
    CompositionIntent,
    MotionIntent,
    TransitionIntent,
)
from app.models.video_base import VideoBasePlan


VISUAL_STORY_GRAPH_VERSION = "visual-story-graph-v0.1"


class StrictStoryGraphModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class NarrativeLinkType(str, Enum):
    CONTINUE_ACT = "CONTINUE_ACT"
    ACT_TRANSITION = "ACT_TRANSITION"
    ENTER_CLIMAX = "ENTER_CLIMAX"
    EXIT_CLIMAX = "EXIT_CLIMAX"
    ENTER_EPILOGUE = "ENTER_EPILOGUE"


class SubjectLinkType(str, Enum):
    CONTINUE = "CONTINUE"
    PARTIAL_CONTINUITY = "PARTIAL_CONTINUITY"
    CHANGE = "CHANGE"
    UNDEFINED = "UNDEFINED"


class CompositionLinkType(str, Enum):
    HOLD = "HOLD"
    EVOLVE = "EVOLVE"
    CONTRAST = "CONTRAST"


class VisualStoryGraphRequest(StrictStoryGraphModel):
    plan: AstronomyVideoPlan
    video_base: VideoBasePlan
    cinematic_direction: CinematicDirectionPlan


class VisualStoryNode(StrictStoryGraphModel):
    node_id: str
    scene_number: int = Field(ge=1)
    act: NarrativeAct
    duration_seconds: float = Field(gt=0.0)

    narrative_role: CinematicNarrativeRole
    pace: CinematicPace
    intensity: float = Field(ge=0.0, le=1.0)
    mood: CinematicMood

    composition_intent: CompositionIntent
    motion_intent: MotionIntent
    transition_out_intent: TransitionIntent

    visual_requirement: str
    astronomy_objects: list[str] = Field(default_factory=list)
    subject_keys: list[str] = Field(default_factory=list)
    continuity_group: str

    placeholder: bool
    execution_ready: bool

    directives: list[str] = Field(default_factory=list)
    future_phase_hints: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class VisualStoryEdge(StrictStoryGraphModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    source_scene_number: int = Field(ge=1)
    target_scene_number: int = Field(ge=1)

    narrative_link: NarrativeLinkType
    subject_link: SubjectLinkType
    composition_link: CompositionLinkType

    shared_subject_keys: list[str] = Field(default_factory=list)
    intensity_delta: float
    source_transition_intent: TransitionIntent
    cut_motivation: str

    continuity_flags: list[str] = Field(default_factory=list)
    future_phase_hints: list[str] = Field(default_factory=list)


class StorySubjectThread(StrictStoryGraphModel):
    thread_id: str
    subject_key: str
    display_label: str
    scene_numbers: list[int]
    node_ids: list[str]

    @model_validator(mode="after")
    def validate_thread(self):
        if not self.scene_numbers:
            raise ValueError("subject thread cannot be empty")
        if len(self.scene_numbers) != len(self.node_ids):
            raise ValueError("subject thread scene/node length mismatch")
        if self.scene_numbers != sorted(set(self.scene_numbers)):
            raise ValueError("subject thread scene_numbers must be unique and sorted")
        return self


class StoryActSpan(StrictStoryGraphModel):
    act: NarrativeAct
    start_scene_number: int = Field(ge=1)
    end_scene_number: int = Field(ge=1)
    scene_numbers: list[int]
    node_ids: list[str]
    peak_intensity: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_span(self):
        if not self.scene_numbers:
            raise ValueError("act span cannot be empty")
        if self.start_scene_number != self.scene_numbers[0]:
            raise ValueError("act span start mismatch")
        if self.end_scene_number != self.scene_numbers[-1]:
            raise ValueError("act span end mismatch")
        if len(self.scene_numbers) != len(self.node_ids):
            raise ValueError("act span scene/node length mismatch")
        return self


class VisualStoryStructuralChecks(StrictStoryGraphModel):
    source_alignment: bool
    sequential_chain: bool
    entry_exit_valid: bool
    climax_connected: bool
    placeholders_preserved: bool
    topological_order_valid: bool
    subject_threads_valid: bool


class VisualStoryGraph(StrictStoryGraphModel):
    version: str = VISUAL_STORY_GRAPH_VERSION

    subject: str
    source_plan_context_hash: str
    source_video_base_version: str
    source_selector_version: str
    source_cinematic_director_version: str
    source_cinematic_direction_hash: str

    deterministic: bool = True
    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    searches_material: bool = False
    auto_publication: bool = False

    node_count: int = Field(ge=1)
    edge_count: int = Field(ge=0)
    placeholder_count: int = Field(ge=0)

    entry_node_id: str
    climax_node_id: str
    exit_node_id: str
    topological_order: list[str]

    nodes: list[VisualStoryNode]
    edges: list[VisualStoryEdge]
    subject_threads: list[StorySubjectThread]
    act_spans: list[StoryActSpan]

    structural_checks: VisualStoryStructuralChecks
    graph_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_graph_contract(self):
        if self.node_count != len(self.nodes):
            raise ValueError("node_count must equal nodes length")
        if self.edge_count != len(self.edges):
            raise ValueError("edge_count must equal edges length")
        if self.placeholder_count != sum(node.placeholder for node in self.nodes):
            raise ValueError("placeholder_count mismatch")

        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node_id values must be unique")
        if self.topological_order != node_ids:
            raise ValueError("topological_order must equal canonical node order")
        if self.entry_node_id != node_ids[0]:
            raise ValueError("entry_node_id mismatch")
        if self.exit_node_id != node_ids[-1]:
            raise ValueError("exit_node_id mismatch")
        if self.climax_node_id not in node_ids:
            raise ValueError("climax_node_id must exist")

        expected_edge_count = max(0, self.node_count - 1)
        if self.edge_count != expected_edge_count:
            raise ValueError("F8 V0.1 requires one sequential edge per adjacent pair")

        for index, edge in enumerate(self.edges):
            if edge.source_node_id != node_ids[index]:
                raise ValueError("edge source breaks sequential chain")
            if edge.target_node_id != node_ids[index + 1]:
                raise ValueError("edge target breaks sequential chain")

        checks = self.structural_checks
        if not all(
            (
                checks.source_alignment,
                checks.sequential_chain,
                checks.entry_exit_valid,
                checks.climax_connected,
                checks.placeholders_preserved,
                checks.topological_order_valid,
                checks.subject_threads_valid,
            )
        ):
            raise ValueError("all Visual Story Graph structural checks must pass")

        if (
            self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.searches_material
            or self.auto_publication
        ):
            raise ValueError("F8 V0.1 is deterministic planning-only")

        return self

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy import ScientificStatus
from app.models.astromedia import MediaType, Origin, Provider, Rights
from app.models.cinematic_director import MotionIntent
from app.models.smart_ken_burns import SmartKenBurnsPlan
from app.models.video_base import VideoBasePlan
from app.models.visual_story_graph import VisualStoryGraph


MASTER_IMAGE_I2V_VERSION = "master-image-i2v-v0.1"


class StrictI2VModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class I2VSceneStatus(str, Enum):
    MASTER_IMAGE_REQUIRED = "MASTER_IMAGE_REQUIRED"
    VIDEO_NOT_APPLICABLE = "VIDEO_NOT_APPLICABLE"
    F13_REVIEW_REQUIRED = "F13_REVIEW_REQUIRED"
    SOURCE_RIGHTS_BLOCKED = "SOURCE_RIGHTS_BLOCKED"
    AWAITING_AI_APPROVAL = "AWAITING_AI_APPROVAL"
    I2V_JOB_READY = "I2V_JOB_READY"


class I2VMotionProfile(str, Enum):
    LOCKED_MICRO_MOTION = "LOCKED_MICRO_MOTION"
    NATURAL_MICRO_MOTION = "NATURAL_MICRO_MOTION"
    VERY_SLOW_PUSH = "VERY_SLOW_PUSH"
    CONTROLLED_REVEAL = "CONTROLLED_REVEAL"
    GENTLE_PULL_BACK = "GENTLE_PULL_BACK"


class MasterImageDescriptor(StrictI2VModel):
    scene_number: int = Field(ge=1)
    media_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_fingerprint: str | None = None

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rotation_deg: int = 0

    provider: Provider
    rights_status: Rights
    publication_eligible: bool

    source_origin_hint: Origin

    @model_validator(mode="after")
    def validate_rights(self):
        if self.publication_eligible and self.rights_status not in {
            Rights.CONFIRMED_OWNED,
            Rights.VERIFIED_LICENSE,
        }:
            raise ValueError(
                "publication_eligible master requires verified rights"
            )
        return self


class I2VJobSpec(StrictI2VModel):
    scene_number: int = Field(ge=1)
    master_image: MasterImageDescriptor

    adapter: str = "WANGP_DEFERRED_TO_F15"
    generation_mode: str = "IMAGE_TO_VIDEO"
    model_id: str | None = None

    requested_duration_seconds: float = Field(gt=0.0)
    delivery_width: int = Field(gt=0)
    delivery_height: int = Field(gt=0)
    delivery_fps: int = Field(gt=0)

    motion_profile: I2VMotionProfile
    motion_intensity: float = Field(ge=0.0, le=1.0)

    positive_prompt: str = Field(min_length=1)
    negative_prompt: str = Field(min_length=1)
    preservation_rules: list[str] = Field(min_length=1)

    output_visual_origin: Origin = Origin.AI_GENERATED
    output_scientific_status: ScientificStatus = (
        ScientificStatus.RECREACION_VISUAL
    )
    disclosure_required: bool = True

    execution_authorized: bool
    requires_f15_backend: bool = True

    ken_burns_is_fallback: bool = True
    stack_ken_burns_with_i2v: bool = False

    @model_validator(mode="after")
    def validate_generated_output_contract(self):
        if self.output_visual_origin != Origin.AI_GENERATED:
            raise ValueError("I2V output must be marked AI_GENERATED")
        if (
            self.output_scientific_status
            != ScientificStatus.RECREACION_VISUAL
        ):
            raise ValueError(
                "I2V output must be marked RECREACION_VISUAL"
            )
        if not self.disclosure_required:
            raise ValueError("I2V output requires disclosure")
        if not self.requires_f15_backend:
            raise ValueError("F14 cannot execute backend directly")
        if not self.ken_burns_is_fallback:
            raise ValueError("F13 must remain the fallback motion route")
        if self.stack_ken_burns_with_i2v:
            raise ValueError("F13 and I2V motion must not be stacked")
        return self


class MasterImageI2VRequest(StrictI2VModel):
    video_base: VideoBasePlan
    story_graph: VisualStoryGraph
    ken_burns: SmartKenBurnsPlan

    approved_scene_numbers: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_approvals(self):
        if len(self.approved_scene_numbers) != len(
            set(self.approved_scene_numbers)
        ):
            raise ValueError("approved_scene_numbers must be unique")
        if any(value < 1 for value in self.approved_scene_numbers):
            raise ValueError("approved scene numbers must be >= 1")
        return self


class I2VScenePlan(StrictI2VModel):
    scene_number: int = Field(ge=1)
    node_id: str

    selected_media_id: str | None = None
    media_type: MediaType | None = None
    source_path: str | None = None

    motion_intent: MotionIntent
    status: I2VSceneStatus

    master_image: MasterImageDescriptor | None = None
    job: I2VJobSpec | None = None

    approval_required: bool
    approved: bool
    handoff_ready: bool
    review_required: bool

    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        job_statuses = {
            I2VSceneStatus.AWAITING_AI_APPROVAL,
            I2VSceneStatus.I2V_JOB_READY,
        }

        if self.status in job_statuses:
            if self.master_image is None or self.job is None:
                raise ValueError(
                    "I2V image candidate requires master image and job"
                )
        else:
            if self.job is not None:
                raise ValueError(
                    "non-I2V scene cannot contain an I2V job"
                )

        if self.status == I2VSceneStatus.AWAITING_AI_APPROVAL:
            if not self.approval_required or self.approved:
                raise ValueError("approval-pending scene contract mismatch")
            if self.handoff_ready:
                raise ValueError(
                    "approval-pending scene cannot be handoff-ready"
                )
            if self.job is None or self.job.execution_authorized:
                raise ValueError(
                    "approval-pending job cannot be authorized"
                )

        if self.status == I2VSceneStatus.I2V_JOB_READY:
            if not self.approval_required or not self.approved:
                raise ValueError("ready I2V job requires explicit approval")
            if not self.handoff_ready:
                raise ValueError("approved I2V job must be handoff-ready")
            if self.job is None or not self.job.execution_authorized:
                raise ValueError("ready I2V job must be authorized")

        if self.review_required and self.handoff_ready:
            raise ValueError(
                "review-required scene cannot be handoff-ready"
            )

        return self


class I2VStructuralChecks(StrictI2VModel):
    source_alignment: bool
    story_graph_hash_preserved: bool
    ken_burns_hash_preserved: bool
    material_identity_preserved: bool
    image_only_generation: bool
    rights_gate_enforced: bool
    explicit_ai_approval_enforced: bool
    generated_origin_labeled: bool
    scientific_recreation_labeled: bool
    ken_burns_fallback_preserved: bool
    no_motion_stacking: bool


class MasterImageI2VPlan(StrictI2VModel):
    version: str = MASTER_IMAGE_I2V_VERSION
    subject: str

    source_plan_context_hash: str
    source_video_base_version: str
    source_story_graph_version: str
    source_story_graph_hash: str
    source_ken_burns_version: str
    source_ken_burns_hash: str

    delivery_width: int
    delivery_height: int
    delivery_fps: int

    deterministic: bool = True
    planning_only: bool = True
    requires_f15_backend: bool = True
    target_backend_family: str = "WanGP"
    backend_contract: str = "WANGP_API_OR_HEADLESS_RESOLVED_IN_F15"
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    downloads_models: bool = False
    wangp_invocations: int = Field(default=0, ge=0)
    searches_material: bool = False
    changes_material_identity: bool = False
    best_moment_search_triggered: bool = False
    tracking_reexecuted: bool = False
    smartfocal_reexecuted: bool = False
    reframing_reexecuted: bool = False
    ken_burns_rendered: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    master_image_required_count: int = Field(ge=0)
    video_not_applicable_count: int = Field(ge=0)
    f13_review_required_count: int = Field(ge=0)
    rights_blocked_count: int = Field(ge=0)
    approval_pending_count: int = Field(ge=0)
    job_ready_count: int = Field(ge=0)
    job_spec_count: int = Field(ge=0)

    approved_scene_numbers: list[int] = Field(default_factory=list)

    scenes: list[I2VScenePlan]
    structural_checks: I2VStructuralChecks

    i2v_plan_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")

        mapping = {
            I2VSceneStatus.MASTER_IMAGE_REQUIRED:
                self.master_image_required_count,
            I2VSceneStatus.VIDEO_NOT_APPLICABLE:
                self.video_not_applicable_count,
            I2VSceneStatus.F13_REVIEW_REQUIRED:
                self.f13_review_required_count,
            I2VSceneStatus.SOURCE_RIGHTS_BLOCKED:
                self.rights_blocked_count,
            I2VSceneStatus.AWAITING_AI_APPROVAL:
                self.approval_pending_count,
            I2VSceneStatus.I2V_JOB_READY:
                self.job_ready_count,
        }

        for status, expected in mapping.items():
            actual = sum(scene.status == status for scene in self.scenes)
            if actual != expected:
                raise ValueError(f"{status.value} count mismatch")

        if sum(mapping.values()) != self.scene_count:
            raise ValueError("F14 status counts do not cover all scenes")

        actual_jobs = sum(scene.job is not None for scene in self.scenes)
        if self.job_spec_count != actual_jobs:
            raise ValueError("job_spec_count mismatch")

        ready_numbers = sorted(
            scene.scene_number
            for scene in self.scenes
            if scene.status == I2VSceneStatus.I2V_JOB_READY
        )
        if ready_numbers != sorted(self.approved_scene_numbers):
            # Approved video/placeholder/blocked scenes are forbidden earlier,
            # therefore plan approvals must equal ready jobs.
            raise ValueError(
                "approved_scene_numbers must equal ready I2V scenes"
            )

        checks = self.structural_checks
        if not all(
            (
                checks.source_alignment,
                checks.story_graph_hash_preserved,
                checks.ken_burns_hash_preserved,
                checks.material_identity_preserved,
                checks.image_only_generation,
                checks.rights_gate_enforced,
                checks.explicit_ai_approval_enforced,
                checks.generated_origin_labeled,
                checks.scientific_recreation_labeled,
                checks.ken_burns_fallback_preserved,
                checks.no_motion_stacking,
            )
        ):
            raise ValueError("all F14 structural checks must pass")

        if (
            not self.planning_only
            or not self.requires_f15_backend
            or self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.downloads_models
            or self.wangp_invocations != 0
            or self.searches_material
            or self.changes_material_identity
            or self.best_moment_search_triggered
            or self.tracking_reexecuted
            or self.smartfocal_reexecuted
            or self.reframing_reexecuted
            or self.ken_burns_rendered
            or self.auto_publication
        ):
            raise ValueError("F14 V0.1 guardrail violation")

        return self

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.astronomy import (
    ScientificStatus,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class MediaType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"


class Provider(str, Enum):
    OWN_MEDIA = "OWN_MEDIA"
    LOCAL_MEDIA = "LOCAL_MEDIA"
    NASA = "NASA"
    ESA = "ESA"
    WIKIMEDIA = "WIKIMEDIA"
    PEXELS = "PEXELS"
    PIXABAY = "PIXABAY"
    COVERR = "COVERR"
    AI_GENERATED = "AI_GENERATED"
    OTHER = "OTHER"


class Rights(str, Enum):
    CONFIRMED_OWNED = "CONFIRMED_OWNED"
    VERIFIED_LICENSE = "VERIFIED_LICENSE"
    UNVERIFIED = "UNVERIFIED"
    RESTRICTED = "RESTRICTED"


class Origin(str, Enum):
    REAL_OWN = "REAL_OWN"
    REAL_EXTERNAL = "REAL_EXTERNAL"
    AI_GENERATED = "AI_GENERATED"
    UNKNOWN = "UNKNOWN"


class Provenance(str, Enum):
    LOCAL_LIBRARY = "LOCAL_LIBRARY"
    MPT_TASK_PROVIDER = "MPT_TASK_PROVIDER"
    MPT_MATERIAL_INFO = "MPT_MATERIAL_INFO"
    MANUAL_METADATA = "MANUAL_METADATA"


class HashMode(str, Enum):
    NONE = "none"

    DUPLICATE_CANDIDATES = "duplicate_candidates"

    FULL = "full"


class Sidecar(StrictModel):
    title: str | None = None

    description: str = ""

    tags: list[str] = Field(default_factory=list)

    astronomy_objects: list[str] = Field(default_factory=list)

    ownership_confirmed: bool = False

    provider: Provider | None = None

    provider_asset_id: str | None = None

    author_name: str | None = None

    license_name: str | None = None

    license_url: str | None = None

    rights_status: Rights | None = None

    attribution: str | None = None

    attribution_required: bool = False

    source_url: str | None = None

    @model_validator(mode="after")
    def validate_rights(
        self,
    ):
        if self.rights_status == Rights.VERIFIED_LICENSE and not self.license_name:
            raise ValueError("VERIFIED_LICENSE requires license_name")

        if self.ownership_confirmed:
            object.__setattr__(
                self,
                "provider",
                Provider.OWN_MEDIA,
            )

            object.__setattr__(
                self,
                "rights_status",
                Rights.CONFIRMED_OWNED,
            )

        return self


class AstroMediaItem(StrictModel):
    media_id: str

    local_path: str
    filename: str

    media_type: MediaType

    width: int = 0
    height: int = 0
    rotation_deg: int = 0

    fps: float = 0.0
    duration_seconds: float = 0.0

    codec_name: str | None = None

    file_size_bytes: int = 0
    mtime_ns: int = 0

    provider: Provider = Provider.LOCAL_MEDIA

    provider_asset_id: str | None = None

    title: str = ""
    description: str = ""

    tags: list[str] = Field(default_factory=list)

    astronomy_objects: list[str] = Field(default_factory=list)

    author_name: str | None = None

    license_name: str | None = None
    license_url: str | None = None

    rights_status: Rights = Rights.UNVERIFIED

    attribution: str | None = None
    attribution_required: bool = False

    source_url: str | None = None
    search_term: str | None = None
    task_id: str | None = None

    visual_origin: Origin = Origin.UNKNOWN

    scientific_status: ScientificStatus = ScientificStatus.NO_VERIFICADO

    provenance_kind: Provenance = Provenance.LOCAL_LIBRARY

    metadata_source: str = "filename"

    content_sha256: str | None = None

    duplicate_of_media_id: str | None = None

    renderable: bool = True

    probe_error: str | None = None

    publication_eligible: bool = False

    active: bool = True

    sidecar_fingerprint: str | None = None

    indexed_at_utc: datetime

    @model_validator(mode="after")
    def enforce_contracts(
        self,
    ):
        eligible = self.rights_status in {
            Rights.CONFIRMED_OWNED,
            Rights.VERIFIED_LICENSE,
        }

        if self.rights_status == Rights.RESTRICTED:
            eligible = False

        object.__setattr__(
            self,
            "publication_eligible",
            eligible,
        )

        if (
            self.provider == Provider.AI_GENERATED
            or self.visual_origin == Origin.AI_GENERATED
        ):
            object.__setattr__(
                self,
                "visual_origin",
                Origin.AI_GENERATED,
            )

            object.__setattr__(
                self,
                "scientific_status",
                ScientificStatus.RECREACION_VISUAL,
            )

        return self


class IndexRequest(StrictModel):
    root: str = r"D:\ASTRONOMÍA\Medios"

    recursive: bool = True

    hash_mode: HashMode = HashMode.DUPLICATE_CANDIDATES

    import_task_artifacts: bool = True


class IndexReport(StrictModel):
    root: str

    scanned_files: int

    supported_media_files: int

    indexed_items: int

    reused_items: int

    duplicate_items: int

    imported_task_items: int

    sidecar_files_used: int

    non_renderable_items: int

    errors: list[str] = Field(default_factory=list)

    elapsed_seconds: float


class SearchRequest(StrictModel):
    query: str = ""

    astronomy_objects: list[str] = Field(default_factory=list)

    providers: list[Provider] = Field(default_factory=list)

    media_types: list[MediaType] = Field(default_factory=list)

    publication_eligible_only: bool = False

    renderable_only: bool = True

    include_duplicates: bool = False

    min_width: int = 0

    min_height: int = 0

    limit: int = Field(
        default=25,
        ge=1,
        le=200,
    )


class SearchResult(StrictModel):
    score: float

    reasons: list[str]

    item: AstroMediaItem


class OverrideRequest(StrictModel):
    scene_key: str = Field(min_length=1)

    media_id: str = Field(min_length=1)

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

PROJECT_MANIFEST_SCHEMA_VERSION = 1
ARTIFACT_REF_SCHEMA_VERSION = 1
RUNTIME_SNAPSHOT_SCHEMA_VERSION = 1

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STATUS_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "credential",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def validate_id(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not _ID_RE.fullmatch(normalized):
        raise ValueError(f"{name} contains unsafe characters")
    return normalized


def _validate_text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > limit:
        raise ValueError(f"{name} must contain 1..{limit} characters")
    return normalized


def _validate_timestamp(value: Any, name: str) -> str:
    normalized = _validate_text(value, name, 64)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return normalized


def _json_copy(value: Any, name: str, expected_type: type) -> Any:
    if not isinstance(value, expected_type):
        raise TypeError(f"{name} must be {expected_type.__name__}")
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be JSON-safe") from exc
    return copy.deepcopy(value)


def _assert_no_secret_keys(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if any(fragment in key_text for fragment in _SECRET_KEY_FRAGMENTS):
                raise ValueError(f"secret-like key is forbidden in RuntimeSnapshot: {path}.{key}")
            _assert_no_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_secret_keys(item, f"{path}[{index}]")


def _relative_path(value: Any) -> str:
    normalized = _validate_text(value, "relative_path", 1024).replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute():
        raise ValueError("relative_path must be relative")
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative_path is unsafe")
    if ":" in path.parts[0]:
        raise ValueError("relative_path must not contain a drive prefix")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    project_id: str
    artifact_type: str
    relative_path: str
    sha256: str
    size_bytes: int
    created_at: str
    producer: str
    schema_version: int = ARTIFACT_REF_SCHEMA_VERSION
    producer_version: str | None = None
    input_artifact_ids: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", validate_id(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "project_id", validate_id(self.project_id, "project_id"))
        object.__setattr__(
            self,
            "artifact_type",
            validate_id(self.artifact_type, "artifact_type"),
        )
        relative_path = _relative_path(self.relative_path)
        expected_prefix = f"projects/{self.project_id}/artifacts/"
        if not relative_path.startswith(expected_prefix):
            raise ValueError("relative_path must stay inside the owning project's artifacts directory")
        object.__setattr__(self, "relative_path", relative_path)

        sha = _validate_text(self.sha256, "sha256", 64).lower()
        if not _SHA256_RE.fullmatch(sha):
            raise ValueError("sha256 must contain exactly 64 hexadecimal characters")
        object.__setattr__(self, "sha256", sha)

        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise TypeError("size_bytes must be an integer")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")

        object.__setattr__(self, "created_at", _validate_timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "producer", _validate_text(self.producer, "producer", 256))

        if self.schema_version != ARTIFACT_REF_SCHEMA_VERSION:
            raise ValueError(f"unsupported ArtifactRef schema_version={self.schema_version}")

        if self.producer_version is not None:
            object.__setattr__(
                self,
                "producer_version",
                _validate_text(self.producer_version, "producer_version", 128),
            )

        inputs = tuple(validate_id(item, "input_artifact_id") for item in self.input_artifact_ids)
        if len(inputs) != len(set(inputs)):
            raise ValueError("input_artifact_ids must be unique")
        if self.artifact_id in inputs:
            raise ValueError("an artifact cannot depend on itself")
        object.__setattr__(self, "input_artifact_ids", inputs)
        object.__setattr__(self, "provenance", _json_copy(self.provenance, "provenance", dict))
        object.__setattr__(self, "metadata", _json_copy(self.metadata, "metadata", dict))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "project_id": self.project_id,
            "artifact_type": self.artifact_type,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "input_artifact_ids": list(self.input_artifact_ids),
            "provenance": copy.deepcopy(self.provenance),
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRef":
        if not isinstance(data, dict):
            raise TypeError("ArtifactRef payload must be a dict")
        return cls(
            artifact_id=data["artifact_id"],
            project_id=data["project_id"],
            artifact_type=data["artifact_type"],
            relative_path=data["relative_path"],
            sha256=data["sha256"],
            size_bytes=data["size_bytes"],
            created_at=data["created_at"],
            producer=data["producer"],
            schema_version=data.get("schema_version", ARTIFACT_REF_SCHEMA_VERSION),
            producer_version=data.get("producer_version"),
            input_artifact_ids=tuple(data.get("input_artifact_ids") or ()),
            provenance=data.get("provenance") or {},
            metadata=data.get("metadata") or {},
        )


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    snapshot_id: str
    created_at: str
    git_commit: str
    git_branch: str
    app_version: str
    python_version: str
    platform: str
    ffmpeg_path: str | None = None
    ffmpeg_version: str | None = None
    encoder: str | None = None
    llm: dict[str, Any] = field(default_factory=dict)
    tts: dict[str, Any] = field(default_factory=dict)
    media_providers: list[dict[str, Any]] = field(default_factory=list)
    render: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    schema_version: int = RUNTIME_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", validate_id(self.snapshot_id, "snapshot_id"))
        object.__setattr__(self, "created_at", _validate_timestamp(self.created_at, "created_at"))
        for name, limit in (
            ("git_commit", 128),
            ("git_branch", 256),
            ("app_version", 128),
            ("python_version", 128),
            ("platform", 512),
        ):
            object.__setattr__(self, name, _validate_text(getattr(self, name), name, limit))

        if self.schema_version != RUNTIME_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported RuntimeSnapshot schema_version={self.schema_version}"
            )

        for name in ("ffmpeg_path", "ffmpeg_version", "encoder"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _validate_text(value, name, 2048))

        for name in ("llm", "tts", "render", "environment"):
            value = _json_copy(getattr(self, name), name, dict)
            _assert_no_secret_keys(value, name)
            object.__setattr__(self, name, value)

        providers = _json_copy(self.media_providers, "media_providers", list)
        if not all(isinstance(item, dict) for item in providers):
            raise TypeError("media_providers must contain only dict items")
        _assert_no_secret_keys(providers, "media_providers")
        object.__setattr__(self, "media_providers", providers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "git_commit": self.git_commit,
            "git_branch": self.git_branch,
            "app_version": self.app_version,
            "python_version": self.python_version,
            "platform": self.platform,
            "ffmpeg_path": self.ffmpeg_path,
            "ffmpeg_version": self.ffmpeg_version,
            "encoder": self.encoder,
            "llm": copy.deepcopy(self.llm),
            "tts": copy.deepcopy(self.tts),
            "media_providers": copy.deepcopy(self.media_providers),
            "render": copy.deepcopy(self.render),
            "environment": copy.deepcopy(self.environment),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeSnapshot":
        if not isinstance(data, dict):
            raise TypeError("RuntimeSnapshot payload must be a dict")
        return cls(
            snapshot_id=data["snapshot_id"],
            created_at=data["created_at"],
            git_commit=data["git_commit"],
            git_branch=data["git_branch"],
            app_version=data["app_version"],
            python_version=data["python_version"],
            platform=data["platform"],
            ffmpeg_path=data.get("ffmpeg_path"),
            ffmpeg_version=data.get("ffmpeg_version"),
            encoder=data.get("encoder"),
            llm=data.get("llm") or {},
            tts=data.get("tts") or {},
            media_providers=data.get("media_providers") or [],
            render=data.get("render") or {},
            environment=data.get("environment") or {},
            schema_version=data.get("schema_version", RUNTIME_SNAPSHOT_SCHEMA_VERSION),
        )


@dataclass(slots=True)
class ProjectManifest:
    project_id: str
    title: str
    created_at: str
    updated_at: str
    status: str = "DRAFT"
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    latest_by_type: dict[str, str] = field(default_factory=dict)
    runtime_snapshot_artifact_id: str | None = None
    observation_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = PROJECT_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.project_id = validate_id(self.project_id, "project_id")
        self.title = _validate_text(self.title, "title", 512)
        self.created_at = _validate_timestamp(self.created_at, "created_at")
        self.updated_at = _validate_timestamp(self.updated_at, "updated_at")
        self.status = _validate_text(self.status, "status", 64).upper()
        if not _STATUS_RE.fullmatch(self.status):
            raise ValueError("status must be an uppercase symbolic state")
        if self.schema_version != PROJECT_MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ProjectManifest schema_version={self.schema_version}"
            )

        self.observation_context = _json_copy(
            self.observation_context,
            "observation_context",
            dict,
        )
        self.metadata = _json_copy(self.metadata, "metadata", dict)

        for artifact_id, ref in self.artifacts.items():
            if not isinstance(ref, ArtifactRef):
                raise TypeError("artifacts values must be ArtifactRef")
            if artifact_id != ref.artifact_id or ref.project_id != self.project_id:
                raise ValueError("artifact mapping contains a mismatched ArtifactRef")

        self._validate_dependency_graph()

        for artifact_type, artifact_id in self.latest_by_type.items():
            normalized_type = validate_id(artifact_type, "artifact_type")
            normalized_id = validate_id(artifact_id, "artifact_id")
            ref = self.artifacts.get(normalized_id)
            if ref is None or ref.artifact_type != normalized_type:
                raise ValueError("latest_by_type points to a missing or mismatched artifact")

        if self.runtime_snapshot_artifact_id is not None:
            snapshot_id = validate_id(
                self.runtime_snapshot_artifact_id,
                "runtime_snapshot_artifact_id",
            )
            ref = self.artifacts.get(snapshot_id)
            if ref is None or ref.artifact_type != "runtime_snapshot":
                raise ValueError(
                    "runtime_snapshot_artifact_id must reference a runtime_snapshot artifact"
                )

    def _validate_dependency_graph(self) -> None:
        for ref in self.artifacts.values():
            missing = [
                input_id
                for input_id in ref.input_artifact_ids
                if input_id not in self.artifacts
            ]
            if missing:
                raise ValueError(
                    f"artifact {ref.artifact_id} has missing input references: {missing}"
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(artifact_id: str) -> None:
            if artifact_id in visited:
                return
            if artifact_id in visiting:
                raise ValueError("artifact dependency graph contains a cycle")
            visiting.add(artifact_id)
            for input_id in self.artifacts[artifact_id].input_artifact_ids:
                visit(input_id)
            visiting.remove(artifact_id)
            visited.add(artifact_id)

        for artifact_id in self.artifacts:
            visit(artifact_id)

    @classmethod
    def new(
        cls,
        title: str,
        *,
        project_id: str | None = None,
        observation_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ProjectManifest":
        now = utc_now_iso()
        return cls(
            project_id=uuid4().hex if project_id is None else project_id,
            title=title,
            created_at=now,
            updated_at=now,
            observation_context=observation_context or {},
            metadata=metadata or {},
        )

    def add_artifact(self, ref: ArtifactRef) -> None:
        if ref.project_id != self.project_id:
            raise ValueError("artifact belongs to another project")
        if ref.artifact_id in self.artifacts:
            raise ValueError("artifact_id is already registered")

        missing = [
            artifact_id
            for artifact_id in ref.input_artifact_ids
            if artifact_id not in self.artifacts
        ]
        if missing:
            raise ValueError(f"artifact has missing input references: {missing}")

        self.artifacts[ref.artifact_id] = ref
        self.latest_by_type[ref.artifact_type] = ref.artifact_id
        self.updated_at = utc_now_iso()

    def set_runtime_snapshot(self, artifact_id: str) -> None:
        artifact_id = validate_id(artifact_id, "artifact_id")
        ref = self.artifacts.get(artifact_id)
        if ref is None or ref.artifact_type != "runtime_snapshot":
            raise ValueError("runtime snapshot must reference a runtime_snapshot artifact")
        self.runtime_snapshot_artifact_id = artifact_id
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "runtime_snapshot_artifact_id": self.runtime_snapshot_artifact_id,
            "observation_context": copy.deepcopy(self.observation_context),
            "metadata": copy.deepcopy(self.metadata),
            "latest_by_type": dict(sorted(self.latest_by_type.items())),
            "artifacts": {
                artifact_id: self.artifacts[artifact_id].to_dict()
                for artifact_id in sorted(self.artifacts)
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectManifest":
        if not isinstance(data, dict):
            raise TypeError("ProjectManifest payload must be a dict")
        raw_artifacts = data.get("artifacts") or {}
        if not isinstance(raw_artifacts, dict):
            raise TypeError("artifacts must be a dict")
        return cls(
            project_id=data["project_id"],
            title=data["title"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            status=data.get("status", "DRAFT"),
            artifacts={
                artifact_id: ArtifactRef.from_dict(payload)
                for artifact_id, payload in raw_artifacts.items()
            },
            latest_by_type=data.get("latest_by_type") or {},
            runtime_snapshot_artifact_id=data.get("runtime_snapshot_artifact_id"),
            observation_context=data.get("observation_context") or {},
            metadata=data.get("metadata") or {},
            schema_version=data.get("schema_version", PROJECT_MANIFEST_SCHEMA_VERSION),
        )

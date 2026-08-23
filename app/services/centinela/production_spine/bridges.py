from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import StageArtifact, StageResult


class LegacyArtifactIngestAdapter:
    """Explicit bridge for immutable F3-F58 files into the R1 artifact store.

    The adapter never invents content and never deletes or moves the legacy source.
    Payload format: {"files": {"artifact_type": "absolute/or/relative/path"}}.
    """

    def __init__(self, *, required_types: tuple[str, ...]) -> None:
        self.required_types = tuple(required_types)

    def __call__(self, context: Any, payload: dict[str, Any]) -> StageResult:
        files = payload.get("files")
        if not isinstance(files, dict):
            return StageResult.needs_input("legacy artifact file mapping is required")

        missing = [item for item in self.required_types if not files.get(item)]
        if missing:
            return StageResult.needs_input(
                "required legacy artifacts are missing",
                details={"missing_types": missing},
            )

        artifacts: list[StageArtifact] = []
        for artifact_type, raw_path in sorted(files.items()):
            path = Path(str(raw_path))
            if not path.is_file():
                return StageResult.needs_input(
                    f"legacy artifact file does not exist: {path}",
                    details={"artifact_type": artifact_type},
                )
            artifacts.append(
                StageArtifact(
                    artifact_type=str(artifact_type),
                    source_path=str(path),
                    provenance={"legacy_bridge": True},
                )
            )
        return StageResult.complete(*artifacts, message="legacy artifacts ingested")


class PydanticServiceAdapter:
    """Small opt-in bridge from an existing strict request model/service to a JSON artifact."""

    def __init__(
        self,
        *,
        request_model: Any,
        service: Callable[[Any], Any],
        artifact_type: str,
    ) -> None:
        self.request_model = request_model
        self.service = service
        self.artifact_type = artifact_type

    def __call__(self, context: Any, payload: dict[str, Any]) -> StageResult:
        raw = payload.get("request")
        if not isinstance(raw, dict):
            return StageResult.needs_input("service request payload is required")
        request = self.request_model.model_validate(raw)
        result = self.service(request)
        if hasattr(result, "model_dump"):
            serialized = result.model_dump(mode="json")
        elif isinstance(result, dict):
            serialized = result
        else:
            raise TypeError("service result must be a Pydantic model or dict")
        return StageResult.complete(
            StageArtifact(
                artifact_type=self.artifact_type,
                payload=serialized,
                provenance={"existing_service_bridge": True},
            )
        )

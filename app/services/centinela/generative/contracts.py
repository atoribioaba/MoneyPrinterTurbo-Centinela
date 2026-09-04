"""Provider-neutral contracts for scene-based generative visual material."""

from dataclasses import dataclass
from enum import Enum
import math
import re


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_ALLOWED_ASPECT_RATIOS = frozenset({"9:16", "16:9", "1:1"})


class VisualGenerationMode(str, Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_VIDEO = "image_to_video"
    TEXT_TO_VIDEO = "text_to_video"


class GenerationQuality(str, Enum):
    PREVIEW = "preview"
    STANDARD = "standard"
    MASTER = "master"


class GeneratedMediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class ScientificVisualStatus(str, Enum):
    """Scientific label attached to a visual representation.

    AI-generated assets start as RECREACION_VISUAL. Fact Lock validates facts,
    not pixels, so an AI generation contract may never promote itself to
    HECHO_VERIFICADO.
    """

    HECHO_VERIFICADO = "HECHO_VERIFICADO"
    APROXIMACION_DIVULGATIVA = "APROXIMACION_DIVULGATIVA"
    HIPOTESIS = "HIPOTESIS"
    RECREACION_VISUAL = "RECREACION_VISUAL"
    INFERENCIA = "INFERENCIA"
    NO_VERIFICADO = "NO_VERIFICADO"


@dataclass(frozen=True, slots=True)
class VisualGenerationRequest:
    scene_id: str
    mode: VisualGenerationMode
    prompt: str
    quality: GenerationQuality = GenerationQuality.STANDARD
    aspect_ratio: str = "9:16"
    source_image: str | None = None
    negative_prompt: str = ""
    seed: int | None = None
    duration_seconds: float | None = None
    target_width: int | None = None
    target_height: int | None = None

    def __post_init__(self) -> None:
        scene_id = str(self.scene_id or "").strip()
        prompt = str(self.prompt or "").strip()
        source_image = (
            str(self.source_image).strip()
            if self.source_image is not None
            else None
        )
        negative_prompt = str(self.negative_prompt or "").strip()

        if not scene_id:
            raise ValueError("scene_id must not be empty")
        if not prompt:
            raise ValueError("prompt must not be empty")
        if self.aspect_ratio not in _ALLOWED_ASPECT_RATIOS:
            raise ValueError(f"unsupported aspect_ratio: {self.aspect_ratio!r}")

        if self.seed is not None and (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or self.seed < 0
        ):
            raise ValueError("seed must be a non-negative integer")

        dimensions = (self.target_width, self.target_height)
        if (dimensions[0] is None) != (dimensions[1] is None):
            raise ValueError("target_width and target_height must be set together")
        if any(
            value is not None
            and (isinstance(value, bool) or not isinstance(value, int) or value <= 0)
            for value in dimensions
        ):
            raise ValueError("target dimensions must be positive integers")

        if self.mode is VisualGenerationMode.IMAGE_TO_VIDEO and not source_image:
            raise ValueError("image_to_video requires source_image")

        if self.mode is VisualGenerationMode.TEXT_TO_IMAGE:
            if self.duration_seconds not in (None, 0):
                raise ValueError("text_to_image must not declare video duration")
        else:
            duration = self.duration_seconds
            if (
                duration is None
                or isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(float(duration))
                or float(duration) <= 0
            ):
                raise ValueError("video generation requires positive duration_seconds")

        object.__setattr__(self, "scene_id", scene_id)
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "source_image", source_image)
        object.__setattr__(self, "negative_prompt", negative_prompt)


@dataclass(frozen=True, slots=True)
class GeneratedVisualAsset:
    asset_id: str
    scene_id: str
    provider_id: str
    model_id: str
    media_type: GeneratedMediaType
    local_path: str
    sha256: str
    width: int
    height: int
    duration_seconds: float | None = None
    seed: int | None = None
    generation_seconds: float | None = None
    scientific_status: ScientificVisualStatus = (
        ScientificVisualStatus.RECREACION_VISUAL
    )

    def __post_init__(self) -> None:
        text_fields = {
            "asset_id": self.asset_id,
            "scene_id": self.scene_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "local_path": self.local_path,
        }
        for field_name, value in text_fields.items():
            normalized = str(value or "").strip()
            if not normalized:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, normalized)

        if not _SHA256_PATTERN.fullmatch(str(self.sha256 or "")):
            raise ValueError("sha256 must contain exactly 64 hexadecimal characters")
        object.__setattr__(self, "sha256", self.sha256.lower())

        for field_name, value in (("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")

        if self.seed is not None and (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or self.seed < 0
        ):
            raise ValueError("seed must be a non-negative integer")

        if self.generation_seconds is not None and (
            isinstance(self.generation_seconds, bool)
            or not isinstance(self.generation_seconds, (int, float))
            or not math.isfinite(float(self.generation_seconds))
            or float(self.generation_seconds) < 0
        ):
            raise ValueError("generation_seconds must be finite and non-negative")

        if self.media_type is GeneratedMediaType.IMAGE:
            if self.duration_seconds not in (None, 0):
                raise ValueError("generated image must not declare video duration")
        else:
            duration = self.duration_seconds
            if (
                duration is None
                or isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(float(duration))
                or float(duration) <= 0
            ):
                raise ValueError("generated video requires positive duration_seconds")

        if self.scientific_status is ScientificVisualStatus.HECHO_VERIFICADO:
            raise ValueError(
                "AI-generated visual assets cannot self-certify as HECHO_VERIFICADO"
            )


class SceneAssetIndex:
    """In-memory scene-to-generated-asset mapping with deterministic ordering."""

    def __init__(self) -> None:
        self._assets: dict[str, list[GeneratedVisualAsset]] = {}

    def register(self, asset: GeneratedVisualAsset) -> None:
        if not isinstance(asset, GeneratedVisualAsset):
            raise TypeError("asset must be GeneratedVisualAsset")
        self._assets.setdefault(asset.scene_id, []).append(asset)

    def for_scene(self, scene_id: str) -> tuple[GeneratedVisualAsset, ...]:
        normalized = str(scene_id or "").strip()
        if not normalized:
            raise ValueError("scene_id must not be empty")
        return tuple(self._assets.get(normalized, ()))

    def latest(
        self,
        scene_id: str,
        *,
        media_type: GeneratedMediaType | None = None,
    ) -> GeneratedVisualAsset | None:
        assets = self.for_scene(scene_id)
        if media_type is not None:
            assets = tuple(
                asset for asset in assets if asset.media_type is media_type
            )
        return assets[-1] if assets else None

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.models.astromedia import Sidecar
from app.services.centinela.writer_room import FactLock


SCIENTIFIC_VISUAL_VERSION = "factlock-scientific-visual-v0.1"
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
_LOGICAL_WIDTH = 270
_LOGICAL_HEIGHT = 480
_SCALE = 4


class ScientificVisualError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScientificVisualArtifact:
    fact_id: str
    image_path: Path
    sidecar_path: Path
    manifest_path: Path
    content_sha256: str
    width: int = OUTPUT_WIDTH
    height: int = OUTPUT_HEIGHT
    network_calls: int = 0
    ai_generated: bool = False
    factlock_only: bool = True


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return result or "fact"


def _stable_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _fact_by_id(fact_lock: FactLock, fact_id: str):
    for fact in fact_lock.facts:
        if fact.fact_id == fact_id:
            return fact
    raise ScientificVisualError(f"fact_id is not present in FactLock: {fact_id}")


def _numeric(value: Any, fact_id: str) -> float:
    if isinstance(value, bool):
        raise ScientificVisualError(f"numeric FactLock value required: {fact_id}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ScientificVisualError(
            f"numeric FactLock value required: {fact_id}"
        ) from exc
    if not math.isfinite(result):
        raise ScientificVisualError(f"finite FactLock value required: {fact_id}")
    return result


def _kind(fact_id: str) -> str:
    normalized = fact_id.casefold()
    if normalized in {
        "moon:angular_diameter_deg",
        "body:moon:angular_diameter_deg",
    }:
        return "angular_diameter"
    if normalized in {
        "body:moon:visual_magnitude",
        "moon:visual_magnitude",
    }:
        return "visual_magnitude"
    raise ScientificVisualError(
        "unsupported deterministic scientific visual fact_id: " + fact_id
    )


def _font():
    # Pillow's bundled default font avoids machine-specific system font paths.
    return ImageFont.load_default()


def _draw_header(draw: ImageDraw.ImageDraw, title: str, fact_id: str) -> None:
    font = _font()
    draw.text((18, 24), title, fill=(238, 241, 248), font=font)
    draw.text((18, 43), "FACTLOCK ONLY / DETERMINISTIC", fill=(174, 184, 203), font=font)
    draw.text((18, 448), fact_id, fill=(130, 140, 160), font=font)


def _render_angular(value: float) -> Image.Image:
    if value <= 0.0 or value > 10.0:
        raise ScientificVisualError("angular diameter must be in (0, 10] degrees")

    image = Image.new("RGB", (_LOGICAL_WIDTH, _LOGICAL_HEIGHT), (9, 12, 20))
    draw = ImageDraw.Draw(image)
    _draw_header(draw, "LUNAR ANGULAR DIAMETER", "moon:angular_diameter_deg")

    center_x, center_y = 135, 224
    radius = 72
    draw.ellipse(
        (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
        outline=(226, 231, 240),
        width=2,
    )
    draw.line((center_x - radius, center_y, center_x + radius, center_y), fill=(98, 188, 255), width=2)
    draw.line((center_x - radius, center_y - 5, center_x - radius, center_y + 5), fill=(98, 188, 255), width=2)
    draw.line((center_x + radius, center_y - 5, center_x + radius, center_y + 5), fill=(98, 188, 255), width=2)
    draw.text((91, 309), f"{value:.3f} deg", fill=(238, 241, 248), font=_font())
    draw.text((66, 332), "verified numeric FactLock value", fill=(174, 184, 203), font=_font())
    return image


def _render_magnitude(value: float) -> Image.Image:
    if value < -40.0 or value > 40.0:
        raise ScientificVisualError("visual magnitude must be in [-40, 40]")

    image = Image.new("RGB", (_LOGICAL_WIDTH, _LOGICAL_HEIGHT), (9, 12, 20))
    draw = ImageDraw.Draw(image)
    _draw_header(draw, "LUNAR VISUAL MAGNITUDE", "body:moon:visual_magnitude")

    x0, x1, y = 28, 242, 246
    minimum, maximum = -15.0, 15.0
    draw.line((x0, y, x1, y), fill=(226, 231, 240), width=2)
    for tick in (-15, -10, -5, 0, 5, 10, 15):
        x = round(x0 + (tick - minimum) / (maximum - minimum) * (x1 - x0))
        draw.line((x, y - 5, x, y + 5), fill=(174, 184, 203), width=1)
        draw.text((x - 7, y + 10), str(tick), fill=(174, 184, 203), font=_font())

    clamped = min(max(value, minimum), maximum)
    marker_x = round(x0 + (clamped - minimum) / (maximum - minimum) * (x1 - x0))
    draw.line((marker_x, y - 34, marker_x, y + 34), fill=(255, 199, 95), width=3)
    draw.text((91, 316), f"m = {value:.2f}", fill=(238, 241, 248), font=_font())
    draw.text((65, 339), "lower magnitude = brighter", fill=(174, 184, 203), font=_font())
    return image


def _render(kind: str, value: float) -> Image.Image:
    if kind == "angular_diameter":
        logical = _render_angular(value)
    elif kind == "visual_magnitude":
        logical = _render_magnitude(value)
    else:  # pragma: no cover - guarded by _kind
        raise ScientificVisualError(f"unsupported visual kind: {kind}")

    try:
        return logical.resize(
            (OUTPUT_WIDTH, OUTPUT_HEIGHT),
            resample=Image.Resampling.NEAREST,
        )
    finally:
        logical.close()


def _metadata(kind: str, fact_id: str, value: float, unit: str | None):
    if kind == "angular_diameter":
        title = f"FactLock lunar angular diameter — {value:.3f} deg"
        tags = [
            "moon",
            "lunar",
            "angular diameter",
            "diameter",
            "angular",
            "geometry",
            "scientific diagram",
            "factlock",
        ]
    else:
        title = f"FactLock lunar visual magnitude — {value:.2f}"
        tags = [
            "moon",
            "lunar",
            "visual magnitude",
            "magnitude",
            "brightness",
            "comparative brightness",
            "scientific diagram",
            "factlock",
        ]

    unit_text = f" {unit}" if unit else ""
    description = (
        "Deterministic scientific diagram generated solely from FactLock; "
        f"fact_id={fact_id}; value={value}{unit_text}; "
        "no network; no generative AI."
    )
    return title, tags, description


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def render_factlock_scientific_visual(
    fact_lock: FactLock,
    fact_id: str,
    output_dir: str | Path,
) -> ScientificVisualArtifact:
    """Render one auditable 9:16 scientific diagram from an immutable FactLock fact.

    The function is deliberately local and deterministic: it performs no network
    calls, invokes no LLM/TTS/image model, and refuses fact IDs absent from the
    supplied FactLock.
    """

    if not isinstance(fact_lock, FactLock):
        raise TypeError("fact_lock must be FactLock")
    fact_id = str(fact_id or "").strip()
    if not fact_id:
        raise ScientificVisualError("fact_id is required")

    fact = _fact_by_id(fact_lock, fact_id)
    kind = _kind(fact_id)
    value = _numeric(fact.value, fact_id)

    stable = {
        "version": SCIENTIFIC_VISUAL_VERSION,
        "fact_lock_hash": fact_lock.context_hash,
        "fact_id": fact.fact_id,
        "value": _stable_value(fact.value),
        "unit": fact.unit,
        "scientific_status": fact.scientific_status.value,
        "kind": kind,
        "width": OUTPUT_WIDTH,
        "height": OUTPUT_HEIGHT,
    }
    stable_json = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    identity = hashlib.sha256(stable_json.encode("utf-8")).hexdigest()[:16]

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    image_path = root / f"scientific-{_slug(fact.fact_id)}-{identity}.png"
    sidecar_path = image_path.with_name(image_path.name + ".astromedia.json")
    manifest_path = image_path.with_name(image_path.name + ".factlock.json")

    image = _render(kind, value)
    try:
        image.save(image_path, format="PNG", optimize=False, compress_level=9)
    finally:
        image.close()

    content_sha256 = _sha256(image_path)
    title, tags, description = _metadata(kind, fact.fact_id, value, fact.unit)

    sidecar = Sidecar(
        title=title,
        description=description,
        tags=tags,
        astronomy_objects=["moon"],
        ownership_confirmed=True,
        provider_asset_id=f"factlock:{identity}",
        author_name="EL CENTINELA DEL UNIVERSO",
        attribution_required=False,
    )
    sidecar_path.write_text(
        json.dumps(
            sidecar.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    manifest = {
        **stable,
        "image_path": str(image_path),
        "content_sha256": content_sha256,
        "factlock_only": True,
        "network_calls": 0,
        "ai_generated": False,
        "publication_requires_human_review": True,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return ScientificVisualArtifact(
        fact_id=fact.fact_id,
        image_path=image_path,
        sidecar_path=sidecar_path,
        manifest_path=manifest_path,
        content_sha256=content_sha256,
    )

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.services.astromedia import AstroMediaCatalog

from .models import MediaRefreshDecision

DEFAULT_MEDIA_ROOT = Path(r"D:\\ASTRONOMÍA\\Medios")
_SUPPORTED_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts", ".m2ts",
    ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp",
})
_MAX_CHANGED_SAMPLES = 5


def _norm(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _sidecar_fingerprint(path: Path) -> str | None:
    rows: list[tuple[str, int, int]] = []
    for candidate in (
        path.with_name(path.name + ".astromedia.json"),
        path.with_name(path.stem + ".astromedia.json"),
    ):
        if candidate.is_file() and not candidate.is_symlink():
            stat = candidate.stat()
            rows.append((str(candidate.resolve()), stat.st_size, stat.st_mtime_ns))
    if not rows:
        return None
    raw = json.dumps(sorted(rows), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _iter_supported(root: Path):
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name
            for name in dirnames
            if not (current_path / name).is_symlink()
        ]
        for name in filenames:
            path = current_path / name
            if path.is_symlink() or path.suffix.casefold() not in _SUPPORTED_EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            yield path, stat


class MediaAutomationPolicy:
    """Cheap exact-stat preflight that decides whether R4 should re-index AstroMedia."""

    def __init__(
        self,
        catalog: AstroMediaCatalog,
        *,
        media_root: str | Path = DEFAULT_MEDIA_ROOT,
    ) -> None:
        self.catalog = catalog
        self.media_root = Path(media_root)

    def decide(self) -> MediaRefreshDecision:
        root = self.media_root
        active_items = list(self.catalog.list_items(True))
        active_count = len(active_items)

        if not root.is_dir() or root.is_symlink():
            return MediaRefreshDecision(
                refresh_catalog=False,
                reason="media_root_missing",
                root=str(root),
                root_exists=False,
                supported_file_count=0,
                catalog_root_item_count=0,
                active_catalog_item_count=active_count,
            )

        root = root.resolve()
        current: dict[str, tuple[Path, os.stat_result]] = {
            _norm(path): (path, stat)
            for path, stat in _iter_supported(root)
        }

        catalog_by_path: dict[str, Any] = {}
        for item in active_items:
            try:
                path = Path(item.local_path).resolve()
                path.relative_to(root)
            except (OSError, ValueError):
                continue
            catalog_by_path[_norm(path)] = item

        changed: list[str] = []
        reason = "up_to_date"

        current_keys = set(current)
        catalog_keys = set(catalog_by_path)

        new_keys = sorted(current_keys - catalog_keys)
        missing_keys = sorted(catalog_keys - current_keys)
        if new_keys:
            reason = "new_media"
            changed.extend(new_keys)
        if missing_keys:
            if reason == "up_to_date":
                reason = "removed_media"
            changed.extend(missing_keys)

        for key in sorted(current_keys & catalog_keys):
            path, stat = current[key]
            item = catalog_by_path[key]
            if (
                int(getattr(item, "file_size_bytes", -1)) != stat.st_size
                or int(getattr(item, "mtime_ns", -1)) != stat.st_mtime_ns
            ):
                if reason == "up_to_date":
                    reason = "media_changed"
                changed.append(key)
                continue
            if getattr(item, "sidecar_fingerprint", None) != _sidecar_fingerprint(path):
                if reason == "up_to_date":
                    reason = "sidecar_changed"
                changed.append(key)

        if not current and not catalog_by_path:
            reason = "empty_library"

        unique_changed = tuple(dict.fromkeys(changed))
        return MediaRefreshDecision(
            refresh_catalog=bool(unique_changed),
            reason=reason,
            root=str(root),
            root_exists=True,
            supported_file_count=len(current),
            catalog_root_item_count=len(catalog_by_path),
            active_catalog_item_count=active_count,
            changed_path_count=len(unique_changed),
            sample_changed_paths=tuple(unique_changed[:_MAX_CHANGED_SAMPLES]),
        )

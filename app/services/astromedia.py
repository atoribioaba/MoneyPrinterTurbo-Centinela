from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import unicodedata

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from urllib.parse import (
    urlsplit,
    urlunsplit,
)

from app.models.astronomy import (
    ScientificStatus,
)

from app.models.astromedia import (
    AstroMediaItem,
    HashMode,
    IndexReport,
    IndexRequest,
    MediaType,
    Origin,
    Provider,
    Provenance,
    Rights,
    SearchRequest,
    SearchResult,
    Sidecar,
)


MEDIA_ROOT = Path(r"D:\ASTRONOMÍA\Medios")

TASKS_ROOT = Path(__file__).resolve().parents[2] / "storage" / "tasks"

RUNTIME = Path(r"E:\IA\AstroMedia")

DB_PATH = RUNTIME / "catalog.sqlite3"

JSON_PATH = RUNTIME / "catalog.json"


VIDEO_EXTS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".m4v",
    ".mts",
    ".m2ts",
}

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
}


OBJECT_ALIASES = {
    "sun": {
        "sun",
        "sol",
        "solar",
    },
    "moon": {
        "moon",
        "luna",
        "lunar",
    },
    "mercury": {
        "mercury",
        "mercurio",
    },
    "venus": {
        "venus",
    },
    "mars": {
        "mars",
        "marte",
    },
    "jupiter": {
        "jupiter",
        "júpiter",
    },
    "saturn": {
        "saturn",
        "saturno",
    },
    "uranus": {
        "uranus",
        "urano",
    },
    "neptune": {
        "neptune",
        "neptuno",
    },
    "milky_way": {
        "milky way",
        "vía láctea",
        "via lactea",
    },
    "eclipse": {
        "eclipse",
    },
    "comet": {
        "comet",
        "cometa",
    },
    "meteor": {
        "meteor",
        "meteoro",
        "perseids",
        "perseidas",
    },
    "galaxy": {
        "galaxy",
        "galaxia",
    },
    "nebula": {
        "nebula",
        "nebulosa",
    },
    "aurora": {
        "aurora",
    },
    "sunset": {
        "sunset",
        "atardecer",
        "puesta de sol",
    },
    "sunrise": {
        "sunrise",
        "amanecer",
        "salida del sol",
    },
}


PROVIDER_MAP = {
    "own_media": Provider.OWN_MEDIA,
    "local": Provider.LOCAL_MEDIA,
    "local_media": Provider.LOCAL_MEDIA,
    "nasa": Provider.NASA,
    "esa": Provider.ESA,
    "wikimedia": Provider.WIKIMEDIA,
    "wikimedia_commons": Provider.WIKIMEDIA,
    "pexels": Provider.PEXELS,
    "pixabay": Provider.PIXABAY,
    "coverr": Provider.COVERR,
    "ai": Provider.AI_GENERATED,
    "ai_generated": Provider.AI_GENERATED,
}


class AstroMediaError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _fold(
    value,
):
    normalized = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).casefold()


def _tokens(
    value,
):
    return set(
        re.findall(
            r"[a-z0-9_]+",
            _fold(value),
        )
    )


def _provider(
    value,
):
    key = (
        str(value or "")
        .strip()
        .casefold()
        .replace(
            "-",
            "_",
        )
        .replace(
            " ",
            "_",
        )
    )

    return PROVIDER_MAP.get(
        key,
        Provider.OTHER,
    )


def _safe_url(
    value,
):
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        return None

    try:
        parsed = urlsplit(value.strip())

    except ValueError:
        return None

    if (
        parsed.scheme
        not in {
            "http",
            "https",
        }
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            "",
        )
    )


def _media_type(
    path,
):
    suffix = path.suffix.casefold()

    if suffix in VIDEO_EXTS:
        return MediaType.VIDEO

    if suffix in IMAGE_EXTS:
        return MediaType.IMAGE

    return None


def _media_id(
    path,
):
    normalized = os.path.normcase(str(path.resolve()))

    return "media_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _sha256(
    path,
):
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(
            lambda: stream.read(8 * 1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def _infer_objects(
    *values,
):
    text = _fold(" ".join(str(value or "") for value in values))

    return [
        canonical
        for (
            canonical,
            aliases,
        ) in OBJECT_ALIASES.items()
        if any(_fold(alias) in text for alias in aliases)
    ]


def _sidecar_paths(
    path,
):
    return [
        path.with_name(path.name + ".astromedia.json"),
        path.with_name(path.stem + ".astromedia.json"),
    ]


def _sidecar_fingerprint(
    path,
):
    rows = []

    for candidate in _sidecar_paths(path):
        if candidate.is_file():
            stat = candidate.stat()

            rows.append(
                (
                    str(candidate.resolve()),
                    stat.st_size,
                    stat.st_mtime_ns,
                )
            )

    if not rows:
        return None

    raw = json.dumps(
        sorted(rows),
        separators=(
            ",",
            ":",
        ),
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest().upper()


def _load_sidecar(
    path,
):
    for candidate in _sidecar_paths(path):
        if candidate.is_file():
            return (
                Sidecar.model_validate_json(candidate.read_text(encoding="utf-8")),
                str(candidate),
            )

    return (
        None,
        None,
    )


def _fraction(
    value,
):
    try:
        text = str(value or "0")

        if "/" in text:
            numerator, denominator = text.split(
                "/",
                1,
            )

            denominator_value = float(denominator)

            if not denominator_value:
                return 0.0

            return float(numerator) / denominator_value

        return float(text)

    except (
        TypeError,
        ValueError,
        ZeroDivisionError,
    ):
        return 0.0


def _ffprobe(
    path,
    media_type,
):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode:
        raise AstroMediaError((result.stderr or "ffprobe failed")[:600])

    data = json.loads(result.stdout or "{}")

    stream = next(
        (
            item
            for item in data.get(
                "streams",
                [],
            )
            if item.get("codec_type") == "video"
        ),
        None,
    )

    if stream is None:
        raise AstroMediaError("No visual stream found")

    width = int(stream.get("width") or 0)

    height = int(stream.get("height") or 0)

    rotation = 0

    try:
        rotation = int(float((stream.get("tags") or {}).get("rotate") or 0)) % 360

    except (
        TypeError,
        ValueError,
    ):
        rotation = 0

    for side_data in stream.get("side_data_list") or []:
        if "rotation" in side_data:
            try:
                rotation = int(round(float(side_data["rotation"]))) % 360

            except (
                TypeError,
                ValueError,
            ):
                pass

    if rotation in {
        90,
        270,
    }:
        width, height = (
            height,
            width,
        )

    duration = 0.0

    if media_type == MediaType.VIDEO:
        try:
            duration = float(
                stream.get("duration")
                or (data.get("format") or {}).get("duration")
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            duration = 0.0

    return {
        "width": max(
            0,
            width,
        ),
        "height": max(
            0,
            height,
        ),
        "rotation_deg": rotation,
        "fps": max(
            0.0,
            _fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
        ),
        "duration_seconds": max(
            0.0,
            duration,
        ),
        "codec_name": stream.get("codec_name"),
    }


class AstroMediaCatalog:
    def __init__(
        self,
        db_path=DB_PATH,
        json_path=JSON_PATH,
        allowed_roots=None,
        tasks_root=TASKS_ROOT,
    ):
        self.db_path = Path(db_path)

        self.json_path = Path(json_path)

        self.tasks_root = Path(tasks_root)

        self.allowed_roots = [
            Path(path).resolve()
            for path in (
                allowed_roots
                or [
                    MEDIA_ROOT,
                    self.tasks_root,
                ]
            )
        ]

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.json_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._init_db()

    def _connect(
        self,
    ):
        connection = sqlite3.connect(
            self.db_path,
            timeout=30.0,
        )

        connection.row_factory = sqlite3.Row

        return connection

    def _init_db(
        self,
    ):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS media(
                    media_id TEXT PRIMARY KEY,
                    local_path TEXT UNIQUE NOT NULL,
                    size INTEGER NOT NULL,
                    mtime INTEGER NOT NULL,
                    sidecar_fp TEXT,
                    active INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS overrides(
                    scene_key TEXT PRIMARY KEY,
                    media_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _allowed_path(
        self,
        path,
    ):
        resolved = Path(path).resolve()

        for root in self.allowed_roots:
            try:
                resolved.relative_to(root)

                return resolved

            except ValueError:
                continue

        raise AstroMediaError("Path outside AstroMedia allowed roots: " + str(resolved))

    def _get_by_path(
        self,
        path,
    ):
        with self._connect() as connection:
            row = connection.execute(
                ("SELECT payload FROM media WHERE local_path=?"),
                (str(path.resolve()),),
            ).fetchone()

        if not row:
            return None

        return AstroMediaItem.model_validate_json(row["payload"])

    def get(
        self,
        media_id,
    ):
        with self._connect() as connection:
            row = connection.execute(
                ("SELECT payload FROM media WHERE media_id=?"),
                (media_id,),
            ).fetchone()

        if not row:
            return None

        return AstroMediaItem.model_validate_json(row["payload"])

    def list_items(
        self,
        active_only=True,
    ):
        query = "SELECT payload FROM media"

        if active_only:
            query += " WHERE active=1"

        query += " ORDER BY local_path COLLATE NOCASE"

        with self._connect() as connection:
            rows = connection.execute(query).fetchall()

        return [AstroMediaItem.model_validate_json(row["payload"]) for row in rows]

    def _put(
        self,
        item,
    ):
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO media(
                    media_id,
                    local_path,
                    size,
                    mtime,
                    sidecar_fp,
                    active,
                    payload
                )
                VALUES(?,?,?,?,?,?,?)

                ON CONFLICT(media_id)
                DO UPDATE SET
                    local_path=excluded.local_path,
                    size=excluded.size,
                    mtime=excluded.mtime,
                    sidecar_fp=excluded.sidecar_fp,
                    active=excluded.active,
                    payload=excluded.payload
                """,
                (
                    item.media_id,
                    item.local_path,
                    item.file_size_bytes,
                    item.mtime_ns,
                    item.sidecar_fingerprint,
                    int(item.active),
                    item.model_dump_json(),
                ),
            )

    def _local_item(
        self,
        path,
        hash_mode,
    ):
        path = self._allowed_path(path)

        media_type = _media_type(path)

        if media_type is None:
            raise AstroMediaError("Unsupported media type")

        stat = path.stat()

        side_fp = _sidecar_fingerprint(path)

        old = self._get_by_path(path)

        if (
            old
            and old.file_size_bytes == stat.st_size
            and old.mtime_ns == stat.st_mtime_ns
            and old.sidecar_fingerprint == side_fp
        ):
            old.active = True

            if hash_mode == HashMode.FULL and not old.content_sha256:
                old.content_sha256 = _sha256(path)

            return (
                old,
                True,
            )

        try:
            probe = _ffprobe(
                path,
                media_type,
            )

            renderable = True
            probe_error = None

        except Exception as exc:
            probe = {
                "width": 0,
                "height": 0,
                "rotation_deg": 0,
                "fps": 0.0,
                "duration_seconds": 0.0,
                "codec_name": None,
            }

            renderable = False

            probe_error = type(exc).__name__ + ": " + str(exc)

        (
            sidecar,
            sidecar_path,
        ) = _load_sidecar(path)

        provider = Provider.LOCAL_MEDIA

        rights = Rights.UNVERIFIED

        origin = Origin.UNKNOWN

        title = path.stem

        description = ""

        tags = []

        objects = _infer_objects(
            path.stem,
            path.parent.name,
        )

        author = None
        license_name = None
        license_url = None
        attribution = None
        source_url = None
        asset_id = None

        attribution_required = False

        provenance = Provenance.LOCAL_LIBRARY

        metadata_source = "filename"

        if sidecar:
            provider = sidecar.provider or provider

            rights = sidecar.rights_status or rights

            title = sidecar.title or title

            description = sidecar.description

            tags = list(sidecar.tags)

            objects = list(sidecar.astronomy_objects) or objects

            author = sidecar.author_name

            license_name = sidecar.license_name

            license_url = _safe_url(sidecar.license_url)

            attribution = sidecar.attribution

            attribution_required = sidecar.attribution_required

            source_url = _safe_url(sidecar.source_url)

            asset_id = sidecar.provider_asset_id

            provenance = Provenance.MANUAL_METADATA

            metadata_source = sidecar_path or "sidecar"

            if sidecar.ownership_confirmed:
                provider = Provider.OWN_MEDIA

                rights = Rights.CONFIRMED_OWNED

                origin = Origin.REAL_OWN

            elif provider not in {
                Provider.LOCAL_MEDIA,
                Provider.AI_GENERATED,
            }:
                origin = Origin.REAL_EXTERNAL

        if provider == Provider.AI_GENERATED:
            origin = Origin.AI_GENERATED

        status = (
            ScientificStatus.RECREACION_VISUAL
            if (origin == Origin.AI_GENERATED)
            else ScientificStatus.NO_VERIFICADO
        )

        return (
            AstroMediaItem(
                media_id=(_media_id(path)),
                local_path=str(path),
                filename=(path.name),
                media_type=(media_type),
                **probe,
                file_size_bytes=(stat.st_size),
                mtime_ns=(stat.st_mtime_ns),
                provider=(provider),
                provider_asset_id=(asset_id),
                title=(title),
                description=(description),
                tags=(tags),
                astronomy_objects=(objects),
                author_name=(author),
                license_name=(license_name),
                license_url=(license_url),
                rights_status=(rights),
                attribution=(attribution),
                attribution_required=(attribution_required),
                source_url=(source_url),
                visual_origin=(origin),
                scientific_status=(status),
                provenance_kind=(provenance),
                metadata_source=(metadata_source),
                content_sha256=(
                    _sha256(path) if (hash_mode == HashMode.FULL) else None
                ),
                renderable=(renderable),
                probe_error=(probe_error),
                sidecar_fingerprint=(side_fp),
                indexed_at_utc=(_now()),
            ),
            False,
        )

    def normalize_material_info(
        self,
        material,
        local_path,
        task_id=None,
    ):
        source = dict(
            getattr(
                material,
                "source_info",
                None,
            )
            or {}
        )

        source.setdefault(
            "provider",
            getattr(
                material,
                "provider",
                None,
            ),
        )

        source.setdefault(
            "source_url",
            getattr(
                material,
                "url",
                None,
            ),
        )

        return self._provider_item(
            local_path,
            source,
            task_id or "material-info",
            Provenance.MPT_MATERIAL_INFO,
        )

    def _provider_item(
        self,
        path,
        source,
        task_id,
        provenance=(Provenance.MPT_TASK_PROVIDER),
    ):
        item, _ = self._local_item(
            path,
            HashMode.NONE,
        )

        item.provider = _provider(source.get("provider"))

        item.provider_asset_id = (
            str(source.get("asset_id") or source.get("id") or "") or None
        )

        item.search_term = str(source.get("search_term") or "") or None

        item.task_id = task_id

        item.title = str(source.get("title") or item.search_term or Path(path).stem)

        item.description = str(source.get("description") or "")

        creator = source.get("creator")

        if isinstance(
            creator,
            dict,
        ):
            creator = creator.get("name")

        item.author_name = str(creator or source.get("author") or "") or None

        item.source_url = _safe_url(
            source.get("source_page") or source.get("source_url") or source.get("url")
        )

        item.provenance_kind = provenance

        item.metadata_source = provenance.value

        item.rights_status = Rights.UNVERIFIED

        explicit_rights = str(source.get("rights_status") or "").upper()

        license_name = (
            str(source.get("license_name") or source.get("license") or "") or None
        )

        if explicit_rights == Rights.RESTRICTED.value:
            item.rights_status = Rights.RESTRICTED

        elif explicit_rights == Rights.VERIFIED_LICENSE.value and license_name:
            item.rights_status = Rights.VERIFIED_LICENSE

            item.license_name = license_name

            item.license_url = _safe_url(source.get("license_url"))

            item.attribution = str(source.get("attribution") or "") or None

            item.attribution_required = bool(
                source.get(
                    "attribution_required",
                    False,
                )
            )

        item.visual_origin = (
            Origin.AI_GENERATED
            if (item.provider == Provider.AI_GENERATED)
            else Origin.REAL_EXTERNAL
        )

        item.scientific_status = (
            ScientificStatus.RECREACION_VISUAL
            if (item.provider == Provider.AI_GENERATED)
            else ScientificStatus.NO_VERIFICADO
        )

        item.publication_eligible = item.rights_status in {
            Rights.CONFIRMED_OWNED,
            Rights.VERIFIED_LICENSE,
        }

        if not item.astronomy_objects:
            item.astronomy_objects = _infer_objects(
                item.title,
                item.search_term,
                item.description,
            )

        return item

    def import_task_artifacts(
        self,
    ):
        imported = 0
        errors = []

        if not self.tasks_root.is_dir():
            return (
                imported,
                errors,
            )

        def walk(
            value,
        ):
            if isinstance(
                value,
                dict,
            ):
                if isinstance(
                    value.get("material_sources"),
                    list,
                ):
                    yield value["material_sources"]

                for nested in value.values():
                    yield from walk(nested)

            elif isinstance(
                value,
                list,
            ):
                for nested in value:
                    yield from walk(nested)

        for script_json in self.tasks_root.glob("*/script.json"):
            try:
                payload = json.loads(script_json.read_text(encoding="utf-8"))

            except Exception as exc:
                errors.append(str(script_json) + ": " + str(exc))

                continue

            for group in walk(payload):
                for source in group:
                    if not isinstance(
                        source,
                        dict,
                    ):
                        continue

                    raw = (
                        source.get("local_file")
                        or source.get("local_path")
                        or source.get("path")
                        or source.get("filename")
                    )

                    if not raw:
                        continue

                    path = Path(str(raw))

                    if not path.is_absolute():
                        path = script_json.parent / path

                    if not path.is_file() or _media_type(path) is None:
                        continue

                    try:
                        item = self._provider_item(
                            path,
                            source,
                            script_json.parent.name,
                        )

                        self._put(item)

                        imported += 1

                    except Exception as exc:
                        errors.append(
                            str(path) + ": " + type(exc).__name__ + ": " + str(exc)
                        )

        return (
            imported,
            errors,
        )

    def _dedupe(
        self,
        hash_mode,
    ):
        items = self.list_items(True)

        groups = {}

        for item in items:
            item.duplicate_of_media_id = None

            groups.setdefault(
                (
                    item.file_size_bytes,
                    item.media_type.value,
                ),
                [],
            ).append(item)

        count = 0

        for group in groups.values():
            if len(group) < 2:
                if hash_mode == HashMode.FULL and group and not group[0].content_sha256:
                    group[0].content_sha256 = _sha256(Path(group[0].local_path))

                continue

            by_hash = {}

            for item in group:
                if not item.content_sha256:
                    item.content_sha256 = _sha256(Path(item.local_path))

                by_hash.setdefault(
                    item.content_sha256,
                    [],
                ).append(item)

            for same in by_hash.values():
                if len(same) < 2:
                    continue

                same = sorted(
                    same,
                    key=lambda item: (
                        0 if (item.provider == Provider.OWN_MEDIA) else 1,
                        0 if item.publication_eligible else 1,
                        item.local_path.casefold(),
                    ),
                )

                for duplicate in same[1:]:
                    duplicate.duplicate_of_media_id = same[0].media_id

                    count += 1

        for item in items:
            self._put(item)

        return count

    def export(
        self,
    ):
        payload = {
            "schema": "astromedia-v0.1",
            "generated_at_utc": _now().isoformat(),
            "items": [item.model_dump(mode="json") for item in self.list_items(False)],
        }

        temp_path = self.json_path.with_suffix(self.json_path.suffix + ".tmp")

        try:
            temp_path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            os.replace(
                temp_path,
                self.json_path,
            )

        finally:
            temp_path.unlink(missing_ok=True)

    def index_library(
        self,
        request: IndexRequest,
    ):
        started = time.perf_counter()

        root = self._allowed_path(Path(request.root))

        if not root.is_dir():
            raise AstroMediaError("Media root missing: " + str(root))

        scanned = 0
        supported = 0
        indexed = 0
        reused = 0
        sidecars = 0
        non_renderable = 0

        errors = []
        seen = set()

        iterator = root.rglob("*") if request.recursive else root.glob("*")

        for path in iterator:
            if not path.is_file():
                continue

            scanned += 1

            if _media_type(path) is None:
                continue

            supported += 1

            try:
                (
                    item,
                    was_reused,
                ) = self._local_item(
                    path,
                    request.hash_mode,
                )

                self._put(item)

                seen.add(item.media_id)

                indexed += 1

                reused += int(was_reused)

                sidecars += int(item.metadata_source.endswith(".astromedia.json"))

                non_renderable += int(not item.renderable)

            except Exception as exc:
                errors.append(str(path) + ": " + type(exc).__name__ + ": " + str(exc))

        for item in self.list_items(True):
            try:
                Path(item.local_path).resolve().relative_to(root)

            except ValueError:
                continue

            if item.media_id not in seen:
                item.active = False

                self._put(item)

        imported = 0

        if request.import_task_artifacts:
            (
                imported,
                task_errors,
            ) = self.import_task_artifacts()

            errors.extend(task_errors)

        duplicates = (
            self._dedupe(request.hash_mode)
            if (request.hash_mode != HashMode.NONE)
            else 0
        )

        self.export()

        return IndexReport(
            root=str(root),
            scanned_files=(scanned),
            supported_media_files=(supported),
            indexed_items=(indexed),
            reused_items=(reused),
            duplicate_items=(duplicates),
            imported_task_items=(imported),
            sidecar_files_used=(sidecars),
            non_renderable_items=(non_renderable),
            errors=(errors),
            elapsed_seconds=(time.perf_counter() - started),
        )

    def search(
        self,
        request: SearchRequest,
    ):
        query_tokens = _tokens(request.query)

        object_filter = {_fold(item) for item in request.astronomy_objects}

        output = []

        for item in self.list_items(True):
            if request.renderable_only and not item.renderable:
                continue

            if not request.include_duplicates and item.duplicate_of_media_id:
                continue

            if request.publication_eligible_only and not item.publication_eligible:
                continue

            if request.providers and item.provider not in request.providers:
                continue

            if request.media_types and item.media_type not in request.media_types:
                continue

            if item.width < request.min_width or item.height < request.min_height:
                continue

            if object_filter and not object_filter.issubset(
                {_fold(value) for value in item.astronomy_objects}
            ):
                continue

            fields = (
                (
                    "objects",
                    " ".join(item.astronomy_objects),
                    8,
                ),
                (
                    "title",
                    item.title,
                    6,
                ),
                (
                    "tags",
                    " ".join(item.tags),
                    5,
                ),
                (
                    "search",
                    item.search_term or "",
                    4,
                ),
                (
                    "description",
                    item.description,
                    2,
                ),
                (
                    "filename",
                    item.filename,
                    1,
                ),
            )

            score = 0.0
            reasons = []

            for (
                name,
                value,
                weight,
            ) in fields:
                overlap = query_tokens & _tokens(value)

                if overlap:
                    score += weight * len(overlap)

                    reasons.append(name + ":" + ",".join(sorted(overlap)))

            if query_tokens and score <= 0:
                continue

            if item.provider == Provider.OWN_MEDIA:
                score += 3

                reasons.append("provider:OWN_MEDIA")

            elif item.provider in {
                Provider.NASA,
                Provider.ESA,
                Provider.WIKIMEDIA,
            }:
                score += 1

            if item.publication_eligible:
                score += 1

                reasons.append("rights:verified")

            output.append(
                SearchResult(
                    score=score,
                    reasons=reasons,
                    item=item,
                )
            )

        return sorted(
            output,
            key=lambda result: (
                -result.score,
                result.item.local_path.casefold(),
            ),
        )[: request.limit]

    def set_override(
        self,
        scene_key,
        media_id,
    ):
        if not self.get(media_id):
            raise AstroMediaError("Unknown media_id")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO overrides(
                    scene_key,
                    media_id,
                    updated_at
                )
                VALUES(?,?,?)

                ON CONFLICT(scene_key)
                DO UPDATE SET
                    media_id=excluded.media_id,
                    updated_at=excluded.updated_at
                """,
                (
                    scene_key,
                    media_id,
                    _now().isoformat(),
                ),
            )

    def get_override(
        self,
        scene_key,
    ):
        with self._connect() as connection:
            row = connection.execute(
                ("SELECT media_id FROM overrides WHERE scene_key=?"),
                (scene_key,),
            ).fetchone()

        return row["media_id"] if row else None

    def clear_override(
        self,
        scene_key,
    ):
        with self._connect() as connection:
            connection.execute(
                ("DELETE FROM overrides WHERE scene_key=?"),
                (scene_key,),
            )

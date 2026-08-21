from __future__ import annotations

import dataclasses
import json

import pytest

import app.services.astromedia as service

from app.models.astromedia import (
    HashMode,
    IndexRequest,
    Provider,
    Rights,
    SearchRequest,
)

from app.models.schema import (
    MaterialInfo,
)


def _catalog(
    tmp_path,
    monkeypatch,
):
    media = tmp_path / "media"

    tasks = tmp_path / "tasks"

    media.mkdir()
    tasks.mkdir()

    monkeypatch.setattr(
        service,
        "_ffprobe",
        lambda path, media_type: {
            "width": 1920,
            "height": 1080,
            "rotation_deg": 0,
            "fps": 30.0,
            "duration_seconds": 5.0,
            "codec_name": "h264",
        },
    )

    return (
        service.AstroMediaCatalog(
            db_path=(tmp_path / "catalog.sqlite3"),
            json_path=(tmp_path / "catalog.json"),
            allowed_roots=[
                media,
                tasks,
            ],
            tasks_root=(tasks),
        ),
        media,
        tasks,
    )


def test_materialinfo_contract():
    assert dataclasses.is_dataclass(MaterialInfo)

    fields = {field.name for field in dataclasses.fields(MaterialInfo)}

    assert {
        "provider",
        "url",
        "duration",
        "source_info",
    } <= fields


def test_unverified_local_is_not_publicable(
    tmp_path,
    monkeypatch,
):
    (
        catalog,
        media,
        _,
    ) = _catalog(
        tmp_path,
        monkeypatch,
    )

    (media / "moon.mp4").write_bytes(b"x")

    catalog.index_library(
        IndexRequest(
            root=str(media),
            hash_mode=(HashMode.NONE),
            import_task_artifacts=False,
        )
    )

    item = catalog.list_items()[0]

    assert item.provider == Provider.LOCAL_MEDIA

    assert item.rights_status == Rights.UNVERIFIED

    assert item.publication_eligible is False


def test_owned_sidecar_is_publicable(
    tmp_path,
    monkeypatch,
):
    (
        catalog,
        media,
        _,
    ) = _catalog(
        tmp_path,
        monkeypatch,
    )

    path = media / "moon.mp4"

    path.write_bytes(b"x")

    path.with_name(path.name + ".astromedia.json").write_text(
        json.dumps(
            {
                "title": "Luna propia",
                "astronomy_objects": ["moon"],
                "ownership_confirmed": True,
            }
        ),
        encoding="utf-8",
    )

    catalog.index_library(
        IndexRequest(
            root=str(media),
            hash_mode=(HashMode.NONE),
            import_task_artifacts=False,
        )
    )

    item = catalog.list_items()[0]

    assert item.provider == Provider.OWN_MEDIA

    assert item.rights_status == Rights.CONFIRMED_OWNED

    assert item.publication_eligible is True


def test_incremental_and_duplicate_detection(
    tmp_path,
    monkeypatch,
):
    (
        catalog,
        media,
        _,
    ) = _catalog(
        tmp_path,
        monkeypatch,
    )

    (media / "a.mp4").write_bytes(b"same")

    (media / "b.mp4").write_bytes(b"same")

    first = catalog.index_library(
        IndexRequest(
            root=str(media),
            hash_mode=(HashMode.DUPLICATE_CANDIDATES),
            import_task_artifacts=False,
        )
    )

    second = catalog.index_library(
        IndexRequest(
            root=str(media),
            hash_mode=(HashMode.DUPLICATE_CANDIDATES),
            import_task_artifacts=False,
        )
    )

    assert first.duplicate_items == 1

    assert second.reused_items == 2


def test_search_and_override(
    tmp_path,
    monkeypatch,
):
    (
        catalog,
        media,
        _,
    ) = _catalog(
        tmp_path,
        monkeypatch,
    )

    path = media / "moon.mp4"

    path.write_bytes(b"x")

    path.with_name(path.name + ".astromedia.json").write_text(
        json.dumps(
            {
                "title": "Luna Valladolid",
                "astronomy_objects": ["moon"],
                "ownership_confirmed": True,
            }
        ),
        encoding="utf-8",
    )

    catalog.index_library(
        IndexRequest(
            root=str(media),
            hash_mode=(HashMode.NONE),
            import_task_artifacts=False,
        )
    )

    results = catalog.search(SearchRequest(query=("Luna moon")))

    assert results

    item = results[0].item

    catalog.set_override(
        "scene-1",
        item.media_id,
    )

    assert catalog.get_override("scene-1") == item.media_id

    catalog.clear_override("scene-1")

    assert catalog.get_override("scene-1") is None


def test_materialinfo_bridge(
    tmp_path,
    monkeypatch,
):
    (
        catalog,
        _,
        tasks,
    ) = _catalog(
        tmp_path,
        monkeypatch,
    )

    path = tasks / "provider.mp4"

    path.write_bytes(b"x")

    material = MaterialInfo(
        provider="nasa",
        url=("https://images.nasa.gov/details/x?signature=do-not-store"),
        duration=5,
        source_info={
            "asset_id": "NASA-1",
            "search_term": "Jupiter",
        },
    )

    item = catalog.normalize_material_info(
        material,
        path,
        "task-1",
    )

    assert item.provider == Provider.NASA

    assert item.provider_asset_id == "NASA-1"

    assert item.rights_status == Rights.UNVERIFIED

    assert item.publication_eligible is False

    assert item.source_url == ("https://images.nasa.gov/details/x")


def test_escape_rejected(
    tmp_path,
    monkeypatch,
):
    (
        catalog,
        _,
        _,
    ) = _catalog(
        tmp_path,
        monkeypatch,
    )

    outside = tmp_path / "outside.mp4"

    outside.write_bytes(b"x")

    with pytest.raises(service.AstroMediaError):
        catalog.index_library(
            IndexRequest(
                root=str(tmp_path),
                hash_mode=(HashMode.NONE),
                import_task_artifacts=False,
            )
        )

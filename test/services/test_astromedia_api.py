from fastapi import FastAPI

from fastapi.testclient import (
    TestClient,
)

import app.controllers.v1.astromedia as controller

from app.services.astromedia import (
    AstroMediaCatalog,
)


def _client(
    tmp_path,
    monkeypatch,
):
    media = tmp_path / "media"

    tasks = tmp_path / "tasks"

    media.mkdir()
    tasks.mkdir()

    catalog = AstroMediaCatalog(
        db_path=(tmp_path / "catalog.sqlite3"),
        json_path=(tmp_path / "catalog.json"),
        allowed_roots=[
            media,
            tasks,
        ],
        tasks_root=(tasks),
    )

    monkeypatch.setattr(
        controller,
        "_catalog",
        catalog,
    )

    app = FastAPI()

    app.include_router(controller.router)

    return TestClient(app)


def test_health(
    tmp_path,
    monkeypatch,
):
    response = _client(
        tmp_path,
        monkeypatch,
    ).get("/api/v1/astromedia/health")

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["media_root_mode"] == "read_only"

    assert data["media_files_modified_by_catalog"] is False


def test_unknown_item_404(
    tmp_path,
    monkeypatch,
):
    response = _client(
        tmp_path,
        monkeypatch,
    ).get(
        "/api/v1/astromedia/item",
        params={"media_id": "missing"},
    )

    assert response.status_code == 404

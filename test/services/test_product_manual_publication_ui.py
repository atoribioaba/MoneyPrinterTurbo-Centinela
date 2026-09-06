from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from webui.product import publication


ROOT = Path(__file__).resolve().parents[2]


def test_product_manual_publication_form_is_explicit_and_ephemeral():
    source = (ROOT / "webui" / "product" / "publication.py").read_text(
        encoding="utf-8"
    )
    compile(source, "webui/product/publication.py", "exec")

    assert "publish_verified_package" in source
    assert "ManualPublicationPlatform.YOUTUBE" in source
    assert "ManualPublicationPlatform.TIKTOK" in source
    assert 'clear_on_submit=True' in source
    assert 'enter_to_submit=False' in source
    assert 'type="password"' in source
    assert '"Ejecutar envío manual"' in source
    assert 'approved=approved' in source
    assert "Publicar ahora" not in source
    assert "AUTO_PUBLICATION=FALSE" in source
    assert "MANUAL_PUBLICATION_ONLY=TRUE" in source
    assert "AUTHORIZATION_TO_PUBLISH=FALSE" in source


def test_product_ui_does_not_offer_unverified_instagram_hosting():
    source = (ROOT / "webui" / "product" / "publication.py").read_text(
        encoding="utf-8"
    )

    options_block = source[
        source.index("_MANUAL_DELIVERY_OPTIONS") : source.index(
            "def _execute_manual_delivery"
        )
    ]
    assert "ManualPublicationPlatform.INSTAGRAM" not in options_block
    assert "Instagram" in source
    assert "hosting HTTPS verificable" in source


def test_product_delivery_executor_passes_fresh_runtime_approval_only(monkeypatch):
    store = object()
    service = SimpleNamespace(store=store)
    calls = []
    sentinel = object()

    def fake_publish(store_arg, project_id, platform, **kwargs):
        calls.append((store_arg, project_id, platform, kwargs))
        return sentinel

    monkeypatch.setattr(publication, "publish_verified_package", fake_publish)

    result = publication._execute_manual_delivery(
        service,
        "project-c7",
        publication.ManualPublicationPlatform.YOUTUBE,
        access_token="runtime-only-token",
        approved=True,
    )

    assert result is sentinel
    assert calls == [
        (
            store,
            "project-c7",
            publication.ManualPublicationPlatform.YOUTUBE,
            {"access_token": "runtime-only-token", "approved": True},
        )
    ]
    assert vars(service) == {"store": store}


def test_product_delivery_executor_does_not_infer_approval(monkeypatch):
    service = SimpleNamespace(store=object())
    calls = []

    def fake_publish(*args, **kwargs):
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(publication, "publish_verified_package", fake_publish)

    publication._execute_manual_delivery(
        service,
        "project-c7",
        publication.ManualPublicationPlatform.TIKTOK,
        access_token="runtime-only-token",
        approved=False,
    )

    assert calls[0][1]["approved"] is False

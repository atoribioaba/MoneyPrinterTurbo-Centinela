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
    assert 'type="password"' not in source
    assert "authorize_desktop" in source
    assert '"Conectar plataforma y ejecutar envío manual"' in source
    assert "No hay fallback de pegado manual de tokens" in source
    assert "st.session_state" not in source
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


def test_product_oauth_flow_preverifies_before_auth_and_reuses_c6_gate(monkeypatch):
    store = object()
    service = SimpleNamespace(store=store)
    order = []
    sentinel = object()

    def fake_verify(store_arg, project_id):
        assert store_arg is store
        assert project_id == "project-c9"
        order.append("verify")

    def fake_authorize(oauth_platform):
        assert oauth_platform == publication.OAuthPlatform.YOUTUBE
        order.append("oauth")
        return SimpleNamespace(token=SimpleNamespace(access_token="runtime-token"))

    def fake_execute(service_arg, project_id, platform, **kwargs):
        assert service_arg is service
        assert project_id == "project-c9"
        assert platform == publication.ManualPublicationPlatform.YOUTUBE
        assert kwargs == {"access_token": "runtime-token", "approved": True}
        order.append("c6")
        return sentinel

    monkeypatch.setattr(publication, "verify_publication_package", fake_verify)
    monkeypatch.setattr(publication, "_execute_manual_delivery", fake_execute)

    result = publication._authorize_and_execute_manual_delivery(
        service,
        "project-c9",
        publication.ManualPublicationPlatform.YOUTUBE,
        publication.OAuthPlatform.YOUTUBE,
        approved=True,
        oauth_authorize=fake_authorize,
    )

    assert result is sentinel
    assert order == ["verify", "oauth", "c6"]


def test_product_oauth_flow_blocks_before_verify_and_browser_without_approval(monkeypatch):
    calls = []
    service = SimpleNamespace(store=object())

    monkeypatch.setattr(
        publication,
        "verify_publication_package",
        lambda *args, **kwargs: calls.append("verify"),
    )

    def fake_authorize(*args, **kwargs):
        calls.append("oauth")
        return SimpleNamespace(token=SimpleNamespace(access_token="unused"))

    try:
        publication._authorize_and_execute_manual_delivery(
            service,
            "project-c9",
            publication.ManualPublicationPlatform.TIKTOK,
            publication.OAuthPlatform.TIKTOK,
            approved=False,
            oauth_authorize=fake_authorize,
        )
    except Exception as exc:
        assert getattr(exc, "code", "") == "human_approval_required"
    else:
        raise AssertionError("missing approval must fail closed")

    assert calls == []

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from webui.product import publication


ROOT = Path(__file__).resolve().parents[2]


def test_instagram_product_ui_is_two_step_token_free_and_manual():
    source = (ROOT / "webui" / "product" / "publication.py").read_text(
        encoding="utf-8"
    )
    compile(source, "webui/product/publication.py", "exec")

    assert "prepare_instagram_manual_publication" in source
    assert "publish_instagram_manual_publication" in source
    assert "load_latest_prepared_instagram_reel" in source
    assert "get_instagram_publish_receipt" in source
    assert "callback_runtime_status" in source
    assert "ephemeral_https_settings" in source
    assert '"Autenticar y preparar Reel"' in source
    assert '"Autenticar de nuevo y publicar Reel"' in source
    assert "segunda aprobación" in source.lower()
    assert "hosting HTTPS verificable" in source
    assert "st.session_state" not in source
    assert 'type="password"' not in source
    assert "access_token=" not in source[source.index("def _render_instagram_manual_action") :]
    assert "Publicar ahora" not in source
    assert "AUTO_PUBLICATION=FALSE" in source


def test_instagram_prepare_product_action_delegates_only_fresh_approval(monkeypatch):
    store = object()
    service = SimpleNamespace(store=store)
    calls = []
    sentinel = object()

    def fake_prepare(store_arg, project_id, **kwargs):
        calls.append((store_arg, project_id, kwargs))
        return sentinel

    monkeypatch.setattr(publication, "prepare_instagram_manual_publication", fake_prepare)

    result = publication._prepare_instagram_product_action(
        service,
        "project-c13",
        approved=True,
    )

    assert result is sentinel
    assert calls == [(store, "project-c13", {"approved": True})]


def test_instagram_publish_product_action_delegates_only_second_fresh_approval(monkeypatch):
    store = object()
    service = SimpleNamespace(store=store)
    calls = []
    sentinel = object()

    def fake_publish(store_arg, project_id, **kwargs):
        calls.append((store_arg, project_id, kwargs))
        return sentinel

    monkeypatch.setattr(publication, "publish_instagram_manual_publication", fake_publish)

    result = publication._publish_instagram_product_action(
        service,
        "project-c13",
        approved=True,
    )

    assert result is sentinel
    assert calls == [(store, "project-c13", {"approved": True})]


def test_instagram_runtime_status_is_secret_free(monkeypatch):
    monkeypatch.setattr(
        publication,
        "callback_runtime_status",
        lambda: {
            "enabled": True,
            "gate_valid": True,
            "provider": "tailscale_funnel",
            "configured": True,
            "token_persistence": False,
            "long_lived_token_default": False,
            "auto_publication": False,
        },
    )
    monkeypatch.setattr(
        publication,
        "ephemeral_https_settings",
        lambda: SimpleNamespace(enabled=True, provider=SimpleNamespace(value="cloudflare_quick")),
    )

    status = publication._instagram_product_runtime_status()

    assert status == {
        "callback_gate_valid": True,
        "callback_enabled": True,
        "callback_configured": True,
        "callback_provider": "tailscale_funnel",
        "transport_gate_valid": True,
        "transport_enabled": True,
        "transport_provider": "cloudflare_quick",
        "ready": True,
        "token_persistence": False,
        "auto_publication": False,
    }
    assert "secret" not in str(status).lower()
    assert "token" in str(status).lower()

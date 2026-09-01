from pathlib import Path
from unittest.mock import patch

from app.config import CENTINELA_API_BIND_HOST, config
from app.services.upload_post import AUTO_PUBLICATION, UploadPostService


ROOT = Path(__file__).resolve().parents[2]


def test_centinela_api_bind_is_forced_to_loopback():
    assert CENTINELA_API_BIND_HOST == "127.0.0.1"
    assert config.listen_host == CENTINELA_API_BIND_HOST


@patch(
    "app.services.upload_post.config.app",
    {
        "upload_post_enabled": True,
        "upload_post_api_key": "configured-key",
        "upload_post_username": "configured-user",
        "upload_post_platforms": ["tiktok", "instagram", "youtube"],
        "upload_post_auto_upload": True,
    },
)
def test_legacy_config_cannot_enable_automatic_publication():
    service = UploadPostService()

    assert service.is_configured() is True
    assert AUTO_PUBLICATION is False
    assert service.auto_upload is False


def test_task_pipeline_still_gates_cross_post_on_fail_closed_auto_upload():
    source = (ROOT / "app" / "services" / "task.py").read_text(
        encoding="utf-8"
    )
    assert "upload_post.upload_post_service.auto_upload" in source


def test_legacy_boolean_review_symbol_routes_to_structured_review():
    source = (ROOT / "webui" / "product" / "__init__.py").read_text(
        encoding="utf-8"
    )
    compile(source, "webui/product/__init__.py", "exec")
    assert "pages.review_page = review.review_page" in source

import os
from types import SimpleNamespace
from unittest.mock import patch

from app.controllers.v1 import video as video_controller
from app.utils import logging_utils


def test_redis_url_without_password_has_no_empty_auth_segment():
    assert video_controller._build_redis_url("localhost", 6379, 0, None) == (
        "redis://localhost:6379/0"
    )
    assert video_controller._build_redis_url("localhost", 6379, 0, "") == (
        "redis://localhost:6379/0"
    )


def test_redis_url_with_password_keeps_authentication():
    assert video_controller._build_redis_url("redis-host", 6380, 1, "secret") == (
        "redis://:secret@redis-host:6380/1"
    )


def test_log_formatter_survives_windows_cross_mount_relpath_failure():
    absolute_path = os.path.join(
        logging_utils.PROJECT_ROOT, "app", "services", "task.py"
    )
    record = {
        "file": SimpleNamespace(name="task.py", path=absolute_path),
        "message": "generation finished",
    }

    with patch.object(
        logging_utils.os.path,
        "relpath",
        side_effect=ValueError("path is on mount X:, start on mount C:"),
    ):
        log_format = logging_utils.format_log_record(record)

    assert log_format == logging_utils.LOG_RECORD_FORMAT
    assert record["file"].path == absolute_path.replace("\\", "/")


def test_log_formatter_keeps_external_paths_absolute():
    outside_path = os.path.join(
        os.path.dirname(logging_utils.PROJECT_ROOT), "site-packages", "worker.py"
    )
    record = {
        "file": SimpleNamespace(name="worker.py", path=outside_path),
        "message": "external warning",
    }

    logging_utils.format_log_record(record)

    assert not record["file"].path.startswith("./..")

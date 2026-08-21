import json
from pathlib import Path
from types import SimpleNamespace

from app.services import semantic_matcher


def test_build_semantic_queries_preserves_script_order():
    result = semantic_matcher.build_semantic_queries(
        video_script=(
            "Primero aparece el Sol. "
            "Después vemos la puesta de sol. "
            "Finalmente aparece la Luna."
        ),
        video_terms=[],
        candidate_count=3,
        max_segments=3,
    )

    assert len(result) == 3
    assert "Sol" in result[0]
    assert "puesta" in result[1]
    assert "Luna" in result[2]


def test_build_semantic_queries_groups_long_script():
    result = semantic_matcher.build_semantic_queries(
        video_script=(
            "Uno. Dos. Tres. Cuatro. Cinco. Seis."
        ),
        video_terms=[],
        candidate_count=2,
        max_segments=2,
    )

    assert len(result) == 2
    assert "Uno" in result[0]
    assert "Seis" in result[1]


def test_disabled_preserves_original_order(
    monkeypatch,
):
    monkeypatch.setattr(
        semantic_matcher,
        "is_enabled",
        lambda: False,
    )

    original = [
        "first.mp4",
        "second.mp4",
    ]

    outcome = (
        semantic_matcher
        .reorder_videos_for_script(
            video_script="Sol. Luna.",
            video_terms=[],
            video_paths=original,
        )
    )

    assert list(
        outcome.video_paths
    ) == original

    assert outcome.method == "disabled"


def test_success_reorders(
    monkeypatch,
    tmp_path,
):
    fake_python = (
        tmp_path
        / "python.exe"
    )

    fake_script = (
        tmp_path
        / "matcher.py"
    )

    fake_model = (
        tmp_path
        / "model"
    )

    fake_python.write_text(
        "",
        encoding="utf-8",
    )

    fake_script.write_text(
        "",
        encoding="utf-8",
    )

    fake_model.mkdir()

    settings = {
        "semantic_matcher_python":
            str(
                fake_python
            ),

        "semantic_matcher_script":
            str(
                fake_script
            ),

        "semantic_matcher_model_dir":
            str(
                fake_model
            ),

        "semantic_matcher_timeout_seconds":
            60,

        "semantic_matcher_sample_fractions":
            [
                0.2,
                0.5,
                0.8,
            ],
    }

    monkeypatch.setattr(
        semantic_matcher,
        "is_enabled",
        lambda: True,
    )

    monkeypatch.setattr(
        semantic_matcher,
        "_app_value",
        lambda name, default:
            settings.get(
                name,
                default,
            ),
    )

    def fake_run(
        command,
        **kwargs,
    ):
        request_path = Path(
            command[
                command.index(
                    "--request"
                )
                + 1
            ]
        )

        output_path = Path(
            command[
                command.index(
                    "--output"
                )
                + 1
            ]
        )

        request = json.loads(
            request_path.read_text(
                encoding="utf-8"
            )
        )

        output_path.write_text(
            json.dumps(
                {
                    "method":
                        "siglip2_test",

                    "ordered_paths": [
                        request[
                            "video_paths"
                        ][1],

                        request[
                            "video_paths"
                        ][0],
                    ],

                    "matches": [
                        {
                            "query":
                                request[
                                    "queries"
                                ][0],

                            "assigned_score":
                                0.9,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        return SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        semantic_matcher.subprocess,
        "run",
        fake_run,
    )

    outcome = (
        semantic_matcher
        .reorder_videos_for_script(
            video_script=(
                "Primero Saturno. "
                "Después la Tierra."
            ),
            video_terms=[],
            video_paths=[
                "earth.mp4",
                "saturn.mp4",
            ],
        )
    )

    assert Path(
        outcome.video_paths[
            0
        ]
    ).name == "saturn.mp4"

    assert Path(
        outcome.video_paths[
            1
        ]
    ).name == "earth.mp4"

    assert outcome.analyzed is True


def test_failure_preserves_original_order(
    monkeypatch,
    tmp_path,
):
    fake_python = (
        tmp_path
        / "python.exe"
    )

    fake_script = (
        tmp_path
        / "matcher.py"
    )

    fake_model = (
        tmp_path
        / "model"
    )

    fake_python.write_text(
        "",
        encoding="utf-8",
    )

    fake_script.write_text(
        "",
        encoding="utf-8",
    )

    fake_model.mkdir()

    settings = {
        "semantic_matcher_python":
            str(
                fake_python
            ),

        "semantic_matcher_script":
            str(
                fake_script
            ),

        "semantic_matcher_model_dir":
            str(
                fake_model
            ),
    }

    monkeypatch.setattr(
        semantic_matcher,
        "is_enabled",
        lambda: True,
    )

    monkeypatch.setattr(
        semantic_matcher,
        "_app_value",
        lambda name, default:
            settings.get(
                name,
                default,
            ),
    )

    monkeypatch.setattr(
        semantic_matcher.subprocess,
        "run",
        lambda *args, **kwargs:
            SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="boom",
            ),
    )

    original = [
        "a.mp4",
        "b.mp4",
    ]

    outcome = (
        semantic_matcher
        .reorder_videos_for_script(
            video_script="Sol. Luna.",
            video_terms=[],
            video_paths=original,
        )
    )

    assert list(
        outcome.video_paths
    ) == original

    assert (
        outcome.method
        == "fallback_original_order"
    )

    assert outcome.error

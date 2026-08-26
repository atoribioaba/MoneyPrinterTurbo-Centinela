from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from PIL import Image

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact
from app.models.astromedia import Sidecar
from app.services.centinela.scientific_visuals import (
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    ScientificVisualError,
    render_factlock_scientific_visual,
)
from app.services.centinela.writer_room import FactLock


def _fact_lock() -> FactLock:
    return FactLock(
        subject="La Luna",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="F" * 64,
        facts=[
            GroundingFact(
                fact_id="moon:angular_diameter_deg",
                label_es="Diametro angular lunar",
                value=0.5,
                unit="deg",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:test"],
            ),
            GroundingFact(
                fact_id="body:moon:visual_magnitude",
                label_es="Magnitud visual lunar",
                value=-12.14,
                unit="mag",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:test"],
            ),
            GroundingFact(
                fact_id="context:moment_utc",
                label_es="Momento UTC",
                value="2026-08-25T23:00:00Z",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["source:test"],
            ),
        ],
        sources=[],
        source_ids=["source:test"],
        scope_note="Fixture hermetico de certificacion cloud.",
        location_assumed=False,
        moment_basis="fixture UTC",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def test_factlock_scientific_visuals_are_real_9x16_files_with_owned_sidecars(tmp_path):
    fact_lock = _fact_lock()

    angular = render_factlock_scientific_visual(
        fact_lock,
        "moon:angular_diameter_deg",
        tmp_path,
    )
    magnitude = render_factlock_scientific_visual(
        fact_lock,
        "body:moon:visual_magnitude",
        tmp_path,
    )

    for artifact in (angular, magnitude):
        assert artifact.image_path.is_file()
        assert artifact.sidecar_path.is_file()
        assert artifact.manifest_path.is_file()
        assert artifact.width == OUTPUT_WIDTH == 1080
        assert artifact.height == OUTPUT_HEIGHT == 1920
        assert artifact.network_calls == 0
        assert artifact.ai_generated is False
        assert artifact.factlock_only is True
        assert len(artifact.content_sha256) == 64

        with Image.open(artifact.image_path) as image:
            assert image.size == (1080, 1920)
            assert image.format == "PNG"

        sidecar = Sidecar.model_validate_json(
            artifact.sidecar_path.read_text(encoding="utf-8")
        )
        assert sidecar.ownership_confirmed is True
        assert sidecar.astronomy_objects == ["moon"]
        assert "factlock" in sidecar.tags

        manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
        assert manifest["fact_lock_hash"] == fact_lock.context_hash
        assert manifest["fact_id"] == artifact.fact_id
        assert manifest["factlock_only"] is True
        assert manifest["network_calls"] == 0
        assert manifest["ai_generated"] is False
        assert manifest["scientific_status"] == ScientificStatus.HECHO_VERIFICADO.value
        assert manifest["content_sha256"] == artifact.content_sha256


def test_factlock_scientific_visual_rerender_is_byte_stable(tmp_path):
    fact_lock = _fact_lock()

    first = render_factlock_scientific_visual(
        fact_lock,
        "moon:angular_diameter_deg",
        tmp_path,
    )
    first_bytes = first.image_path.read_bytes()

    second = render_factlock_scientific_visual(
        fact_lock,
        "moon:angular_diameter_deg",
        tmp_path,
    )

    assert second.image_path == first.image_path
    assert second.content_sha256 == first.content_sha256
    assert second.image_path.read_bytes() == first_bytes


def test_factlock_scientific_visual_refuses_unknown_fact_id(tmp_path):
    fact_lock = _fact_lock()

    with pytest.raises(ScientificVisualError, match="not present in FactLock"):
        render_factlock_scientific_visual(
            fact_lock,
            "moon:not-a-real-fact",
            tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


def test_factlock_scientific_visual_refuses_unsupported_fact_type(tmp_path):
    fact_lock = _fact_lock()

    with pytest.raises(ScientificVisualError, match="unsupported deterministic"):
        render_factlock_scientific_visual(
            fact_lock,
            "context:moment_utc",
            tmp_path,
        )

    assert list(tmp_path.iterdir()) == []

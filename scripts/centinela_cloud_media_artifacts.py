from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# This script is intentionally executable both as `python scripts/...py` and as a
# module. Direct-file execution normally puts only `scripts/` on sys.path, which
# would make the repository `app` package unreachable. Keep the fix local to the
# certification script rather than requiring a persistent PYTHONPATH setting.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import GroundingFact
from app.services.centinela.scientific_visuals import render_factlock_scientific_visual
from app.services.centinela.writer_room import FactLock


def build_fixture_fact_lock() -> FactLock:
    return FactLock(
        subject="La Luna",
        research_mode="GENERIC_GEOCENTRIC",
        context_hash="C" * 64,
        facts=[
            GroundingFact(
                fact_id="moon:angular_diameter_deg",
                label_es="Diametro angular lunar",
                value=0.5,
                unit="deg",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["cloud-cert-fixture"],
            ),
            GroundingFact(
                fact_id="body:moon:visual_magnitude",
                label_es="Magnitud visual lunar",
                value=-12.14,
                unit="mag",
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
                source_ids=["cloud-cert-fixture"],
            ),
        ],
        sources=[],
        source_ids=["cloud-cert-fixture"],
        scope_note=(
            "Fixture hermetico para revisar visualmente los scientific visuals; "
            "no representa una efemeride publicada."
        ),
        location_assumed=False,
        moment_basis="cloud-cert-fixture",
        primary_source_verification_required_for_publication=True,
        generated_at_utc=datetime.now(timezone.utc),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="cloud-cert-artifacts")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    fact_lock = build_fixture_fact_lock()

    artifacts = [
        render_factlock_scientific_visual(
            fact_lock,
            "moon:angular_diameter_deg",
            output,
        ),
        render_factlock_scientific_visual(
            fact_lock,
            "body:moon:visual_magnitude",
            output,
        ),
    ]

    report = {
        "certification": "C2.11J-V33-mobile-v0.3",
        "fixture_only": True,
        "fact_lock_hash": fact_lock.context_hash,
        "scientific_visuals_deterministic": True,
        "scientific_visuals_factlock_only": True,
        "network_calls": 0,
        "ai_generation": False,
        "auto_publication": False,
        "requires_human_visual_review": True,
        "artifacts": [
            {
                "fact_id": artifact.fact_id,
                "image": artifact.image_path.name,
                "sidecar": artifact.sidecar_path.name,
                "manifest": artifact.manifest_path.name,
                "sha256": artifact.content_sha256,
                "width": artifact.width,
                "height": artifact.height,
            }
            for artifact in artifacts
        ],
    }
    (output / "scientific-visuals-review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("SCIENTIFIC_VISUAL_ARTIFACT_COUNT=2")
    print("SCIENTIFIC_VISUAL_DIMENSIONS=1080x1920")
    print("SCIENTIFIC_VISUAL_FACTLOCK_ONLY=TRUE")
    print("SCIENTIFIC_VISUAL_NETWORK_CALLS=0")
    print("SCIENTIFIC_VISUAL_AI_GENERATION=FALSE")
    print(f"SCIENTIFIC_VISUAL_OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

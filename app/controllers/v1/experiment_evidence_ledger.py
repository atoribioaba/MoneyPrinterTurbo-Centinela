from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.experiment_evidence_ledger import ExperimentEvidenceLedgerRequest
from app.services.experiment_evidence_ledger import (
    build_experiment_evidence_ledger,
)
from app.utils import utils

router = new_router()


@router.get("/experiment-evidence-ledger/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "experiment-evidence-ledger-v0.1",
            "planning_only": True,
            "runs_experiments": False,
            "calculates_p_values": False,
            "causal_claims": False,
            "database_writes": 0,
        },
    )


@router.post("/experiment-evidence-ledger/plan")
def plan(body: ExperimentEvidenceLedgerRequest):
    try:
        result = build_experiment_evidence_ledger(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))

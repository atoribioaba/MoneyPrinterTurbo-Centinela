from app.controllers.v1.base import new_router
from app.models.experiment_planner import ExperimentPlannerRequest
from app.services.experiment_planner import build_experiment_planner
from app.utils import utils

router = new_router()


@router.get("/experiment-planner/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "experiment-planner-v0.1",
            "planning_only": True,
            "causal_claims": False,
            "edits_project": False,
            "runs_experiments": False,
            "publishes_content": False,
        },
    )


@router.post("/experiment-planner/plan")
def plan(body: ExperimentPlannerRequest):
    result = build_experiment_planner(body)
    return utils.get_response(200, result.model_dump(mode="json"))

"""Development/Mock only. No DB, LLM, Places API or optimizer is invoked."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.models.contracts import TripRequest
from app.services.mock_workflow import fixture, mock_components
from app.services.orchestrator import Orchestrator, WorkflowRun

router = APIRouter(prefix="/api/v1/dev/workflows", tags=["Development/Mock"])


@router.post("/mock-run", response_model=WorkflowRun,
             summary="Run offline mock workflow (not an AI travel planner)",
             description="One-shot in-memory demo. Engine and Validator return fixtures, not optimized or business-validated results. Unsupported fixture inputs return a structured failed state.")
async def mock_run(request: TripRequest):
    return await Orchestrator(mock_components(), defaults=fixture("planner_defaults")).run(
        request, current_date=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date())

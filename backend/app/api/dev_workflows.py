"""Development/Mock only. No DB, LLM, Places API or optimizer is invoked."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from shared.contracts import TripRequest
from ai.interface import LangGraphOrchestrator, WorkflowRun
from app.services.workflow_factory import get_graph_orchestrator

router = APIRouter(prefix="/api/v1/dev/workflows", tags=["Development/Mock"])


@router.post("/mock-run", response_model=WorkflowRun,
             summary="Run offline mock workflow (not an AI travel planner)",
             description="One-shot in-memory demo. Engine and Validator return fixtures, not optimized or business-validated results. Unsupported fixture inputs return a structured failed state.")
async def mock_run(request: TripRequest, graph: LangGraphOrchestrator = Depends(get_graph_orchestrator)):
    result = await graph.run(
        request, current_date=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date())

    result.mode = "development_mock"
    return result

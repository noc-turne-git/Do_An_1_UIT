"""Explicit fixture adapters; Constraint Planner is deterministic business logic."""
from fastapi import Request
from app.services.graph_workflow import GraphLimits, LangGraphOrchestrator
from app.services.mock_workflow import fixture, mock_components


def get_graph_orchestrator(request: Request):
    settings = request.app.state.settings
    return LangGraphOrchestrator(mock_components(), defaults=fixture("planner_defaults"),
        limits=GraphLimits(max_clarifications=settings.graph_max_clarifications,
            max_revisions=settings.graph_max_revisions, max_retries=settings.graph_max_retries,
            max_transitions=settings.graph_max_transitions, max_candidates=settings.graph_max_candidates))

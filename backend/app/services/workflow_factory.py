"""FastAPI dependency adapter for the independent AI package."""
from fastapi import Request
from ai.interface import build_orchestrator

def get_graph_orchestrator(request: Request):
    return build_orchestrator(request.app.state.settings)

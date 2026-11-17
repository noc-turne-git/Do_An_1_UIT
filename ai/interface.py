"""Stable in-process entry points used by the API; no FastAPI or database imports."""
from ai.orchestration.graph_workflow import GraphLimits, GraphRun, LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.request_parser import empty_request, parse_turn as _parse_turn
from ai.orchestration.workflow_state import WorkflowRun
from ai.logging import log_execution
from shared.validation import validate_trip_request
from ai.orchestration.clarification_policy import ClarificationPolicy
from ai.orchestration.turns import ParsedTurn, TurnResult, StaleTurn


def get_clarification_policy(settings) -> ClarificationPolicy:
    """Export validated configuration without applying defaults or routing a run."""
    return settings.build_clarification_policy()


def build_orchestrator(settings, *, persistence=None, clarification_policy=None):
    policy = clarification_policy or get_clarification_policy(settings)
    if settings.agent_runtime_enabled:
        from ai.agents.adapters.mock import runtime_mock_components
        components = runtime_mock_components()
    else:
        components = mock_components()
    return LangGraphOrchestrator(components, defaults=fixture('planner_defaults'),
        clarification_policy=policy, persistence=persistence,
        limits=GraphLimits(**{name: getattr(settings, 'graph_' + name)
            for name in GraphLimits.model_fields}))


async def parse_turn(settings, **kwargs):
    validate_trip_request(kwargs['previous'].model_dump(mode='json'))
    run_id = kwargs.get('request_id')
    try:
        request, reply, error = await _parse_turn(settings, **kwargs)
        if request is not None:
            validate_trip_request(request.model_dump(mode='json'))
        log_execution(run_id=run_id, step='request_parser', result={
            'status': request.meta.parser_status if request else 'error'}, error=error)
        return request, reply, error
    except Exception as exc:
        log_execution(run_id=run_id, step='request_parser', error=type(exc).__name__)
        raise


async def run_turn(settings, *, graph=None, history=(), conversation_id=None,
                   correlation_id=None, **kwargs):
    """Shared chat/graph entry; extraction never issues questions or writes history."""
    graph = graph or build_orchestrator(settings)
    async def extract(previous, content, question, workflow):
        try:
            return await _parse_turn(settings, previous=previous, content=content,
                history=list(history), request_id=correlation_id, conversation_id=conversation_id,
                extraction_only=True,
                pending_question=question.model_dump(mode='json') if question else None,
                workflow_context=workflow.state.model_dump(mode='json') if workflow else None)
        except Exception:
            return ParsedTurn(None, error='PARSER_ERROR')
    return await graph.run_turn(parser=extract, **kwargs)

"""Stable in-process entry points used by the API; no FastAPI or database imports."""
from ai.orchestration.graph_workflow import GraphLimits, GraphRun, LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.request_parser import empty_request, parse_turn as _parse_turn
from ai.orchestration.workflow_state import WorkflowRun
from uuid import uuid4
from ai.logging import current_diagnostic_identity, diagnostic_scope, log_execution, traced
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
        log_execution(run_id=run_id, step='request_parser', event_type='parser.turn', phase='completed',
            input=kwargs, result={'status': request.meta.parser_status if request else 'error',
                                   'request': request, 'reply': reply}, error=error)
        return request, reply, error
    except Exception as exc:
        log_execution(run_id=run_id, step='request_parser', event_type='parser.turn', phase='failed',
                      input=kwargs, error=exc)
        raise


async def run_turn(settings, *, graph=None, history=(), conversation_id=None,
                   correlation_id=None, **kwargs):
    """Shared chat/graph entry; extraction never issues questions or writes history."""
    graph = graph or build_orchestrator(settings)
    @traced('parser')
    async def extract(previous, content, question, workflow):
        try:
            return await _parse_turn(settings, previous=previous, content=content,
                history=list(history), request_id=correlation_id, conversation_id=conversation_id,
                extraction_only=True,
                pending_question=question.model_dump(mode='json') if question else None,
                workflow_context=workflow.state.model_dump(mode='json') if workflow else None)
        except Exception:
            return ParsedTurn(None, error='PARSER_ERROR')
    # A workflow/request can span many user turns. Generate a distinct run ID
    # here, before parser and graph work begin, and retain the workflow ID as a
    # separate field in events emitted once the graph resolves it.
    trace_run_id = current_diagnostic_identity().get('run_id') or uuid4()
    with diagnostic_scope(conversation_id=conversation_id, run_id=trace_run_id,
                          request_id=correlation_id, transport='chat'):
        log_execution(event_type='run_turn', phase='started', step='run_turn',
                      input={'conversation_history': list(history),
                              'user_input': kwargs.get('content'),
                              'expected_transitions': kwargs.get('expected_transitions'),
                              'previous_run': kwargs.get('previous'),
                              'seed': kwargs.get('seed'),
                              'has_previous_run': kwargs.get('previous') is not None})
        try:
            result = await graph.run_turn(parser=extract, **kwargs)
            # Transport code commits after this scope has exited; carry the
            # generated diagnostic ID without changing the public response.
            result.diagnostic_run_id = str(trace_run_id)
            log_execution(event_type='run_turn', phase='completed', step='run_turn', result={
                'planning': result.planning, 'error': result.error,
                'workflow_status': result.run.state.status if result.run else None,
                'workflow_id': result.run.state.request_id if result.run else None,
                'parsed_request': result.request, 'assistant_reply': result.reply,
                'workflow_run': result.run})
            return result
        except Exception as exc:
            log_execution(event_type='run_turn', phase='failed', step='run_turn',
                          error=exc)
            raise

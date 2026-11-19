"""Dynamic LangGraph workflow used by HTTP and offline callers.

Components retain their existing contracts. DataRequirement is an explicit,
structured control signal, never inferred from free text or a test call count.
"""
import asyncio
from copy import deepcopy
from datetime import date
from typing import TypedDict
from uuid import uuid4

from langgraph.errors import NodeCancelledError
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator
from sqlalchemy.exc import SQLAlchemyError
from ai.logging import (current_diagnostic_identity, diagnostic_scope, log_execution,
                        update_diagnostic_identity)
from shared.validation import validate_trip_request

from shared.errors import ApplicationError
from ai.agents.runtime.context import execution_identity
from shared.contracts import (AnswerHistory, Attempt, Model, TripRequest, WorkflowState,
                              DestinationResult, DestinationEpisode, SelectionPolicy, PendingQuestion,
                              QuestionOption)
from ai.planning.constraint_planner import ConstraintPlanningError
from ai.orchestration.workflow_state import OUTPUTS, REFS, STEPS, StateMachine, WorkflowRun
from ai.orchestration.clarification_policy import ClarificationPolicy
from ai.orchestration.clarification_questions import QuestionSpec
from ai.orchestration.trip_request_defaults import apply_trip_defaults
from ai.orchestration.destination_resolution import (ANY_INTENTS, apply_resolved_destination,
    authorize_selection, can_offer_choice, can_select, reject)
from ai.orchestration.clarification_answers import accept_answer, option_request, InvalidAnswer


class DataRequirement(Exception):
    """Adapter cannot finish until a provider refreshes its data.

    Allowed providers are upstream modules only. The normal dependency walk
    then rebuilds all invalidated consumers, including the requesting module.
    """
    def __init__(self, provider: str, reason: str, *, exclude_place_ids=()):
        super().__init__(reason)
        self.provider = provider
        self.reason = reason
        self.exclude_place_ids = list(exclude_place_ids)


class FinalResolvePending(Exception):
    """A durable claim must be reconciled, never started a second time."""


class GraphLimits(Model):
    max_clarifications: int = Field(default=3, ge=0)
    max_revisions: int = Field(default=8, ge=0)
    max_retries: int = Field(default=3, ge=0)
    max_transitions: int = Field(default=80, ge=1)
    max_candidates: int = Field(default=400, ge=100)


class GraphRun(WorkflowRun):
    mode: str = "development_mock_langgraph"
    outputs: dict[str, object] = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)
    user_updates: list[dict] = Field(default_factory=list)
    visits: dict[str, int] = Field(default_factory=dict)
    transitions: int = 0
    revisions: int = 0
    retries: int = 0
    last_random_seed: int | None = None
    route_provider: str | None = None
    route_reason: str | None = None
    exclude_place_ids: list[str] = Field(default_factory=list)
    candidate_limit: int = 100
    stop_reason: str | None = None
    limits: GraphLimits | None = None
    trip_request_fields: list[str] = Field(default_factory=list)
    destination_info_fields: list[str] = Field(default_factory=list)
    awaiting_final_resolve: bool = False
    selection_question: PendingQuestion | None = None

    @field_validator("outputs", mode="before")
    @classmethod
    def restore_outputs(cls, value):
        return {step: TypeAdapter(OUTPUTS[STEPS.index(step)]).validate_python(output)
                for step, output in value.items()}



class GraphState(TypedDict):
    run: GraphRun
    request: TripRequest
    current_date: date
    answer_raw: str | None
    previous_request: TripRequest | None
    answer: AnswerHistory | None
    parsed_input: bool
    question_drafts: list[dict]


class LangGraphOrchestrator:
    def __init__(self, components, *, defaults, configuration=None, limits=None,
                 clarification_defaults=None, clarification_policy=None, persistence=None):
        self.persistence = persistence
        self.components = components
        self.defaults = deepcopy(defaults)
        self.configuration = deepcopy(configuration or {})
        self.limits = limits or GraphLimits()
        self.clarification_policy = clarification_policy or ClarificationPolicy(
            max_clarification_rounds=self.limits.max_clarifications)
        self.limits = self.limits.model_copy(update={
            'max_clarifications': self.clarification_policy.max_clarification_rounds})
        # Retained for old callers; arbitrary maps are never applied as policy.
        self.clarification_defaults = deepcopy(clarification_defaults or {})
        builder = StateGraph(GraphState)
        for step in STEPS:
            builder.add_node(step, self._node(step))
            builder.add_conditional_edges(step, self._route,
                                          {name: name for name in (*STEPS, "halt", END)})
        builder.add_node("halt", self._halt)
        builder.add_edge("halt", END)
        builder.add_conditional_edges(START, self._route,
                                      {name: name for name in (*STEPS, "halt", END)})
        self.graph = builder.compile()

    def _route(self, state):
        """Called by LangGraph after each node; no component is invoked here."""
        r = state["run"]
        def route(target, reason):
            log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=r.state.current_step,
                event_type='workflow.route', phase='selected', result={
                    'target': 'END' if target == END else target, 'reason': reason,
                    'status': r.state.status, 'transitions': r.transitions,
                    'completed_steps': r.state.completed_steps, 'route_provider': r.route_provider})
            return target
        if r.awaiting_final_resolve:
            return route(END, 'awaiting_final_resolve')
        if r.state.status in {"completed", "failed", "clarifying", "awaiting_relaxation"}:
            return route(END, 'terminal_or_waiting_state')
        if r.stop_reason or r.transitions >= self.limits.max_transitions:
            return route('halt', r.stop_reason or 'transition_limit')
        if r.route_provider:
            target = r.route_provider
        else:
            o = r.outputs
            if "planning_engine" in o and o["planning_engine"].status in {"infeasible", "partial"}:
                target = "place_agent"
            elif "validator" in o and o["validator"].suggested_action == "replan":
                rules = {v.rule for v in o["validator"].violations}
                target = ("place_agent" if rules & {"budget", "price_integrity", "must_visit"}
                          else "constraint_planner" if "input_integrity" in rules
                          else "planning_engine")
            else:
                target = next((s for s in STEPS if s not in o), END)
        if target == END:
            return route(END, 'all_steps_complete')
        if r.visits.get(target, 0) and r.revisions >= self.limits.max_revisions:
            return route('halt', 'revision_limit')
        if target == "planning_engine" and r.visits.get(target, 0):
            maximum = min(self.limits.max_retries, r.outputs["planning_input_builder"].solver_config.max_retries)
            if r.retries >= maximum:
                return route('halt', 'retry_limit')
        # Refresh prerequisites before invoking the requested provider.
        next_step = next((s for s in STEPS[:STEPS.index(target)] if s not in r.outputs), target)
        return route(next_step, r.route_reason or ('refresh_prerequisite' if next_step != target else 'next_step'))

    async def _halt(self, state):
        r = state["run"].model_copy(deep=True)
        reason = r.stop_reason or ("transition_limit" if r.transitions >= self.limits.max_transitions
                                  else "retry_or_revision_limit")
        StateMachine(r).fail(r.state.current_step, reason, "Workflow stopped at configured limit")
        r.final_result = None
        r.explanation = None
        r.stop_reason = reason
        r.history.append(dict(event="halt", reason=reason, transitions=r.transitions))
        log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step='halt',
            event_type='workflow.halt', phase='completed', result={'reason': reason, 'state': r.state})
        return {"run": r}

    def _invalidate(self, r, step):
        index = STEPS.index(step)
        removed = [s for s in STEPS[index:] if s in r.outputs]
        for s in STEPS[index:]:
            r.outputs.pop(s, None)
        refs = r.state.artifacts.model_dump()
        for ref in REFS[index:]:
            if ref:
                refs[ref] = None
        StateMachine(r).update(artifacts=refs,
                               completed_steps=[s for s in r.state.completed_steps if s not in STEPS[index:]])
        r.final_result = None
        r.explanation = None
        return removed

    def _save(self, r, step, value):
        r.outputs[step] = deepcopy(value)
        ref = REFS[STEPS.index(step)]
        if ref:
            artifact_id = uuid4()
            r.artifacts[artifact_id] = TypeAdapter(OUTPUTS[STEPS.index(step)]).dump_python(value, mode="json")
            refs = r.state.artifacts.model_dump()
            refs[ref] = artifact_id
            StateMachine(r).update(artifacts=refs)
            if self.persistence:
                self.persistence.save(r, step, value, artifact_id)
        StateMachine(r).update(completed_steps=[*r.state.completed_steps, step])

    def _attempt(self, r, result, violations):
        p = r.outputs["planning_input_builder"]
        StateMachine(r).update(attempts=[*r.attempts, Attempt(
            attempt=len(r.attempts) + 1, step=r.state.current_step,
            random_seed=p.solver_config.random_seed, time_limit_seconds=p.solver_config.time_limit_seconds,
            result=result, violations=violations, itinerary_id=r.state.artifacts.itinerary_id,
            validation_result_id=r.state.artifacts.validation_result_id)])

    def _node(self, step):
        async def invoke(state):
            r = state["run"].model_copy(deep=True)
            sm = StateMachine(r)
            rerun = bool(r.visits.get(step))
            r.transitions += 1
            r.revisions += int(rerun)
            r.visits[step] = r.visits.get(step, 0) + 1
            reason = r.route_reason
            r.route_provider = r.route_reason = None
            refs_before = r.state.artifacts.model_dump(mode="json")
            removed = self._invalidate(r, step)
            sm.update(current_step=step, status="parsing" if step == "request_parser" else
                      "validating" if step in {"validator", "explainer"} else "planning")
            event = dict(event="node", step=step, visit=r.visits[step], reason=reason,
                         invalidated=removed, dependency_refs=refs_before,
                         refs_before=r.state.artifacts.model_dump(mode="json"))
            r.history.append(event)
            log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                event_type='workflow.node', phase='started', result={
                    'visit': r.visits[step], 'rerun': rerun, 'route_reason': reason,
                    'invalidated_steps': removed, 'state_before': state['run'].state,
                    'state_after_invalidation': r.state, 'dependency_refs': refs_before})
            try:
                if step == "planning_engine" and rerun:
                    r.retries += 1
                    sm.update(retry_count=r.retries)
                    data = r.outputs["planning_input_builder"].model_dump()
                    data["solver_config"]["random_seed"] = max(
                        data["solver_config"]["random_seed"],
                        r.last_random_seed + 1 if r.last_random_seed is not None else data["solver_config"]["random_seed"] + 1)
                    self._invalidate(r, "planning_input_builder")
                    self._save(r, "planning_input_builder", TypeAdapter(OUTPUTS[5]).validate_python(data))
                if step == "planning_engine":
                    r.last_random_seed = r.outputs["planning_input_builder"].solver_config.random_seed
                token = execution_identity.set({"request_id": str(r.state.request_id), "trip_id": str(r.state.trip_id),
                                                "metadata": {"step": step, "visit": r.visits[step]}})
                try:
                    raw = await self._call(step, r, state)
                finally:
                    execution_identity.reset(token)
                raw = (raw.model_dump() if isinstance(raw, BaseModel) else
                       [v.model_dump() if isinstance(v, BaseModel) else v for v in raw]
                       if isinstance(raw, list) else raw)
                log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                    event_type='workflow.validation', phase='started',
                    input={'node': step, 'raw_output': raw,
                           'output_schema': TypeAdapter(OUTPUTS[STEPS.index(step)]).json_schema()})
                value = TypeAdapter(OUTPUTS[STEPS.index(step)]).validate_python(raw, strict=step == "explainer")
                log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                    event_type='workflow.validation', phase='succeeded',
                    input={'node': step, 'raw_output': raw}, output={'validated_output': value})
                if step in {"planning_input_builder", "planning_engine", "validator"} and value.trip_id != r.state.trip_id:
                    raise ApplicationError("planning_input_inconsistent", "Trip IDs differ")
                if step == 'request_parser':
                    question = next((q for q in r.pending_questions if q.status == 'open'), None)
                    if question is not None:
                        value, answer = accept_answer(state['previous_request'], value, question,
                            state['answer_raw'], state.get('answer'))
                        if self.persistence:
                            self.persistence.answer_question(r, answer)
                        r.answers_history.append(answer)
                        if answer.selected_option_id:
                            r.selection_question = question.model_copy(deep=True)
                        sm.update(pending_questions=[], pending_fields=[])
                    self._update_episode_policy(r, value)
                    fields = list(dict.fromkeys([*r.trip_request_fields,
                        *(p for p in value.missing_fields if not p.startswith('destination.')
                          and p not in r.destination_info_fields)]))
                    if fields:
                        value = apply_trip_defaults(value, [QuestionSpec('trip_request', tuple(fields))],
                            policy=self.clarification_policy,
                            exhausted=r.state.clarification_round >= r.state.max_clarification_rounds,
                            question_open=any(q.status == 'open' for q in r.pending_questions))
                if step == 'destination_agent':
                    value = self._destination_selection(r, value)
                self._save(r, step, value)
                self._outcome(r, step, value,
                              question_drafts=state.get('question_drafts', ()) if step == 'request_parser' else ())
                event["refs_after"] = r.state.artifacts.model_dump(mode="json")
            except InvalidAnswer as exc:
                # No accepted answer, no counter/default/final-resolve transition.
                r = state['run'].model_copy(deep=True)
                StateMachine(r).update(status='clarifying')
                event['exception'] = {'type': 'InvalidAnswer', 'handling': 'restore_clarifying'}
                log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                    event_type='workflow.validation', phase='failed', error=exc,
                    input={'node': step, 'state': state})
            except FinalResolvePending:
                r.awaiting_final_resolve = True
                event['final_resolve'] = 'pending'
            except SQLAlchemyError as exc:
                log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id,
                    step=step, event_type='database.workflow', phase='failed',
                    input={'node': step, 'state': r.state}, error=exc)
                raise
            except DataRequirement as exc:
                # No arbitrary jumps or hidden continuations: provider must precede consumer.
                if exc.provider not in STEPS[:STEPS.index(step)]:
                    sm.fail(step, "invalid_dependency", "Provider must be an upstream module")
                else:
                    r.route_provider, r.route_reason = exc.provider, exc.reason
                    r.exclude_place_ids = list(dict.fromkeys([*r.exclude_place_ids, *exc.exclude_place_ids]))
                    event["requirement"] = dict(provider=exc.provider, reason=exc.reason)
                log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                    event_type='workflow.data_requirement', phase='raised',
                    input={'node': step, 'state': r.state},
                    result={'provider': exc.provider, 'reason': exc.reason,
                            'exclude_place_ids': exc.exclude_place_ids})
            except ConstraintPlanningError as exc:
                event['exception'] = {'type': type(exc).__name__, 'code': exc.code,
                                      'message': exc.message, 'pending_fields': exc.pending_fields,
                                      'issues': exc.issues}
                log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                    event_type='workflow.constraint_error', phase='raised',
                    input={'node': step, 'state': r.state}, error=exc,
                    result={'code': exc.code, 'message': exc.message,
                            'pending_fields': exc.pending_fields, 'issues': exc.issues})
                if exc.pending_fields and all(i.code == "missing_required_field" for i in exc.issues):
                    StateMachine(r, self.persistence).clarify(
                        exc.pending_fields, request=r.outputs.get('request_parser'))
                else:
                    sm.fail(step, exc.code, exc.message)
            except Exception as exc:
                code = "output_schema_invalid" if isinstance(exc, ValidationError) else exc.code if isinstance(exc, ApplicationError) else "module_exception"
                message = "Output failed Pydantic validation" if isinstance(exc, ValidationError) else exc.message if isinstance(exc, ApplicationError) else f"Module raised {type(exc).__name__}"
                if step in {"planning_engine", "validator"}:
                    self._attempt(r, "error", [code])
                sm.fail(step, code, message, getattr(exc, "retryable", False))
                event['exception'] = {'type': type(exc).__name__, 'code': code,
                                      'retryable': bool(getattr(exc, 'retryable', False))}
                log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                    event_type='workflow.validation', phase='failed', error=exc,
                    input={'node': step, 'state': state})
            log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                event_type='workflow.node', phase='completed',
                result={'status': r.state.status, 'visit': r.visits[step],
                        'output': r.outputs.get(step), 'event': event, 'state_after': r.state,
                        'route_provider': r.route_provider, 'route_reason': r.route_reason},
                error='workflow_failed' if r.state.status == 'failed' else None)
            return {"run": r}
        return invoke

    async def _call(self, step, r, state):
        c, o = self.components, deepcopy(r.outputs)
        request = o.get("request_parser")
        destination, times = o.get("destination_agent"), o.get("constraint_planner")
        places = o.get("place_agent")
        def stage_input(component, arguments):
            log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step=step,
                event_type='workflow.stage_input', phase='prepared',
                input={'component': component, 'arguments': arguments,
                       'workflow_state': r.state, 'prior_outputs': o})
        if step == "request_parser":
            incoming = state['request']
            if state.get('parsed_input'):
                stage_input('request_parser', {'structured_request': incoming,
                    'current_date': state['current_date'], 'parsed_input': True})
                return incoming
            question = next((q for q in r.pending_questions if q.status == 'open'), None)
            answer = state.get('answer')
            selected = answer.selected_option_id if answer else (
                state['answer_raw'].strip() if question and question.kind == 'destination_choice'
                and state['answer_raw'] and state['answer_raw'].strip() in {o.option_id for o in question.options}
                else None)
            if selected:
                incoming = option_request(incoming, question, selected)
            context = {"trip_request": incoming.model_dump(mode="json"), "answer_raw": state["answer_raw"],
                       'pending_question': question.model_dump(mode='json') if question else None}
            stage_input('request_parser', {'raw_prompt': incoming.meta.raw_prompt,
                'current_date': state['current_date'], 'context': context,
                'previous_request': state['previous_request']})
            return await c.request_parser.parse(incoming.meta.raw_prompt, current_date=state["current_date"],
                context=context,
                previous_request=state["previous_request"])
        if step == "destination_agent":
            episode = r.state.destination_episode
            if (request.destination.selection_intent in ANY_INTENTS
                    and request.destination.destination_source is None
                    and r.state.destination_round >= r.state.max_destination_rounds):
                if any(q.status == 'open' for q in r.pending_questions):
                    reject('Answer the open question before final resolution')
                if episode is None:
                    reject('Final resolution requires a canonical episode')
                if self.persistence:
                    episode = self.persistence.refresh_episode(r)
                    StateMachine(r).update(destination_episode=episode)
                if episode.final_resolve_status == 'completed':
                    return episode.final_resolve_result
                if episode.final_resolve_status == 'claimed':
                    raise FinalResolvePending()
                operation_id = uuid4()
                if self.persistence:
                    episode, acquired = self.persistence.claim_final_resolve(r, operation_id)
                else:
                    episode = DestinationEpisode.model_validate(episode.model_dump() | dict(
                        final_resolve_id=operation_id, final_resolve_status='claimed'))
                    acquired = True
                StateMachine(r).update(destination_episode=episode)
                if not acquired:
                    raise FinalResolvePending()
                identity = execution_identity.get() or {}
                token = execution_identity.set(identity | {'metadata': {
                    **identity.get('metadata', {}), 'final_resolve_id': str(operation_id),
                    'final_resolve': True}})
                try:
                    stage_input('destination_agent.final_resolve', {'request': request,
                        'episode': episode, 'operation_id': operation_id})
                    raw = await c.destination_agent.select(request)
                except Exception as exc:
                    raise FinalResolvePending() from exc
                finally:
                    execution_identity.reset(token)
                result = DestinationResult.model_validate(raw).require_canonical_recovery()
                if self.persistence:
                    episode = self.persistence.complete_final_resolve(r, operation_id, result)
                else:
                    episode = DestinationEpisode.model_validate(episode.model_dump() | dict(
                        final_resolve_status='completed', final_resolve_result=result))
                StateMachine(r).update(destination_episode=episode)
                return result
            stage_input('destination_agent', {'request': request})
            return await c.destination_agent.select(request)
        if step == "constraint_planner":
            stage_input('constraint_planner', {'request': request, 'destination': destination,
                'defaults': self.defaults})
            return await c.constraint_planner.build(request, destination, defaults=deepcopy(self.defaults))
        if step == "place_agent":
            stage_input('place_agent', {'request': request, 'destination': destination,
                'time_constraints': times, 'max_candidates': r.candidate_limit,
                'exclude_place_ids': r.exclude_place_ids})
            return await c.place_agent.find(request, destination, times, max_candidates=r.candidate_limit, exclude_place_ids=list(r.exclude_place_ids))
        if step == "budget_module":
            stage_input('budget_module', {'request': request, 'places': places,
                'must_visit_place_ids': [p.place_id for p in places if p.place_id in request.destination.must_visit or p.name in request.destination.must_visit]})
            return await c.budget_module.estimate(request, places, must_visit_place_ids=[p.place_id for p in places if p.place_id in request.destination.must_visit or p.name in request.destination.must_visit])
        if step == "planning_input_builder":
            stage_input('planning_input_builder', {'trip_id': r.state.trip_id, 'request': request,
                'destination': destination, 'time_constraints': times, 'places': places,
                'budget': o['budget_module'], 'configuration': self.configuration})
            return await c.planning_input_builder.build(r.state.trip_id, request, destination, times, places, o["budget_module"], configuration=deepcopy(self.configuration))
        if step == "planning_engine":
            stage_input('planning_engine', {'planning_input': o['planning_input_builder']})
            return await c.planning_engine.plan(o["planning_input_builder"])
        if step == "validator":
            stage_input('validator', {'itinerary': o['planning_engine'],
                'planning_input': o['planning_input_builder']})
            return await c.validator.validate(o["planning_engine"], o["planning_input_builder"])
        stage_input('explainer', {'itinerary': o['planning_engine'], 'validation': o['validator']})
        return await c.explainer.explain(o["planning_engine"], o["validator"])

    def _update_episode_policy(self, r, request):
        episode = r.state.destination_episode
        if episode is None:
            return
        policy = SelectionPolicy.model_validate(request.destination.model_dump(
            include=set(SelectionPolicy.model_fields)))
        if self.persistence:
            episode = self.persistence.update_episode_policy(r, policy)
        else:
            episode = DestinationEpisode.model_validate(episode.model_dump() | policy.model_dump())
        StateMachine(r).update(destination_episode=episode)

    def _destination_selection(self, r, value):
        value.require_canonical_recovery()
        request = r.outputs['request_parser']
        episode = r.state.destination_episode
        # This node only receives an exhausted, unresolved ANY result through
        # the durable final-resolve branch.  A round-2 USER option answer has
        # destination_source=user and must never be converted to a default.
        final = bool(request.destination.selection_intent in ANY_INTENTS
                     and request.destination.destination_source is None
                     and r.state.destination_round >= r.state.max_destination_rounds)
        question = r.selection_question
        chosen = next((a for a in reversed(r.answers_history) if question
                       and a.question_id == question.question_id and a.selected_option_id), None)
        choice = bool(chosen)
        if final or value.selection_status == 'selected' and (can_select(request.destination) or choice):
            selected = authorize_selection(request, value, final=final, user_choice=choice)
            if choice:
                option = next(o for o in question.options if o.option_id == chosen.selected_option_id)
                selected.selected_candidate_id = option.candidate_id
            resolved_request = apply_resolved_destination(request, selected)
            if resolved_request != request:
                self._save(r, 'request_parser', resolved_request)
                self._update_episode_policy(r, resolved_request)
            return selected
        return value

    def _ask_destination(self, r, spec, request):
        if any(q.status == 'open' for q in r.pending_questions):
            return  # The last issued question remains actionable at the limit.
        if spec.kind == 'trip_request':
            r.trip_request_fields = list(dict.fromkeys([*r.trip_request_fields, *spec.fields]))
            if r.state.clarification_round >= r.state.max_clarification_rounds:
                updated = apply_trip_defaults(request, [spec], policy=self.clarification_policy,
                    exhausted=True, question_open=False)
                if updated == request:
                    reject('Trip requirements remain unresolved after applying configured defaults')
                self._invalidate(r, 'destination_agent')
                self._save(r, 'request_parser', updated)
                r.route_provider = 'destination_agent'
                return
        else:
            if r.state.destination_round >= r.state.max_destination_rounds:
                reject('Destination question budget exhausted without an authorized selection')
            if spec.kind == 'destination_info':
                r.destination_info_fields = list(dict.fromkeys([*r.destination_info_fields, *spec.fields]))
            if spec.constraint_proposal:
                from ai.orchestration.clarification_answers import read_path
                data = request.model_dump(mode='json')
                if any(read_path(data, path) != spec.constraint_proposal.current_values[path]
                       for path in spec.constraint_proposal.fields):
                    reject('Constraint proposal does not match the current request')
        StateMachine(r, self.persistence).issue_question(spec, request=request)

    @staticmethod
    def _draft_for_fields(fields, question_drafts):
        """Return LLM wording while keeping the issued field snapshot canonical."""
        field_set = set(fields)
        source = next((item for item in question_drafts
                       if item.get('question') and field_set.intersection(item.get('fields', ()))), None)
        if source is None:
            return None
        return {'fields': list(fields), 'question': source['question']}

    def _outcome(self, r, step, value, *, question_drafts=()):
        sm, o = StateMachine(r), r.outputs
        if step == "request_parser" and any(
                not field.startswith('destination.') and field not in r.destination_info_fields
                for field in value.missing_fields):
            fields = [field for field in value.missing_fields
                      if not field.startswith('destination.') and field not in r.destination_info_fields]
            # Only one question can be actionable at a time. Select the first
            # valid wording from the parser's (up to three) suggestions.
            source = next((item for item in question_drafts
                           if set(item.get('fields', ())).intersection(fields)), None)
            asked_fields = [field for field in fields if source and field in source['fields']] or fields
            draft = self._draft_for_fields(asked_fields, (source,) if source else ())
            r.trip_request_fields = list(dict.fromkeys([*r.trip_request_fields, *asked_fields]))
            StateMachine(r, self.persistence).clarify(asked_fields, request=value, draft=draft)
        elif (step == 'request_parser' and value.destination.selection_mode == 'explicit'
              and 'destination.city' in value.missing_fields):
            self._ask_destination(r, QuestionSpec('destination_info', ('destination.city',)), value)
        elif step == "destination_agent":
            # _destination_selection may have persisted the selected option or
            # default into request_parser.  Route using that canonical value,
            # never the pre-node output snapshot.
            request = r.outputs['request_parser']
            # A canonical source proves this node already applied either a
            # USER option, AGENT delegation, or SYSTEM exhaustion default.
            # Do not ask a third question merely because the resulting policy
            # authority is USER/SYSTEM rather than an agent-selection grant.
            if value.selection_status == 'selected' and value.destination_source is not None:
                return
            if value.selection_status == 'selected' and not can_select(request.destination):
                if can_offer_choice(request.destination) and value.candidate_regions:
                    options = tuple(QuestionOption(
                        option_id=c.candidate_id, candidate_id=c.candidate_id, city=c.city,
                        province=c.province, country=c.country, rank=c.rank, reason=c.reason)
                        for c in value.candidate_regions)
                    self._ask_destination(r, QuestionSpec('destination_choice', ('destination.city',), options), request)
                elif request.destination.selection_intent == 'UNSPECIFIED':
                    self._ask_destination(r, QuestionSpec('destination_info', ('destination.selection_intent',)), request)
                else:
                    reject('Resolver selected a destination without the required authority')
            elif value.selection_status != 'selected':
                from ai.orchestration.clarification_questions import specifications
                specs = specifications(value)
                if not specs:
                    reject('No valid destination and no concrete recovery fields')
                if value.selection_status == 'needs_user_choice' and not can_offer_choice(request.destination):
                    if request.destination.selection_intent == 'UNSPECIFIED':
                        self._ask_destination(r, QuestionSpec('destination_info', ('destination.selection_intent',)), request)
                        return
                    reject('destination_choice is not authorized for this intent')
                self._ask_destination(r, specs[0], request)
        elif step == "place_agent":
            names = {p.place_id for p in value} | {p.name for p in value}
            if not value or not set(o["request_parser"].destination.must_visit) <= names:
                r.route_provider, r.route_reason = "place_agent", "empty_or_missing_required_places"
                r.candidate_limit = min(r.candidate_limit + 100, self.limits.max_candidates)
        elif step == "budget_module":
            request = o["request_parser"]
            must = {p.place_id for p in o["place_agent"] if p.place_id in request.destination.must_visit or p.name in request.destination.must_visit}
            limit = request.budget.amount
            # Optional candidates may be skipped: never sum the entire catalog as a hard limit.
            required_cost = sum(p.estimated_total_cost.max for p in value.places if p.place_id in must and p.estimated_total_cost)
            allowed = None if limit is None else limit * (1 + request.budget.max_overrun_percent / 100)
            ids = {p.place_id for p in o["place_agent"]}
            if value.missing_costs or any(p.price_status == "UNKNOWN" for p in value.places) or {p.place_id for p in value.places} != ids or (allowed is not None and required_cost > allowed):
                r.route_provider, r.route_reason = "place_agent", "missing_costs_or_required_cost_exceeds_budget"
                r.candidate_limit = min(r.candidate_limit + 100, self.limits.max_candidates)
        elif step == "planning_engine":
            if value.status in {"infeasible", "partial"}:
                self._attempt(r, "infeasible", value.diagnostics.unsatisfied_constraints)
                if value.relaxation_suggestions:
                    sm.update(status="awaiting_relaxation")
                else:
                    r.route_reason = "infeasible_expand_candidates"
                    r.candidate_limit = min(r.candidate_limit + 100, self.limits.max_candidates)
            elif value.status == "error":
                self._attempt(r, "error", value.diagnostics.unsatisfied_constraints)
                sm.fail(step, "solver_error", "Engine reported error")
        elif step == "validator":
            self._attempt(r, "accepted" if value.is_valid and value.suggested_action == "accept" else "hard_violation", [v.type for v in value.violations])
            if value.suggested_action == "accept" and not value.is_valid:
                sm.fail(step, "validation_rejected", "Validator acceptance requires is_valid")
            elif value.suggested_action == "ask_user":
                if o["planning_engine"].relaxation_suggestions:
                    sm.update(status="awaiting_relaxation")
                else:
                    StateMachine(r, self.persistence).clarify(
                        ["additional_constraints"], request=o['request_parser'])
            elif value.suggested_action == "fail":
                sm.fail(step, "validation_rejected", "Validator rejected itinerary")
            elif value.suggested_action == "replan":
                r.route_reason = "validator_replan:" + ",".join(v.rule for v in value.violations)
        elif step == "explainer":
            r.explanation = value
            r.final_result = o["planning_engine"].model_copy(deep=True)
            sm.update(status="completed")

    async def run_turn(self, request=None, *, current_date, previous=None, content=None,
                       parser=None, seed=None, workflow_id=None, episode_id=None,
                       question_id=None, expected_transitions=None, answer=None,
                       answer_raw=None, trip_id=None, request_id=None, legacy=False):
        if not current_diagnostic_identity().get('run_id'):
            # Direct/offline graph callers have no HTTP envelope. Give every
            # invocation its own run ID while keeping the public API unchanged.
            with diagnostic_scope(conversation_id='standalone', run_id=uuid4(),
                                  workflow_id=previous.state.request_id if previous else request_id,
                                  trip_id=trip_id):
                log_execution(step='run_turn', event_type='run_turn', phase='started',
                    result={'direct_graph_call': True, 'has_previous_run': previous is not None,
                            'user_input': content or answer_raw})
                try:
                    result = await self.run_turn(request, current_date=current_date, previous=previous,
                        content=content, parser=parser, seed=seed, workflow_id=workflow_id,
                        episode_id=episode_id, question_id=question_id,
                        expected_transitions=expected_transitions, answer=answer, answer_raw=answer_raw,
                        trip_id=trip_id, request_id=request_id, legacy=legacy)
                    log_execution(step='run_turn', event_type='run_turn', phase='completed',
                        result={'status': result.run.state.status if result.run else 'not_scheduled',
                                'error_code': result.error})
                    return result
                except Exception as exc:
                    log_execution(step='run_turn', event_type='run_turn', phase='failed',
                                  error=exc)
                    raise
        from ai.orchestration.turns import check_reference, TurnResult, StaleTurn, seed_after_failed
        from ai.orchestration.request_parser import empty_request
        question = check_reference(previous, workflow_id=workflow_id, episode_id=episode_id,
            question_id=question_id, answer=answer, expected_transitions=expected_transitions)
        if answer is not None:
            if content is not None and content != answer.answer_raw:
                raise StaleTurn('Answer text differs from its reference')
            answer_raw = answer.answer_raw
        old = previous.outputs.get('request_parser') if previous else seed
        reply = None
        if content is not None:
            if parser is None:
                raise ValueError('Text turns require an extraction parser')
            base = (old or empty_request()).model_copy(deep=True)
            # A failed destination is never supplied as a candidate for reuse.
            if previous and previous.state.status == 'failed':
                base.destination = empty_request().destination
                for name in ('field_sources', 'field_confidences', 'field_decisions'):
                    setattr(base.meta, name, {k: v for k, v in getattr(base.meta, name).items()
                                             if not k.startswith('destination.')})
            parsed = await parser(base, content, question, previous)
            if parsed.error or parsed.request is None or not parsed.planning:
                log_execution(run_id=request_id, trip_id=trip_id, step='run_turn.completed',
                    result={'parsed_request': parsed.request or old or base,
                            'planning': parsed.planning, 'status': 'not_scheduled'},
                    error=parsed.error)
                return TurnResult(old or base, parsed.reply, parsed.error, parsed.planning, run=previous)
            request, reply = parsed.request, parsed.reply
            answer_raw = content
        if request is None:
            raise ValueError('A structured request or text input is required')
        validate_trip_request(request.model_dump(mode='json'))
        if previous and previous.state.status == 'failed':
            if legacy or answer_raw is None:
                retained = previous.model_copy(deep=True)
                log_execution(run_id=retained.state.request_id, trip_id=retained.state.trip_id,
                    step='run_turn.completed', result={'run': retained, 'status': 'retained_failed'})
                return TurnResult(old, reply, run=retained)
            request = seed_after_failed(old, request.destination, content or answer_raw)
            if self.persistence:
                request_id, episode, request = self.persistence.new_workflow_after_failed(previous, request)
                trip_id = previous.state.trip_id
            else:
                request_id, trip_id = uuid4(), previous.state.trip_id
            previous = None
        if not legacy and self.persistence:
            trip_id, request_id = self.persistence.prepare_turn(request, previous,
                trip_id=trip_id, request_id=request_id)
        # An unreferenced input is an edit. It may supersede an open question,
        # but a referenced response was already checked above and cannot escape it.
        if previous and not legacy and question is None and answer_raw is not None:
            previous = previous.model_copy(deep=True)
            if previous.pending_questions:
                if any(q.status == 'legacy' for q in previous.pending_questions):
                    raise StaleTurn('Legacy questions are read-only; start a new workflow')
                if self.persistence:
                    self.persistence.supersede_questions(previous)
                StateMachine(previous).update(pending_questions=[], pending_fields=[])
            if previous.state.status == 'completed' and old.destination != request.destination:
                if self.persistence:
                    episode = self.persistence.restart_completed_episode(previous, request)
                else:
                    episode = DestinationEpisode(episode_id=uuid4(), request_id=previous.state.request_id,
                        max_destination_rounds=previous.state.max_destination_rounds,
                        **request.destination.model_dump(include=set(SelectionPolicy.model_fields)))
                StateMachine(previous).update(destination_episode=episode, destination_round=0)
        raw = content or answer_raw or ''
        if question is not None and answer is None and raw.strip() in {o.option_id for o in question.options}:
            answer = AnswerHistory(answer_id=uuid4(), question_id=question.question_id,
                episode_id=question.episode_id, round=question.round, kind=question.kind,
                asked_fields=question.fields, question=question.question,
                answer_raw=raw, resolved_fields=['destination.city'], declared_unknown_fields=[],
                selected_option_id=raw.strip())
        run = await self._execute(request, current_date=current_date, previous=previous,
            answer_raw=answer_raw, answer=answer, trip_id=trip_id, request_id=request_id,
            parsed_input=content is not None, canonical=not legacy,
            question_drafts=parsed.question_drafts if content is not None else ())
        value = run.outputs.get('request_parser', request)
        if run.pending_questions:
            reply = '\n\n'.join(q.question for q in run.pending_questions)
        elif run.state.status == 'failed':
            reply = 'Không thể hoàn tất yêu cầu này. Bạn có thể gửi một điểm đến mới để bắt đầu yêu cầu mới.'
        else:
            reply = reply or run.explanation or 'Đã ghi nhận yêu cầu.'
        return TurnResult(value, reply, run=run)

    async def run(self, request: TripRequest, **kwargs):
        """Compatibility adapter; all scheduling remains in run_turn."""
        return (await self.run_turn(request, legacy=True, **kwargs)).run

    async def _execute(self, request: TripRequest, *, current_date: date, previous: GraphRun | None = None,
                  answer_raw: str | None = None, answer: AnswerHistory | None = None,
                  trip_id=None, request_id=None, parsed_input=False, canonical=False,
                  question_drafts=()):
        validate_trip_request(request.model_dump(mode='json'))
        if answer is not None:
            answer = AnswerHistory.model_validate(answer.model_dump())
            if answer_raw is not None and answer_raw != answer.answer_raw:
                raise InvalidAnswer('Answer text differs from its snapshot')
            answer_raw = answer.answer_raw
            question = next((q for q in previous.pending_questions if q.status == 'open'), None) if previous else None
            if question is None:
                raise InvalidAnswer('No open question for this answer')
            answer.validate_for(question)
        if previous and (previous.state.status == "failed" or answer_raw is None
                         and previous.state.status in {'completed', 'clarifying', 'awaiting_relaxation'}):
            return previous.model_copy(deep=True)
        r = previous.model_copy(deep=True) if previous else GraphRun(state=WorkflowState(
            request_id=request_id or uuid4(), trip_id=trip_id or uuid4(), status="parsing",
            current_step="request_parser", completed_steps=[], artifacts={}, clarification_round=0,
            max_clarification_rounds=self.clarification_policy.max_clarification_rounds,
            max_destination_rounds=self.clarification_policy.max_destination_rounds,
            pending_fields=[], retry_count=0))
        update_diagnostic_identity(workflow_id=r.state.request_id, trip_id=r.state.trip_id)
        if previous and previous.limits:
            self.limits = previous.limits.model_copy(deep=True)
        r.limits = self.limits.model_copy(deep=True)
        if canonical and previous is None:
            policy = SelectionPolicy.model_validate(request.destination.model_dump(
                include=set(SelectionPolicy.model_fields)))
            episode = (self.persistence.ensure_episode(r, policy) if self.persistence else
                DestinationEpisode(episode_id=uuid4(), request_id=r.state.request_id,
                    max_destination_rounds=r.state.max_destination_rounds, **policy.model_dump()))
            StateMachine(r).update(destination_episode=episode, destination_round=episode.destination_round)
        r.awaiting_final_resolve = False  # Refresh the durable operation on retry.
        log_execution(run_id=r.state.request_id, trip_id=r.state.trip_id, step='run_turn.started',
            event_type='workflow.run', phase='started', result={'current_date': current_date, 'request': request,
                    'previous_status': previous.state.status if previous else None,
                    'previous_state': previous.state if previous else None,
                    'parsed_input': parsed_input, 'canonical': canonical})
        old = r.outputs.get("request_parser")
        if previous:
            if previous.state.status == 'completed':
                # A completed edit gets a fresh execution budget on the same
                # workflow. Audit history and the transition revision stay intact.
                r.visits = {}
                r.revisions = 0
                r.retries = 0
                r.stop_reason = None
                r.candidate_limit = 100
            question = next((q for q in previous.pending_questions if q.status == 'open'), None)
            if question and (not previous.state.destination_episode or
                    question.episode_id != previous.state.destination_episode.episode_id):
                raise InvalidAnswer('Question does not belong to the active episode')
            r.user_updates.append(dict(event="user_update", answer_raw=answer_raw,
                                  previous_status=previous.state.status))
            if previous.state.status == "clarifying" and question is None:
                resolved, unknown = [], []
                data = request.model_dump()
                for path in previous.state.pending_fields:
                    node = data
                    try:
                        for part in path.split("."):
                            node = node[int(part)] if isinstance(node, list) else node[part]
                    except (KeyError, IndexError, TypeError, ValueError):
                        continue
                    if node is not None or data["meta"]["field_sources"].get(path) == "user":
                        data["meta"]["field_sources"][path] = "user"
                        (resolved if node is not None else unknown).append(path)
                request = TripRequest.model_validate(data)
                if previous.pending_questions:
                    r.answers_history.append(AnswerHistory(round=r.state.clarification_round or 1,
                        asked_fields=previous.state.pending_fields,
                        question=' '.join(q.question for q in previous.pending_questions),
                        answer_raw=answer_raw, resolved_fields=resolved,
                        declared_unknown_fields=unknown))
            # Parser owns changed user input; downstream artifacts are invalidated at entry.
            if answer_raw is not None:
                r.route_provider, r.route_reason = "request_parser", "user_update"
            r.final_result = None
            r.explanation = None
            StateMachine(r).update(status="parsing",
                pending_fields=question.fields if question else [],
                pending_questions=[question] if question else [])
        try:
            state = await self.graph.ainvoke(dict(run=r, request=request.model_copy(deep=True),
                current_date=current_date, answer_raw=answer_raw, answer=answer, previous_request=deepcopy(old),
                parsed_input=parsed_input, question_drafts=list(question_drafts or ())),
                config={"recursion_limit": self.limits.max_transitions + 3})
        except NodeCancelledError as exc:
            # LangGraph must treat node-raised cancellation as a failure internally.
            # Restore the public cancellation contract only after graph cleanup has finished.
            if isinstance(exc.__cause__, asyncio.CancelledError):
                raise exc.__cause__
            raise
        result = state["run"]
        if self.persistence:
            self.persistence.sync(result)
            self.persistence.save_graph(result)
        log_execution(run_id=result.state.request_id, trip_id=result.state.trip_id,
            step='run_turn.completed', event_type='workflow.run', phase='completed', result={
                'state': result.state, 'visits': result.visits, 'transitions': result.transitions,
                'revisions': result.revisions, 'retries': result.retries,
                'output_steps': list(result.outputs), 'attempts': result.attempts,
                'errors': result.errors, 'pending_questions': result.pending_questions,
                'final_result': result.final_result, 'explanation': result.explanation},
            error='workflow_failed' if result.state.status == 'failed' else None)
        return result

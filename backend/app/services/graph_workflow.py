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

from app.core.errors import ApplicationError
from app.agents.runtime.context import execution_identity
from app.models.contracts import AnswerHistory, Attempt, Model, TripRequest, WorkflowState
from app.services.constraint_planner import ConstraintPlanningError
from app.services.workflow_state import OUTPUTS, REFS, STEPS, StateMachine, WorkflowRun


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


class LangGraphOrchestrator:
    def __init__(self, components, *, defaults, configuration=None, limits=None,
                 clarification_defaults=None, persistence=None):
        self.persistence = persistence
        self.components = components
        self.defaults = deepcopy(defaults)
        self.configuration = deepcopy(configuration or {})
        self.limits = limits or GraphLimits()
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
        if r.state.status in {"completed", "failed", "clarifying", "awaiting_relaxation"}:
            return END
        if r.stop_reason or r.transitions >= self.limits.max_transitions:
            return "halt"
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
            return END
        if r.visits.get(target, 0) and r.revisions >= self.limits.max_revisions:
            return "halt"
        if target == "planning_engine" and r.visits.get(target, 0):
            maximum = min(self.limits.max_retries, r.outputs["planning_input_builder"].solver_config.max_retries)
            if r.retries >= maximum:
                return "halt"
        # Refresh prerequisites before invoking the requested provider.
        return next((s for s in STEPS[:STEPS.index(target)] if s not in r.outputs), target)

    async def _halt(self, state):
        r = state["run"].model_copy(deep=True)
        reason = r.stop_reason or ("transition_limit" if r.transitions >= self.limits.max_transitions
                                  else "retry_or_revision_limit")
        StateMachine(r).fail(r.state.current_step, reason, "Workflow stopped at configured limit")
        r.final_result = None
        r.explanation = None
        r.stop_reason = reason
        r.history.append(dict(event="halt", reason=reason, transitions=r.transitions))
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
                token = execution_identity.set({"request_id": str(r.state.request_id),
                                                "metadata": {"step": step, "visit": r.visits[step]}})
                try:
                    raw = await self._call(step, r, state)
                finally:
                    execution_identity.reset(token)
                raw = (raw.model_dump() if isinstance(raw, BaseModel) else
                       [v.model_dump() if isinstance(v, BaseModel) else v for v in raw]
                       if isinstance(raw, list) else raw)
                value = TypeAdapter(OUTPUTS[STEPS.index(step)]).validate_python(raw, strict=step == "explainer")
                if step in {"planning_input_builder", "planning_engine", "validator"} and value.trip_id != r.state.trip_id:
                    raise ApplicationError("planning_input_inconsistent", "Trip IDs differ")
                if step == "request_parser" and value.missing_fields and r.state.clarification_round >= self.limits.max_clarifications:
                    data = value.model_dump()
                    for path in value.missing_fields:
                        if path in self.clarification_defaults:
                            group, field = path.split(".")
                            data[group][field] = deepcopy(self.clarification_defaults[path])
                            data["meta"]["field_sources"][path] = "default"
                    value = TripRequest.model_validate(data)
                self._save(r, step, value)
                self._outcome(r, step, value)
                event["refs_after"] = r.state.artifacts.model_dump(mode="json")
            except SQLAlchemyError:
                raise
            except DataRequirement as exc:
                # No arbitrary jumps or hidden continuations: provider must precede consumer.
                if exc.provider not in STEPS[:STEPS.index(step)]:
                    sm.fail(step, "invalid_dependency", "Provider must be an upstream module")
                else:
                    r.route_provider, r.route_reason = exc.provider, exc.reason
                    r.exclude_place_ids = list(dict.fromkeys([*r.exclude_place_ids, *exc.exclude_place_ids]))
                    event["requirement"] = dict(provider=exc.provider, reason=exc.reason)
            except ConstraintPlanningError as exc:
                if exc.pending_fields and all(i.code == "missing_required_field" for i in exc.issues):
                    sm.clarify(exc.pending_fields)
                else:
                    sm.fail(step, exc.code, exc.message)
            except Exception as exc:
                code = "output_schema_invalid" if isinstance(exc, ValidationError) else exc.code if isinstance(exc, ApplicationError) else "module_exception"
                message = "Output failed Pydantic validation" if isinstance(exc, ValidationError) else exc.message if isinstance(exc, ApplicationError) else f"Module raised {type(exc).__name__}"
                if step in {"planning_engine", "validator"}:
                    self._attempt(r, "error", [code])
                sm.fail(step, code, message, getattr(exc, "retryable", False))
            return {"run": r}
        return invoke

    async def _call(self, step, r, state):
        c, o = self.components, deepcopy(r.outputs)
        request = o.get("request_parser")
        destination, times = o.get("destination_agent"), o.get("constraint_planner")
        places = o.get("place_agent")
        if step == "request_parser":
            return await c.request_parser.parse(state["request"].meta.raw_prompt, current_date=state["current_date"],
                context={"trip_request": state["request"].model_dump(mode="json"), "answer_raw": state["answer_raw"]}, previous_request=state["previous_request"])
        if step == "destination_agent":
            return await c.destination_agent.select(request)
        if step == "constraint_planner":
            return await c.constraint_planner.build(request, destination, defaults=deepcopy(self.defaults))
        if step == "place_agent":
            return await c.place_agent.find(request, destination, times, max_candidates=r.candidate_limit, exclude_place_ids=list(r.exclude_place_ids))
        if step == "budget_module":
            return await c.budget_module.estimate(request, places, must_visit_place_ids=[p.place_id for p in places if p.place_id in request.destination.must_visit or p.name in request.destination.must_visit])
        if step == "planning_input_builder":
            return await c.planning_input_builder.build(r.state.trip_id, request, destination, times, places, o["budget_module"], configuration=deepcopy(self.configuration))
        if step == "planning_engine":
            return await c.planning_engine.plan(o["planning_input_builder"])
        if step == "validator":
            return await c.validator.validate(o["planning_engine"], o["planning_input_builder"])
        return await c.explainer.explain(o["planning_engine"], o["validator"])

    def _outcome(self, r, step, value):
        sm, o = StateMachine(r), r.outputs
        if step == "request_parser" and value.missing_fields:
            sm.clarify(value.missing_fields)
        elif step == "destination_agent":
            sm.update(destination_round=r.state.destination_round + 1)
            if value.selection_status != "selected" or value.missing_fields:
                sm.clarify(value.missing_fields or ["destination.city"])
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
                    sm.clarify(["additional_constraints"])
            elif value.suggested_action == "fail":
                sm.fail(step, "validation_rejected", "Validator rejected itinerary")
            elif value.suggested_action == "replan":
                r.route_reason = "validator_replan:" + ",".join(v.rule for v in value.violations)
        elif step == "explainer":
            r.explanation = value
            r.final_result = o["planning_engine"].model_copy(deep=True)
            sm.update(status="completed")

    async def run(self, request: TripRequest, *, current_date: date, previous: GraphRun | None = None,
                  answer_raw: str | None = None, trip_id=None, request_id=None):
        if previous and (previous.state.status == "failed" or answer_raw is None):
            return previous.model_copy(deep=True)
        r = previous.model_copy(deep=True) if previous else GraphRun(state=WorkflowState(
            request_id=request_id or uuid4(), trip_id=trip_id or uuid4(), status="parsing",
            current_step="request_parser", completed_steps=[], artifacts={}, clarification_round=0,
            max_clarification_rounds=self.limits.max_clarifications, pending_fields=[], retry_count=0))
        if previous and previous.limits:
            self.limits = previous.limits.model_copy(deep=True)
        r.limits = self.limits.model_copy(deep=True)
        old = r.outputs.get("request_parser")
        if previous:
            r.user_updates.append(dict(event="user_update", answer_raw=answer_raw,
                                  previous_status=previous.state.status))
            if previous.state.status == "clarifying":
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
                r.answers_history.append(AnswerHistory(round=r.state.clarification_round,
                    asked_fields=previous.state.pending_fields, question=" ".join(q.question for q in previous.pending_questions),
                    answer_raw=answer_raw, resolved_fields=resolved, declared_unknown_fields=unknown))
            # Parser owns changed user input; downstream artifacts are invalidated at entry.
            r.route_provider, r.route_reason = "request_parser", "user_update"
            r.final_result = None
            r.explanation = None
            StateMachine(r).update(status="parsing", pending_fields=[], pending_questions=[])
        try:
            state = await self.graph.ainvoke(dict(run=r, request=request.model_copy(deep=True),
                current_date=current_date, answer_raw=answer_raw, previous_request=deepcopy(old)),
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
        return result

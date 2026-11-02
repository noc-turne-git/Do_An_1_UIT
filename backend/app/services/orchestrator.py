"""Sequential orchestration; state transitions belong here, never in agents.

Artifacts/checkpoints are per-run in-memory snapshots. No database persistence.
"""
from copy import deepcopy
from datetime import date
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.core.errors import ApplicationError
from app.models.contracts import (
    AnswerHistory, Attempt, BudgetResult, DestinationResult, Itinerary, Model,
    PlaceCandidate, PlanningInput, TimeConstraints, TripRequest, ValidationResult,
    WorkflowError, WorkflowState,
)
from app.services.constraint_planner import ConstraintPlanningError
from app.services.mock_workflow import Components

STEPS = ("request_parser", "destination_agent", "constraint_planner", "place_agent",
         "budget_module", "planning_input_builder", "planning_engine", "validator", "explainer")
REFS = ("trip_request_id", "destination_result_id", "time_constraints_id", "candidates_id",
        "costed_candidates_id", "planning_input_id", "itinerary_id", "validation_result_id", None)
OUTPUTS = (TripRequest, DestinationResult, TimeConstraints, list[PlaceCandidate],
           BudgetResult, PlanningInput, Itinerary, ValidationResult, str)


class WorkflowRun(Model):
    mode: str = "development_mock"
    notice: str = "Mock agents, builder, engine and validator; no AI optimization or business validation."
    state: WorkflowState
    artifacts: dict[str, object] = Field(default_factory=dict)
    checkpoints: list[WorkflowState] = Field(default_factory=list)
    final_result: Itinerary | None = None
    explanation: str | None = None


class StateMachine:
    """All updates are revalidated, including nested state and snapshots."""
    def __init__(self, run):
        self.run = run

    def update(self, **changes):
        data = self.run.state.model_dump()
        data.update(changes)
        self.run.state = WorkflowState.model_validate(data)
        self.run.checkpoints.append(self.run.state.model_copy(deep=True))

    def fail(self, step, code, message, retryable=False):
        self.update(status="failed", errors=[*self.run.state.errors,
                    WorkflowError(step=step, code=code, message=message, retryable=retryable)])

    def clarify(self, fields):
        fields = list(dict.fromkeys(fields))
        if self.run.state.clarification_round >= 3:
            self.fail(self.run.state.current_step, "missing_required_fields",
                      "No configured default for: " + ", ".join(fields))
            return
        self.update(status="clarifying", pending_fields=fields,
                    pending_questions=[dict(question=f"Vui lòng cung cấp {f}.", fields=[f]) for f in fields],
                    clarification_round=self.run.state.clarification_round + 1)


class Orchestrator:
    def __init__(self, components: Components, *, defaults: dict,
                 configuration: dict | None = None, clarification_defaults: dict | None = None):
        self.components = components
        self.defaults = deepcopy(defaults)
        self.configuration = deepcopy(configuration or {})
        self.clarification_defaults = deepcopy(clarification_defaults or {})

    async def run(self, request: TripRequest, *, current_date: date,
                  previous: WorkflowRun | None = None, answer_raw: str | None = None) -> WorkflowRun:
        """Resume requires an explicit answer and a structured parser input.

        Mock API is one-shot. Python callers may supply updated TripRequest for
        clarification/relaxation; no natural-language parsing is claimed.
        Resume conservatively reruns downstream steps (no artifact reuse cache).
        """
        if previous and (previous.state.status not in {"clarifying", "awaiting_relaxation"} or answer_raw is None):
            return previous.model_copy(deep=True)
        run = previous.model_copy(deep=True) if previous else WorkflowRun(state=WorkflowState(
            request_id=str(uuid4()), status="parsing", current_step="request_parser", completed_steps=[],
            artifacts={}, clarification_round=0, pending_fields=[], pending_questions=[], answers_history=[],
            attempts=[], retry_count=0, errors=[]))
        sm = StateMachine(run)
        old = run.state.model_copy(deep=True)
        sm.update(status="parsing", current_step="request_parser", completed_steps=[], artifacts={},
                  pending_fields=[], pending_questions=[], retry_count=0)
        run.final_result = None
        run.explanation = None
        attempt_open = False
        active_input = None

        def save(step, value):
            index = STEPS.index(step)
            ref = REFS[index]
            if ref:
                artifact_id = str(uuid4())
                payload = (value.model_dump(mode="json") if isinstance(value, BaseModel)
                           else [v.model_dump(mode="json") for v in value])
                run.artifacts[artifact_id] = deepcopy(payload)
                refs = run.state.artifacts.model_dump()
                refs[ref] = artifact_id
                sm.update(artifacts=refs)
            sm.update(completed_steps=list(dict.fromkeys([*run.state.completed_steps, step])))

        async def execute(step, call):
            status = "parsing" if step == "request_parser" else "validating" if step in {"validator", "explainer"} else "planning"
            sm.update(current_step=step, status=status)
            # Serialize model outputs first: model_construct/copy must not bypass validation.
            raw = await call()
            if isinstance(raw, BaseModel):
                raw = raw.model_dump()
            elif isinstance(raw, list):
                raw = [v.model_dump() if isinstance(v, BaseModel) else v for v in raw]
            value = TypeAdapter(OUTPUTS[STEPS.index(step)]).validate_python(raw, strict=step == "explainer")
            if step == "planning_input_builder" and value.trip_id != run.state.request_id:
                raise ApplicationError("planning_input_inconsistent", "Builder changed the trip ID")
            if step in {"planning_engine", "validator"} and value.trip_id != active_input.trip_id:
                raise ApplicationError("planning_input_inconsistent", "Trip IDs differ")
            save(step, value)
            return value

        def record(result, violations):
            config = active_input.solver_config
            sm.update(attempts=[*run.state.attempts, Attempt(
                attempt=len(run.state.attempts) + 1, step=run.state.current_step,
                random_seed=config.random_seed, time_limit_seconds=config.time_limit_seconds,
                result=result, violations=violations,
                itinerary_id=run.state.artifacts.itinerary_id,
                validation_result_id=run.state.artifacts.validation_result_id)])

        try:
            c = self.components
            parsed = await execute("request_parser", lambda: c.request_parser.parse(
                request.meta.raw_prompt, current_date=current_date,
                context={"trip_request": request.model_dump(mode="json"), "answer_raw": answer_raw},
                previous_request=TripRequest.model_validate(previous.artifacts[old.artifacts.trip_request_id])
                if previous and old.artifacts.trip_request_id else None))
            if previous:
                data = parsed.model_dump()
                resolved, unknown = [], []
                for path in old.pending_fields:
                    parts = path.split(".")
                    node = data
                    try:
                        for part in parts:
                            node = node[int(part)] if isinstance(node, list) else node[part]
                    except (KeyError, IndexError, ValueError, TypeError):
                        continue
                    if node is not None or data["meta"]["field_sources"].get(path) == "user":
                        data["meta"]["field_sources"][path] = "user"
                        (resolved if node is not None else unknown).append(path)
                parsed = TripRequest.model_validate(data)
                save("request_parser", parsed)
                if old.status == "clarifying":
                    sm.update(answers_history=[*run.state.answers_history, AnswerHistory(
                        round=old.clarification_round, asked_fields=old.pending_fields,
                        question=" ".join(q.question for q in old.pending_questions), answer_raw=answer_raw,
                        resolved_fields=resolved, declared_unknown_fields=unknown)])
            if parsed.missing_fields and run.state.clarification_round >= 3:
                data = parsed.model_dump()
                for path in parsed.missing_fields:
                    if path in self.clarification_defaults:
                        group, field = path.split(".")
                        data[group][field] = deepcopy(self.clarification_defaults[path])
                        data["meta"]["field_sources"][path] = "default"
                parsed = TripRequest.model_validate(data)
                save("request_parser", parsed)
            if parsed.missing_fields:
                sm.clarify(parsed.missing_fields)
                return run
            destination = await execute("destination_agent", lambda: c.destination_agent.select(parsed))
            if destination.selection_status != "selected" or destination.missing_fields:
                fields = [*destination.missing_fields]
                if destination.selection_status != "selected":
                    fields.append("destination.city" if destination.selection_status == "needs_user_choice" else "destination.selection_mode")
                sm.clarify(fields)
                return run
            times = await execute("constraint_planner", lambda: c.constraint_planner.build(parsed, destination, defaults=deepcopy(self.defaults)))
            places = await execute("place_agent", lambda: c.place_agent.find(parsed, destination, times, max_candidates=100, exclude_place_ids=[]))
            must_ids = [p.place_id for p in places if p.place_id in parsed.destination.must_visit or p.name in parsed.destination.must_visit]
            costs = await execute("budget_module", lambda: c.budget_module.estimate(parsed, places, must_visit_place_ids=must_ids))
            planning = await execute("planning_input_builder", lambda: c.planning_input_builder.build(
                run.state.request_id, parsed, destination, times, places, costs, configuration=deepcopy(self.configuration)))
            while True:
                data = planning.model_dump()
                data["solver_config"]["random_seed"] += run.state.retry_count
                active_input = PlanningInput.model_validate(data)
                if run.state.retry_count:
                    save("planning_input_builder", active_input)
                refs = run.state.artifacts.model_dump()
                refs.update(itinerary_id=None, validation_result_id=None)
                sm.update(artifacts=refs)
                attempt_open = True
                itinerary = await execute("planning_engine", lambda: c.planning_engine.plan(active_input))
                validation = await execute("validator", lambda: c.validator.validate(itinerary, active_input))
                result = ("infeasible" if itinerary.status in {"infeasible", "partial"}
                          else "error" if itinerary.status == "error" else "accepted"
                          if validation.is_valid and validation.suggested_action == "accept" else "hard_violation")
                record(result, [v.type for v in validation.violations])
                attempt_open = False
                action = validation.suggested_action
                if itinerary.status in {"infeasible", "partial"} and action != "fail":
                    action = "ask_user" if itinerary.relaxation_suggestions else "fail"
                elif itinerary.status == "error":
                    action = "fail"
                if action == "accept" and validation.is_valid:
                    run.explanation = await execute("explainer", lambda: c.explainer.explain(itinerary, validation))
                    run.final_result = itinerary.model_copy(deep=True)
                    sm.update(status="completed")
                    return run
                if action == "ask_user" and itinerary.relaxation_suggestions:
                    sm.update(status="awaiting_relaxation", retry_count=0)
                    return run
                if action == "replan" and run.state.retry_count < planning.solver_config.max_retries:
                    sm.update(retry_count=run.state.retry_count + 1, status="planning")
                    continue
                sm.fail("validator", "retry_exhausted" if action == "replan" else "validation_rejected",
                        "; ".join([v.message for v in validation.violations] + itinerary.diagnostics.unsatisfied_constraints)
                        or "Validation did not accept the itinerary")
                return run
        except ConstraintPlanningError as exc:
            if exc.pending_fields and all(i.code == "missing_required_field" for i in exc.issues):
                sm.clarify(exc.pending_fields)
            else:
                sm.fail(run.state.current_step, exc.code, exc.message)
        except Exception as exc:
            if isinstance(exc, ValidationError):
                code, message, retryable = "output_schema_invalid", "Output failed Pydantic validation", False
            elif isinstance(exc, ApplicationError):
                code, message, retryable = exc.code, exc.message, exc.retryable
            else:
                code, message, retryable = "module_exception", f"Module raised {type(exc).__name__}", False
            if attempt_open:
                record("error", [code])
            sm.fail(run.state.current_step, code, message, retryable)
        return run

"""Shared workflow contracts and validated state transitions.

This module defines data and state operations; scheduling belongs to LangGraph.
"""
from uuid import UUID

from pydantic import Field

from app.models.contracts import (
    AnswerHistory, Attempt, BudgetResult, DestinationResult, Itinerary, Model,
    PlaceCandidate, PlanningInput, TimeConstraints, TripRequest, ValidationResult,
    WorkflowError, WorkflowState, PendingQuestion,
)

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
    pending_questions: list[PendingQuestion] = Field(default_factory=list)
    answers_history: list[AnswerHistory] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    errors: list[WorkflowError] = Field(default_factory=list)
    artifacts: dict[UUID, object] = Field(default_factory=dict)
    checkpoints: list[WorkflowState] = Field(default_factory=list)
    final_result: Itinerary | None = None
    explanation: str | None = None


class StateMachine:
    """All updates are revalidated, including nested state and snapshots."""
    def __init__(self, run, persistence=None):
        self.run = run
        self.persistence = persistence

    def update(self, **changes):
        for field in ("pending_questions", "answers_history", "attempts", "errors"):
            if field in changes:
                from pydantic import TypeAdapter
                setattr(self.run, field, TypeAdapter(WorkflowRun.model_fields[field].annotation).validate_python(changes.pop(field)))
        data = self.run.state.model_dump()
        data.update(changes)
        self.run.state = WorkflowState.model_validate(data)
        self.run.checkpoints.append(self.run.state.model_copy(deep=True))
        if self.persistence:
            self.persistence.sync(self.run)

    def fail(self, step, code, message, retryable=False):
        self.update(status="failed", errors=[*self.run.errors,
                    WorkflowError(step=step, code=(code if code in {
                        "llm_output_invalid", "external_api_error", "planning_input_inconsistent",
                        "solver_error", "validator_internal_error"} else
                        "llm_output_invalid" if code == "output_schema_invalid" else
                        "validator_internal_error" if step == "validator" else
                        "solver_error" if step == "planning_engine" else "planning_input_inconsistent"),
                        message=f"[{code}] {message}", retryable=retryable)])

    def clarify(self, fields):
        fields = list(dict.fromkeys(fields))
        if self.run.state.clarification_round >= self.run.state.max_clarification_rounds:
            self.fail(self.run.state.current_step, "missing_required_fields",
                      "No configured default for: " + ", ".join(fields))
            return
        self.update(status="clarifying", pending_fields=fields,
                    pending_questions=[dict(question=f"Vui lòng cung cấp {f}.", fields=[f]) for f in fields],
                    clarification_round=self.run.state.clarification_round + 1)



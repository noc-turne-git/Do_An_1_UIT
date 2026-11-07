"""Shared workflow contracts and validated state transitions.

This module defines data and state operations; scheduling belongs to LangGraph.
"""
from uuid import UUID

from pydantic import Field

from shared.contracts import (
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

    def issue_question(self, spec, *, request=None, draft=None, question_id=None):
        """The sole workflow transition that can consume a clarification slot."""
        from ai.orchestration.clarification_questions import prepare_question

        question = prepare_question(spec, draft=draft)
        if self.persistence is not None:
            if request is None:
                raise ValueError('Issuance requires the current TripRequest')
            issued, episode, clarification_round = self.persistence.issue_question(
                self.run, question, request, question_id=question_id)
            self.update(status='clarifying', pending_fields=issued.fields,
                pending_questions=[issued], destination_episode=episode,
                destination_round=episode.destination_round,
                clarification_round=clarification_round)
            return issued
        # A draft assembled in memory has no issued identity or budget effect.
        self.update(status='clarifying', pending_fields=question.fields,
                    pending_questions=[question])
        return question

    def clarify(self, fields, *, request=None):
        from ai.orchestration.clarification_questions import QuestionSpec

        fields = tuple(dict.fromkeys(fields))
        if self.run.state.clarification_round >= self.run.state.max_clarification_rounds:
            self.fail(self.run.state.current_step, 'missing_required_fields',
                      'No configured default for: ' + ', '.join(fields))
            return
        return self.issue_question(QuestionSpec('trip_request', fields), request=request)



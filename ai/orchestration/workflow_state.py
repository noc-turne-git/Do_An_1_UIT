"""Shared workflow contracts and validated state transitions.

This module defines data and state operations; scheduling belongs to LangGraph.
"""
from uuid import UUID
import sys
from ai.logging import state_snapshot, log_state_update

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
        before = state_snapshot(self.run)
        if before is not None:
            caller = sys._getframe(1)
            source = f'{caller.f_globals.get("__name__")}.{caller.f_code.co_name}:{caller.f_lineno}'
            del caller
        for field in ("pending_questions", "answers_history", "attempts", "errors"):
            if field in changes:
                from pydantic import TypeAdapter
                setattr(self.run, field, TypeAdapter(WorkflowRun.model_fields[field].annotation).validate_python(changes.pop(field)))
        data = self.run.state.model_dump()
        data.update(changes)
        self.run.state = WorkflowState.model_validate(data)
        self.run.checkpoints.append(self.run.state.model_copy(deep=True))
        if before is not None:
            log_state_update(self.run, before, source=source)
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

    def cannot_plan(self, fields):
        """Stop without asking again; a later voluntary edit can resume this run."""
        self.update(status='awaiting_relaxation', pending_questions=[], pending_fields=[],
            errors=[*self.run.errors, WorkflowError(step=self.run.state.current_step,
                code='planning_input_inconsistent', retryable=False,
                message='[missing_required_fields] No authorized value/default for: ' + ', '.join(fields))])

    def issue_question(self, spec, *, request=None, draft=None, question_id=None):
        """The sole workflow transition that can consume a clarification slot."""
        from ai.orchestration.clarification_questions import askable_fields, prepare_question, QuestionSpec

        if request is not None and not spec.constraint_proposal and spec.kind != 'destination_choice':
            fields = askable_fields(request, spec.kind, spec.fields,
                                    parser=self.run.state.current_step == 'request_parser')
            if not fields:
                self.cannot_plan(spec.fields)
                return None
            if fields != spec.fields:
                spec = QuestionSpec(spec.kind, fields)
                draft = None  # Original wording might re-ask a closed companion field.
            if spec.kind == 'trip_request':
                from ai.orchestration.request_parser import collection_question
                draft = collection_question(request, fields=fields, drafts=[draft] if draft else ())
                if draft is not None:
                    spec = QuestionSpec(spec.kind, tuple(draft['fields']))

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

    def clarify(self, fields, *, request=None, draft=None):
        from ai.orchestration.clarification_questions import askable_fields, QuestionSpec

        fields = tuple(dict.fromkeys(fields))
        if request is not None:
            askable = askable_fields(request, 'trip_request', fields)
            if not askable:
                self.cannot_plan(fields)
                return
            if askable != fields:
                draft = None
            fields = askable
        if self.run.state.clarification_round >= self.run.state.max_clarification_rounds:
            self.fail(self.run.state.current_step, 'missing_required_fields',
                      'No configured default for: ' + ', '.join(fields))
            return
        return self.issue_question(QuestionSpec('trip_request', fields), request=request, draft=draft)



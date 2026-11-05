"""Business artifacts and application graph snapshots; not a LangGraph checkpointer."""
from uuid import uuid4
from sqlalchemy import select
from app.db.models import (ClarificationRoundRecord, PendingItemRecord, SolverAttemptRecord,
    WorkflowErrorRecord, WorkflowArtifactRecord)
from shared.contracts import PlaceCandidates
from app.repositories.workflows import OwnedRepository, RequestRepository
from app.repositories.artifacts import ArtifactRepository
from app.repositories.results import ResultRepository
from app.repositories.places import PlaceRepository

TYPES = dict(request_parser='trip_request', destination_agent='destination_result',
    constraint_planner='time_constraints', place_agent='candidates', budget_module='costed_candidates',
    planning_input_builder='planning_input', planning_engine='itinerary', validator='validation_result')


class WorkflowPersistence(OwnedRepository):
    def save_graph(self, run):
        row = self.request(run.state.request_id, lock=True)
        row.graph_snapshot = run.model_dump(mode="json")
        self.session.flush()

    def load_graph(self, request_id):
        from ai.orchestration.graph_workflow import GraphRun
        from shared.errors import ApplicationError
        row = self.request(request_id)
        if row.graph_snapshot is None:
            raise ApplicationError("not_found", "No graph snapshot; legacy sequential requests cannot resume as graphs")
        run = GraphRun.model_validate(row.graph_snapshot)
        if run.state.request_id != request_id or run.state.trip_id != row.trip_id or run.state.status != row.status:
            raise ApplicationError("planning_input_inconsistent", "Graph snapshot and request differ")
        return run

    def save(self, run, step, value, artifact_id):
        # A node is atomic even when Python mapping raises before DB commit.
        with self.session.begin_nested():
            self._save(run, step, value, artifact_id)

    def _save(self, run, step, value, artifact_id):
        request_id = run.state.request_id
        if step == 'place_agent':
            PlaceRepository(self.session, self.user_id).save_candidates(request_id, value)
        if step == 'budget_module':
            PlaceRepository(self.session, self.user_id).save_costs(request_id, value)
        payload = PlaceCandidates(places=value) if step == 'place_agent' else value
        artifact = ArtifactRepository(self.session, self.user_id).add(
            request_id, TYPES[step], payload, artifact_id=artifact_id)
        results = ResultRepository(self.session, self.user_id)
        if step == 'planning_engine':
            results.itinerary(request_id, artifact, value, len(run.attempts) + 1)
        if step == 'validator':
            results.validation(request_id, artifact, run.state.artifacts.itinerary_id, value)

    def sync(self, run):
        RequestRepository(self.session, self.user_id).update_projection(run.state)
        request_id = run.state.request_id
        rounds = {r.round: r for r in self.session.scalars(select(ClarificationRoundRecord).where(
            ClarificationRoundRecord.request_id == request_id))}
        if run.state.status == 'clarifying' and run.state.clarification_round not in rounds:
            row = ClarificationRoundRecord(id=uuid4(), request_id=request_id,
                round=run.state.clarification_round, asked_fields=run.state.pending_fields,
                question=' '.join(q.question for q in run.pending_questions))
            self.session.add(row)
            rounds[row.round] = row
        for answer in run.answers_history:
            row = rounds[answer.round]
            row.answer_raw = answer.answer_raw
            row.resolved_fields = answer.resolved_fields
            row.declared_unknown_fields = answer.declared_unknown_fields
        pending = list(self.session.scalars(select(PendingItemRecord).where(
            PendingItemRecord.request_id == request_id)))
        unknown = {f for a in run.answers_history for f in a.declared_unknown_fields}
        for row in pending:
            row.status = 'open' if row.field_path in run.state.pending_fields else 'unknown' if row.field_path in unknown else 'resolved'
        for question in run.pending_questions:
            for field in question.fields:
                if not any(p.field_path == field for p in pending):
                    row = PendingItemRecord(id=uuid4(), request_id=request_id,
                        field_path=field, question=question.question, status='open')
                    self.session.add(row)
                    pending.append(row)
        stored_attempts = set(self.session.scalars(select(SolverAttemptRecord.attempt_no).where(
            SolverAttemptRecord.request_id == request_id)))
        for attempt in run.attempts:
            if attempt.attempt not in stored_attempts:
                self.session.add(SolverAttemptRecord(id=uuid4(), request_id=request_id,
                    attempt_no=attempt.attempt, **attempt.model_dump(exclude={'attempt'})))
        # Count only the prefix already persisted; request-level lock serializes writers.
        stored_errors = list(self.session.scalars(select(WorkflowErrorRecord).where(
            WorkflowErrorRecord.request_id == request_id)))
        for error in run.errors[len(stored_errors):]:
            self.session.add(WorkflowErrorRecord(id=uuid4(), request_id=request_id, **error.model_dump()))
        self.session.flush()

    def load(self, request_id):
        from shared.contracts import WorkflowState, ArtifactReferences, AnswerHistory, Attempt, WorkflowError
        from ai.orchestration.workflow_state import WorkflowRun, STEPS, REFS
        request = self.request(request_id, lock=True)
        artifacts = list(self.session.scalars(select(WorkflowArtifactRecord).where(
            WorkflowArtifactRecord.request_id == request_id)))
        latest = {a.artifact_type: a.artifact_id for a in artifacts if a.is_latest}
        refs = {ref: latest[TYPES[step]] for step, ref in zip(STEPS, REFS)
                if ref and TYPES[step] in latest}
        pending = list(self.session.scalars(select(PendingItemRecord).where(
            PendingItemRecord.request_id == request_id, PendingItemRecord.status == 'open')))
        rounds = list(self.session.scalars(select(ClarificationRoundRecord).where(
            ClarificationRoundRecord.request_id == request_id).order_by(ClarificationRoundRecord.round)))
        run = WorkflowRun(state=WorkflowState(request_id=request_id, trip_id=request.trip_id,
            schema_version=request.schema_version, status=request.status, current_step=request.current_step,
            completed_steps=[step for step in STEPS if step in TYPES and TYPES[step] in latest],
            artifacts=ArtifactReferences(**refs), clarification_round=request.clarification_round,
            max_clarification_rounds=request.max_clarification_rounds, destination_round=request.destination_round,
            retry_count=request.retry_count, pending_fields=[p.field_path for p in pending]),
            artifacts={a.artifact_id: a.payload for a in artifacts},
            pending_questions=[dict(question=p.question, fields=[p.field_path]) for p in pending],
            answers_history=[AnswerHistory(round=r.round, asked_fields=r.asked_fields, question=r.question,
                answer_raw=r.answer_raw, resolved_fields=r.resolved_fields or [],
                declared_unknown_fields=r.declared_unknown_fields or []) for r in rounds if r.answer_raw is not None])
        run.attempts = [Attempt(attempt=a.attempt_no, step=a.step, random_seed=a.random_seed,
            time_limit_seconds=a.time_limit_seconds, result=a.result, violations=a.violations,
            itinerary_id=a.itinerary_id, validation_result_id=a.validation_result_id)
            for a in self.session.scalars(select(SolverAttemptRecord).where(
                SolverAttemptRecord.request_id == request_id).order_by(SolverAttemptRecord.attempt_no))]
        run.errors = [WorkflowError(step=e.step, code=e.code, message=e.message, retryable=e.retryable)
            for e in self.session.scalars(select(WorkflowErrorRecord).where(
                WorkflowErrorRecord.request_id == request_id).order_by(WorkflowErrorRecord.created_at))]
        return run

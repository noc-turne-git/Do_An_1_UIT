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
from ai.logging import log_execution

TYPES = dict(request_parser='trip_request', destination_agent='destination_result',
    constraint_planner='time_constraints', place_agent='candidates', budget_module='costed_candidates',
    planning_input_builder='planning_input', planning_engine='itinerary', validator='validation_result')


class WorkflowPersistence(OwnedRepository):
    def prepare_turn(self, request, previous, *, trip_id=None, request_id=None):
        from app.repositories.workflows import TripRepository
        if previous:
            row = self.request(previous.state.request_id, lock=True)
            if row.status == 'completed':
                row.status = 'parsing'
                self.session.flush()
            log_execution(run_id=row.request_id, trip_id=row.trip_id, step='persistence.prepare_turn',
                event_type='database.workflow', phase='read_update', result={
                    'operation': 'resume_workflow', 'workflow_id': row.request_id,
                    'previous_status': previous.state.status, 'status_reset': row.status == 'parsing',
                    'previous_run': previous, 'request': request})
            return row.trip_id, row.request_id
        if request_id is None:
            if trip_id is None:
                trip_id = TripRepository(self.session, self.user_id).create(title=request.destination.city).trip_id
            request_id = RequestRepository(self.session, self.user_id).create(
                trip_id, schema_version=request.schema_version).request_id
        log_execution(run_id=request_id, trip_id=trip_id, step='persistence.prepare_turn',
            event_type='database.workflow', phase='created', result={
                'operation': 'create_workflow', 'workflow_id': request_id, 'trip_created': trip_id is not None,
                'request': request})
        return trip_id, request_id

    def ensure_episode(self, run, policy):
        from app.repositories.clarifications import ClarificationRepository
        repo = ClarificationRepository(self.session, self.user_id)
        row = self.request(run.state.request_id, lock=True)
        if row.active_episode_id:
            return repo.contract(repo.episode(row.request_id))
        RequestRepository(self.session, self.user_id).update_projection(run.state)
        return repo.start_episode(row.request_id, policy)

    def new_workflow_after_failed(self, previous, request):
        from app.repositories.clarifications import ClarificationRepository
        return ClarificationRepository(self.session, self.user_id).new_workflow_after_failed(
            previous.state.request_id, request.destination, raw_prompt=request.meta.raw_prompt)

    def supersede_questions(self, run):
        from app.repositories.clarifications import ClarificationRepository
        ClarificationRepository(self.session, self.user_id).supersede_questions(run.state.request_id)

    def restart_completed_episode(self, run, request):
        from app.repositories.clarifications import ClarificationRepository
        from shared.contracts import SelectionPolicy
        repo = ClarificationRepository(self.session, self.user_id)
        if run.state.destination_episode and run.state.destination_episode.status == 'active':
            repo.close_episode(run.state.request_id, run.state.destination_episode.episode_id, status='completed')
        return repo.start_episode(run.state.request_id, SelectionPolicy.model_validate(
            request.destination.model_dump(include=set(SelectionPolicy.model_fields))))

    def refresh_episode(self, run):
        from app.repositories.clarifications import ClarificationRepository
        repo = ClarificationRepository(self.session, self.user_id)
        return repo.contract(repo.episode(run.state.request_id))

    def update_episode_policy(self, run, policy):
        from app.repositories.clarifications import ClarificationRepository
        return ClarificationRepository(self.session, self.user_id).update_policy(
            run.state.request_id, run.state.destination_episode.episode_id, policy)

    def _durable_final_checkpoint(self, run, episode):
        from ai.orchestration.workflow_state import StateMachine
        StateMachine(run).update(destination_episode=episode)
        self.sync(run)
        self.save_graph(run)
        # This is a business operation boundary, not a savepoint: a restart must
        # see the claim even if the provider or a later planning node crashes.
        try:
            self.session.commit()
            log_execution(run_id=run.state.request_id, trip_id=run.state.trip_id,
                step='persistence.final_checkpoint', event_type='database.transaction', phase='committed',
                result={'operation': 'final_resolve_checkpoint', 'episode_id': episode.episode_id,
                        'final_resolve_status': episode.final_resolve_status})
        except Exception as exc:
            log_execution(run_id=run.state.request_id, trip_id=run.state.trip_id,
                step='persistence.final_checkpoint', event_type='database.transaction', phase='failed',
                error=exc)
            raise

    def claim_final_resolve(self, run, operation_id):
        from app.repositories.clarifications import ClarificationRepository
        episode, acquired = ClarificationRepository(self.session, self.user_id).claim_final_resolve(
            run.state.request_id, run.state.destination_episode.episode_id, operation_id)
        self._durable_final_checkpoint(run, episode)
        return episode, acquired

    def complete_final_resolve(self, run, operation_id, result):
        from app.repositories.clarifications import ClarificationRepository
        episode = ClarificationRepository(self.session, self.user_id).complete_final_resolve(
            run.state.request_id, run.state.destination_episode.episode_id, operation_id, result)
        self._durable_final_checkpoint(run, episode)
        return episode

    def answer_question(self, run, answer):
        from app.repositories.clarifications import ClarificationRepository
        stored = ClarificationRepository(self.session, self.user_id).answer(
            run.state.request_id, answer)
        return stored

    def issue_question(self, run, draft, trip_request, *, question_id=None):
        """Bind identity and persist issuance in one transaction.

        The repository row lock and trigger serialize competing issuers. Delivery
        retries reuse the open question ID; a new ID is never minted for them.
        """
        from ai.orchestration.clarification_questions import attach_identity
        from app.repositories.clarifications import ClarificationRepository, conflict
        from shared.contracts import SelectionPolicy

        repo = ClarificationRepository(self.session, self.user_id)
        with self.session.begin_nested():
            request = self.request(run.state.request_id, lock=True)
            if request.active_episode_id is None:
                # The graph factory owns the configured limits for a new run.
                RequestRepository(self.session, self.user_id).update_projection(run.state)
            episode = (repo.contract(repo.episode(request.request_id))
                       if request.active_episode_id else repo.start_episode(
                           request.request_id, SelectionPolicy.model_validate(
                               trip_request.destination.model_dump(
                                   include=set(SelectionPolicy.model_fields)))))
            open_questions = repo.questions(request.request_id, open_only=True)
            if open_questions:
                existing = open_questions[0]
                if question_id is not None and existing.question_id == question_id and (
                        existing.question, existing.fields, existing.kind, existing.options,
                        existing.constraint_proposal) == (
                        draft.question, draft.fields, draft.kind, draft.options,
                        draft.constraint_proposal):
                    return existing, episode, request.clarification_round
                conflict('An issued question is still open')
            counter = (episode.destination_round if draft.counter_group == 'destination'
                       else request.clarification_round)
            maximum = (episode.max_destination_rounds if draft.counter_group == 'destination'
                       else request.max_clarification_rounds)
            if counter >= maximum:
                conflict('Question budget exhausted')
            issued = attach_identity(draft, question_id=question_id or uuid4(),
                episode_id=episode.episode_id, intent_snapshot=episode.selection_intent,
                round=counter + 1)
            issued = repo.issue(request.request_id, issued)
            episode = repo.contract(repo.episode(request.request_id))
            self.session.refresh(request)
            return issued, episode, request.clarification_round

    def save_graph(self, run):
        row = self.request(run.state.request_id, lock=True)
        if row.trip_id != run.state.trip_id or row.status != run.state.status:
            from shared.errors import ApplicationError
            raise ApplicationError('planning_input_inconsistent', 'Snapshot and persisted workflow differ; failed is terminal')
        if row.active_episode_id:
            self._validate_canonical(run)
        row.graph_snapshot = run.model_dump(mode="json")
        self.session.flush()
        log_execution(run_id=run.state.request_id, trip_id=run.state.trip_id, step='persistence.save_graph',
            event_type='database.write', phase='flushed', result={'operation': 'graph_snapshot',
                'status': run.state.status, 'completed_steps': run.state.completed_steps,
                'graph_snapshot': row.graph_snapshot})

    def load_graph(self, request_id):
        from ai.orchestration.graph_workflow import GraphRun
        from shared.errors import ApplicationError
        row = self.request(request_id)
        if row.graph_snapshot is None:
            raise ApplicationError("not_found", "No graph snapshot; legacy sequential requests cannot resume as graphs")
        run = GraphRun.model_validate(row.graph_snapshot)
        if run.state.request_id != request_id or run.state.trip_id != row.trip_id or run.state.status != row.status:
            raise ApplicationError("planning_input_inconsistent", "Graph snapshot and request differ")
        if row.active_episode_id:
            self._validate_canonical(run)
        # Legacy snapshots can still contain questions for decisions now known
        # to be closed. Retire the entire wording, including grouped questions,
        # without refunding either counter or changing destination-agent choices.
        from ai.orchestration.clarification_questions import askable_fields
        collected = run.outputs.get('request_parser')
        if collected is not None and run.state.status == 'clarifying' and any(
                askable_fields(collected, question.kind, question.fields,
                    constraint_proposal=question.constraint_proposal,
                    parser=run.state.current_step == 'request_parser') != tuple(question.fields)
                for question in run.pending_questions):
            from ai.orchestration.workflow_state import StateMachine
            if row.active_episode_id:
                self.supersede_questions(run)
            StateMachine(run).update(status='parsing', pending_questions=[], pending_fields=[])
            run.route_provider, run.route_reason = 'request_parser', 'collection_state_migration'
            self.sync(run)
            self.save_graph(run)
        log_execution(run_id=request_id, trip_id=row.trip_id, step='persistence.load_graph',
            event_type='database.read', phase='completed', result={'operation': 'graph_snapshot',
                'workflow_id': request_id, 'status': row.status, 'has_active_episode': bool(row.active_episode_id),
                'graph_snapshot': row.graph_snapshot, 'run': run})
        return run

    def _validate_canonical(self, run):
        from app.repositories.clarifications import ClarificationRepository, conflict
        repo = ClarificationRepository(self.session, self.user_id)
        request = self.request(run.state.request_id)
        episode = repo.contract(repo.episode(request.request_id))
        if run.state.destination_episode != episode or run.state.clarification_round != request.clarification_round:
            conflict('Snapshot differs from persisted canonical budget/episode')
        if run.pending_questions != repo.questions(request.request_id, open_only=True):
            conflict('Snapshot differs from issued question snapshot')
        fields = list(dict.fromkeys(f for q in run.pending_questions for f in q.fields))
        if run.state.pending_fields != fields or (fields and run.state.status != 'clarifying'):
            conflict('Snapshot pending state differs from issued questions')
        canonical_answers = [a for a in run.answers_history if a.question_id is not None]
        if canonical_answers != repo.answers(request.request_id):
            conflict('Snapshot differs from persisted canonical answers')

    def save(self, run, step, value, artifact_id):
        # A node is atomic even when Python mapping raises before DB commit.
        try:
            with self.session.begin_nested():
                self._save(run, step, value, artifact_id)
            log_execution(run_id=run.state.request_id, trip_id=run.state.trip_id, step='persistence.save',
                event_type='database.write', phase='savepoint_committed', result={'operation': 'artifact_save',
                    'node': step, 'artifact_id': artifact_id, 'artifact_type': TYPES[step],
                    'artifact_value': value, 'run_state': run.state})
        except Exception as exc:
            log_execution(run_id=run.state.request_id, trip_id=run.state.trip_id, step='persistence.save',
                event_type='database.write', phase='savepoint_rolled_back',
                result={'operation': 'artifact_save', 'node': step}, error=exc)
            raise

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
        try:
            with self.session.begin_nested():
                self._sync(run)
            log_execution(run_id=run.state.request_id, trip_id=run.state.trip_id, step='persistence.sync',
                event_type='database.write', phase='savepoint_committed', result={'operation': 'workflow_sync',
                    'status': run.state.status, 'attempts': len(run.attempts), 'errors': len(run.errors),
                    'pending_questions': len(run.pending_questions), 'run': run})
        except Exception as exc:
            log_execution(run_id=run.state.request_id, trip_id=run.state.trip_id, step='persistence.sync',
                event_type='database.write', phase='savepoint_rolled_back',
                result={'operation': 'workflow_sync'}, error=exc)
            raise

    def _sync(self, run):
        # Close the episode before the workflow becomes immutable/terminal.
        if run.state.status in {'completed', 'failed'} and run.state.destination_episode:
            from app.repositories.clarifications import ClarificationRepository
            from ai.orchestration.workflow_state import StateMachine
            repo = ClarificationRepository(self.session, self.user_id)
            episode = repo.contract(repo.episode(run.state.request_id))
            if episode.status == 'active':
                episode = repo.close_episode(run.state.request_id, episode.episode_id, status=run.state.status)
                StateMachine(run).update(destination_episode=episode, pending_questions=[], pending_fields=[])
        RequestRepository(self.session, self.user_id).update_projection(run.state)
        request_id = run.state.request_id
        if run.state.destination_episode:
            self._validate_canonical(run)
        else:
            self._sync_legacy_questions(run)
        self._sync_attempts_errors(run)
        self.session.flush()

    def _sync_legacy_questions(self, run):
        request_id = run.state.request_id
        if any(q.status != 'legacy' for q in run.pending_questions) or any(a.question_id for a in run.answers_history):
            raise ValueError('Canonical questions require explicit issuance and episode ownership')
        rounds = {(r.kind, r.round): r for r in self.session.scalars(select(ClarificationRoundRecord).where(
            ClarificationRoundRecord.request_id == request_id))}
        question_kinds = {question.kind for question in run.pending_questions}
        if len(question_kinds) > 1:
            raise ValueError('A clarification batch must have one question kind')
        question_kind = next(iter(question_kinds), 'trip_request')
        question_round = (run.state.destination_round if question_kind in {'destination_choice', 'destination_info'}
                          else run.state.clarification_round)
        round_key = (question_kind, question_round)
        if run.state.status == 'clarifying' and round_key not in rounds:
            row = ClarificationRoundRecord(id=uuid4(), request_id=request_id,
                kind=question_kind, round=question_round, asked_fields=run.state.pending_fields,
                question=' '.join(q.question for q in run.pending_questions))
            self.session.add(row)
            rounds[(row.kind, row.round)] = row
        for answer in run.answers_history:
            row = rounds[(answer.kind, answer.round)]
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
    def _sync_attempts_errors(self, run):
        request_id = run.state.request_id
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
        episode = None
        canonical_questions = []
        canonical_answers = []
        if request.active_episode_id:
            from app.repositories.clarifications import ClarificationRepository
            canonical = ClarificationRepository(self.session, self.user_id)
            episode = canonical.contract(canonical.episode(request_id))
            canonical_questions = canonical.questions(request_id, open_only=True)
            canonical_answers = canonical.answers(request_id)
        artifacts = list(self.session.scalars(select(WorkflowArtifactRecord).where(
            WorkflowArtifactRecord.request_id == request_id)))
        latest = {a.artifact_type: a.artifact_id for a in artifacts if a.is_latest}
        refs = {ref: latest[TYPES[step]] for step, ref in zip(STEPS, REFS)
                if ref and TYPES[step] in latest}
        pending = list(self.session.scalars(select(PendingItemRecord).where(
            PendingItemRecord.request_id == request_id, PendingItemRecord.status == 'open')))
        rounds = list(self.session.scalars(select(ClarificationRoundRecord).where(
            ClarificationRoundRecord.request_id == request_id).order_by(
                ClarificationRoundRecord.kind, ClarificationRoundRecord.round)))
        open_round_kinds = {round_.kind for round_ in rounds if round_.answer_raw is None}
        if pending and len(open_round_kinds) > 1:
            raise ValueError('Open pending items map to multiple clarification kinds')
        pending_kind = next(iter(open_round_kinds), 'trip_request')
        run = WorkflowRun(state=WorkflowState(request_id=request_id, trip_id=request.trip_id,
            schema_version=request.schema_version, status=request.status, current_step=request.current_step,
            completed_steps=[step for step in STEPS if step in TYPES and TYPES[step] in latest],
            artifacts=ArtifactReferences(**refs), clarification_round=request.clarification_round,
            max_clarification_rounds=request.max_clarification_rounds, destination_round=request.destination_round,
            max_destination_rounds=request.max_destination_rounds, destination_episode=episode,
            retry_count=request.retry_count, pending_fields=(list(dict.fromkeys(f for q in canonical_questions for f in q.fields))
                if episode else [p.field_path for p in pending])),
            artifacts={a.artifact_id: a.payload for a in artifacts},
            pending_questions=(canonical_questions if episode else
                [dict(question=p.question, fields=[p.field_path], kind=pending_kind) for p in pending]),
            answers_history=[AnswerHistory(round=r.round, kind=r.kind, asked_fields=r.asked_fields, question=r.question,
                answer_raw=r.answer_raw, resolved_fields=r.resolved_fields or [],
                declared_unknown_fields=r.declared_unknown_fields or []) for r in rounds if r.answer_raw is not None] + canonical_answers)
        run.attempts = [Attempt(attempt=a.attempt_no, step=a.step, random_seed=a.random_seed,
            time_limit_seconds=a.time_limit_seconds, result=a.result, violations=a.violations,
            itinerary_id=a.itinerary_id, validation_result_id=a.validation_result_id)
            for a in self.session.scalars(select(SolverAttemptRecord).where(
                SolverAttemptRecord.request_id == request_id).order_by(SolverAttemptRecord.attempt_no))]
        run.errors = [WorkflowError(step=e.step, code=e.code, message=e.message, retryable=e.retryable)
            for e in self.session.scalars(select(WorkflowErrorRecord).where(
                WorkflowErrorRecord.request_id == request_id).order_by(WorkflowErrorRecord.created_at))]
        return run

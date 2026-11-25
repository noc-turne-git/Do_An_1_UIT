"""Canonical persistence operations. Caller commits the enclosing transaction.

Graph/Chat adoption is deliberately separate: legacy sync never invents identity.
Historical final-resolve data remains readable but cannot authorize a decision.
"""
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select

from app.db.models import (DestinationEpisodeRecord, ClarificationQuestionRecord,
    ClarificationAnswerRecord)
from app.repositories.workflows import OwnedRepository, RequestRepository
from shared.contracts import (DestinationEpisode, SelectionPolicy, PendingQuestion,
    AnswerHistory, DestinationResult, Destination, TripRequest)
from shared.errors import ApplicationError
from shared.clarification_config import destination_question_allowed


def conflict(message):
    raise ApplicationError('planning_input_inconsistent', message)


class ClarificationRepository(OwnedRepository):
    def episode(self, request_id, episode_id=None):
        request = self.request(request_id)
        identifier = episode_id or request.active_episode_id
        row = self.session.scalar(select(DestinationEpisodeRecord).where(
            DestinationEpisodeRecord.request_id == request_id,
            DestinationEpisodeRecord.episode_id == identifier).execution_options(populate_existing=True))
        if row is None:
            conflict('No canonical episode; legacy snapshots are read-only for selection')
        return row

    @staticmethod
    def contract(row):
        return DestinationEpisode(episode_id=row.episode_id, request_id=row.request_id,
            status=row.status, destination_round=row.destination_round,
            max_destination_rounds=row.max_destination_rounds,
            final_resolve_status=row.final_resolve_status, final_resolve_id=row.final_resolve_id,
            final_resolve_result=row.final_resolve_result, **row.selection_policy)

    def _active(self, request, episode):
        if request.status in {'failed', 'completed'} or request.active_episode_id != episode.episode_id or episode.status != 'active':
            conflict('Stale or terminal workflow episode')

    def start_episode(self, request_id, policy: SelectionPolicy, *, episode_id=None):
        policy = SelectionPolicy.model_validate(policy.model_dump())
        with self.session.begin_nested():
            request = self.request(request_id, lock=True)
            if request.status == 'failed':
                conflict('Failed workflow requires a new workflow identity')
            identifier = episode_id or uuid4()
            existing = self.session.get(DestinationEpisodeRecord, identifier)
            if existing:
                if existing.request_id != request_id or existing.selection_policy != policy.model_dump(mode='json'):
                    conflict('Episode identity reused with different ownership or intent')
                return self.contract(existing)
            if request.active_episode_id:
                previous = self.episode(request_id)
                if previous.status == 'active':
                    conflict('Close the current episode before starting another')
            # Legacy adoption preserves its already-consumed budget. Later episodes
            # start at zero only after the previous episode was explicitly closed.
            consumed = request.destination_round if request.active_episode_id is None else 0
            value = DestinationEpisode(episode_id=identifier, request_id=request_id,
                destination_round=consumed, max_destination_rounds=request.max_destination_rounds,
                **policy.model_dump())
            row = DestinationEpisodeRecord(episode_id=identifier, request_id=request_id,
                destination_round=value.destination_round, max_destination_rounds=value.max_destination_rounds,
                selection_policy=policy.model_dump(mode='json'))
            self.session.add(row)
            self.session.flush()
            request.active_episode_id = identifier
            request.destination_round = consumed
            if request.status == 'completed':
                request.status = 'parsing'
            self.session.flush()
            self._snapshot(request)
            return self.contract(row)

    def questions(self, request_id, *, open_only=False):
        request = self.request(request_id)
        query = select(ClarificationQuestionRecord).where(ClarificationQuestionRecord.request_id == request_id)
        if open_only:
            query = query.where(ClarificationQuestionRecord.episode_id == request.active_episode_id,
                                ClarificationQuestionRecord.status == 'open')
        return [PendingQuestion.model_validate(r.payload) for r in self.session.scalars(
            query.order_by(ClarificationQuestionRecord.created_at, ClarificationQuestionRecord.question_id))]

    def answers(self, request_id):
        self.request(request_id)
        query = select(ClarificationAnswerRecord).join(ClarificationQuestionRecord,
            ClarificationAnswerRecord.question_id == ClarificationQuestionRecord.question_id).where(
            ClarificationAnswerRecord.request_id == request_id).order_by(
                ClarificationAnswerRecord.created_at, ClarificationAnswerRecord.answer_id)
        return [AnswerHistory.model_validate(r.payload) for r in self.session.scalars(query)]

    def issue(self, request_id, question: PendingQuestion):
        question = question.require_actionable()
        with self.session.begin_nested():
            request = self.request(request_id, lock=True)
            episode = self.episode(request_id, question.episode_id)
            self._active(request, episode)
            existing = self.session.get(ClarificationQuestionRecord, question.question_id)
            if existing:
                original = dict(existing.payload, status='open')
                if existing.request_id != request_id or original != question.model_dump(mode='json'):
                    conflict('Question ID retry has different content')
                return PendingQuestion.model_validate(existing.payload)
            if question.intent_snapshot != episode.selection_policy['selection_intent']:
                conflict('Question intent snapshot differs from episode')
            if self.questions(request_id, open_only=True):
                conflict('An issued question is still open')
            consumed = episode.destination_round if question.counter_group == 'destination' else request.clarification_round
            maximum = episode.max_destination_rounds if question.counter_group == 'destination' else request.max_clarification_rounds
            if question.round != consumed + 1 or not destination_question_allowed(question.kind, consumed, maximum):
                conflict('Question round is stale or budget exhausted')
            self.session.add(ClarificationQuestionRecord(question_id=question.question_id,
                request_id=request_id, episode_id=question.episode_id, kind=question.kind,
                counter_group=question.counter_group, round=question.round, status='open',
                payload=question.model_dump(mode='json')))
            self.session.flush()  # DB trigger consumes the shared budget atomically.
            self.session.refresh(request)
            self.session.refresh(episode)
            request.status = 'clarifying'
            self.session.flush()
            self._snapshot(request)
            return question

    def answer(self, request_id, answer: AnswerHistory):
        answer = AnswerHistory.model_validate(answer.model_dump())
        with self.session.begin_nested():
            request = self.request(request_id, lock=True)
            episode = self.episode(request_id, answer.episode_id)
            self._active(request, episode)
            existing = self.session.scalar(select(ClarificationAnswerRecord).where(
                ClarificationAnswerRecord.question_id == answer.question_id))
            if existing:
                if existing.request_id != request_id or existing.payload != answer.model_dump(mode='json'):
                    conflict('Question already answered with different content/identity')
                return AnswerHistory.model_validate(existing.payload)
            row = self.session.get(ClarificationQuestionRecord, answer.question_id)
            if row is None or row.request_id != request_id:
                conflict('Unknown question for workflow')
            answer.validate_for(PendingQuestion.model_validate(row.payload))
            self.session.add(ClarificationAnswerRecord(answer_id=answer.answer_id,
                request_id=request_id, episode_id=answer.episode_id, question_id=answer.question_id,
                payload=answer.model_dump(mode='json')))
            self.session.flush()
            self.session.refresh(row)
            self.session.refresh(request)
            self._snapshot(request)
            return answer

    def close_episode(self, request_id, episode_id, *, status):
        if status not in {'completed', 'failed'}:
            raise ValueError('Episode closure must be terminal')
        with self.session.begin_nested():
            request = self.request(request_id, lock=True)
            episode = self.episode(request_id, episode_id)
            if episode.status == status:
                return self.contract(episode)
            self._active(request, episode)
            for row in self.session.scalars(select(ClarificationQuestionRecord).where(
                    ClarificationQuestionRecord.episode_id == episode_id, ClarificationQuestionRecord.status == 'open')):
                row.status = 'cancelled'
                row.payload = dict(row.payload, status='cancelled')
            episode.status = status
            self.session.flush()
            self._snapshot(request)
            if status == 'failed':
                request.status = 'failed'
                if request.graph_snapshot:
                    snapshot = deepcopy(request.graph_snapshot)
                    snapshot['state']['status'] = 'failed'
                    request.graph_snapshot = snapshot
                self.session.flush()
            return self.contract(episode)

    def claim_final_resolve(self, request_id, episode_id, operation_id):
        conflict('Question exhaustion no longer authorizes final destination resolution')

    def update_policy(self, request_id, episode_id, policy: SelectionPolicy):
        policy = SelectionPolicy.model_validate(policy.model_dump())
        with self.session.begin_nested():
            request = self.request(request_id, lock=True)
            episode = self.episode(request_id, episode_id)
            payload = policy.model_dump(mode='json')
            if payload == episode.selection_policy:
                return self.contract(episode)
            self._active(request, episode)
            if payload != episode.selection_policy:
                if self.questions(request_id, open_only=True):
                    conflict('Cannot change intent while a question or final resolve is open')
                episode.selection_policy = payload
                self.session.flush()
                self._snapshot(request)
            return self.contract(episode)

    def supersede_questions(self, request_id):
        with self.session.begin_nested():
            request = self.request(request_id, lock=True)
            self._active(request, self.episode(request_id))
            for row in self.session.scalars(select(ClarificationQuestionRecord).where(
                    ClarificationQuestionRecord.request_id == request_id,
                    ClarificationQuestionRecord.episode_id == request.active_episode_id,
                    ClarificationQuestionRecord.status == 'open')):
                row.status = 'superseded'
                row.payload = dict(row.payload, status='superseded')
            self.session.flush()
            self._snapshot(request)

    def complete_final_resolve(self, request_id, episode_id, operation_id, result: DestinationResult):
        conflict('Automatic destination defaults are no longer authorized')

    def _snapshot(self, request):
        if request.graph_snapshot is None:
            return
        snapshot = deepcopy(request.graph_snapshot)
        episode = self.contract(self.episode(request.request_id))
        questions = self.questions(request.request_id, open_only=True)
        snapshot['state'].update(status=request.status, clarification_round=request.clarification_round,
            destination_round=episode.destination_round, max_destination_rounds=episode.max_destination_rounds,
            destination_episode=episode.model_dump(mode='json'),
            pending_fields=list(dict.fromkeys(f for q in questions for f in q.fields)))
        snapshot['pending_questions'] = [q.model_dump(mode='json') for q in questions]
        legacy = [a for a in snapshot.get('answers_history', []) if not a.get('question_id')]
        snapshot['answers_history'] = legacy + [a.model_dump(mode='json') for a in self.answers(request.request_id)]
        request.graph_snapshot = snapshot
        self.session.flush()

    def new_workflow_after_failed(self, request_id, destination: Destination, *, raw_prompt: str):
        from app.repositories.artifacts import ArtifactRepository
        destination = Destination.model_validate(destination.model_dump())
        if destination.selection_intent != 'EXPLICIT' or destination.selection_authority != 'USER' or destination.selection_mode != 'explicit' or not destination.city or not destination.city.strip():
            conflict('A new explicit user destination is required')
        with self.session.begin_nested():
            old = self.request(request_id, lock=True)
            if old.status != 'failed':
                conflict('Lifecycle B factory requires a failed workflow')
            artifacts = ArtifactRepository(self.session, self.user_id)
            seed = artifacts.latest(request_id, 'trip_request')
            if seed is None:
                conflict('No validated TripRequest available to seed the new workflow')
            from ai.orchestration.turns import seed_after_failed
            value = seed_after_failed(TripRequest.model_validate(seed.payload), destination, raw_prompt)
            new = RequestRepository(self.session, self.user_id).create(old.trip_id, schema_version=value.schema_version)
            policy = SelectionPolicy.model_validate(destination.model_dump(include=set(SelectionPolicy.model_fields)))
            episode = self.start_episode(new.request_id, policy)
            artifacts.add(new.request_id, 'trip_request', value)
            return new.request_id, episode, value

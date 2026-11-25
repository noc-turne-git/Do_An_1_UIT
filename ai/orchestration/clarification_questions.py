"""Validate wording supplied by an LLM against a CODE-owned question snapshot.

The specification owns every actionable value. A model may only supply wording;
invalid wording falls back to the deterministic template without another call.
"""
from dataclasses import dataclass
from copy import deepcopy
from uuid import UUID
from pydantic import ValidationError

from shared.contracts import (ConstraintProposal, DestinationResult, PendingQuestion,
                              QuestionKind, QuestionOption, SelectionIntent, TRIP_COLLECTION_FIELDS)


def askable_fields(request, kind, fields, *, constraint_proposal=None, parser=False):
    """Gate collection without changing destination choices or recovery proposals."""
    if kind == 'destination_choice' or constraint_proposal is not None:
        return tuple(fields)
    def askable(path):
        if parser or kind == 'trip_request' or path in TRIP_COLLECTION_FIELDS:
            return request.should_ask(path)
        if path in {'destination.city', 'destination.selection_mode', 'destination.selection_intent'}:
            return request.should_ask(path)
        if path in request.meta.field_decisions:
            return False
        value = request.model_dump()
        try:
            for part in path.split('.'):
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, TypeError, ValueError, IndexError):
            return False
        return value is None or value == '' or value == []
    return tuple(path for path in fields if askable(path))


@dataclass(frozen=True)
class QuestionSpec:
    kind: QuestionKind
    fields: tuple[str, ...]
    options: tuple[QuestionOption, ...] = ()
    constraint_proposal: ConstraintProposal | None = None

    def __post_init__(self):
        if not self.fields or any(not field.strip() for field in self.fields):
            raise ValueError('Question needs assigned fields')
        if len(set(self.fields)) != len(self.fields):
            raise ValueError('Assigned fields must be unique')
        if self.kind == 'destination_choice' and not self.options:
            raise ValueError('Choice needs canonical candidates')
        if self.kind != 'destination_choice' and self.options:
            raise ValueError('Only choice may contain candidates')
        if self.kind == 'destination_choice':
            for key in ('option_id', 'candidate_id', 'rank'):
                values = [getattr(option, key) for option in self.options]
                if any(value is None or value == '' for value in values) or len(set(values)) != len(values):
                    raise ValueError('Choice needs unique canonical IDs and ranks')
            if any(not option.reason or not option.reason.strip() for option in self.options):
                raise ValueError('Choice needs canonical reasons')
        if self.constraint_proposal and (self.kind != 'destination_info' or
                not set(self.constraint_proposal.fields) <= set(self.fields)):
            raise ValueError('Constraint proposal does not match requested fields')
        if self.constraint_proposal and self.constraint_proposal.current_values is None:
            raise ValueError('Constraint proposal needs the unchanged current values')


def specifications(result: DestinationResult) -> list[QuestionSpec]:
    """Route one purpose at a time from structured Agent A output."""
    result.require_canonical_recovery()
    if result.selection_status == 'needs_user_choice':
        return [QuestionSpec('destination_choice', ('destination.city',), tuple(
            QuestionOption(option_id=c.candidate_id, candidate_id=c.candidate_id,
                city=c.city, province=c.province, country=c.country, rank=c.rank,
                reason=c.reason) for c in result.candidate_regions))]
    if result.selection_status == 'needs_more_info':
        return [QuestionSpec(info.purpose, tuple(info.fields))
                for info in result.information_requests]
    if result.selection_status == 'no_valid_candidate':
        recovery = result.recovery
        if recovery is None:
            return []
        return [QuestionSpec('destination_info', tuple(recovery.fields),
                             constraint_proposal=recovery.constraint_proposal)]
    return []


def validate_draft(draft: PendingQuestion, spec: QuestionSpec) -> bool:
    """Coverage is over this specification, never all workflow pending fields."""
    try:
        if draft.status != 'legacy' or draft.question_id or draft.episode_id or draft.round:
            return False
        if draft.kind != spec.kind or set(draft.fields) != set(spec.fields):
            return False
        if draft.constraint_proposal != spec.constraint_proposal:
            return False
        if draft.options != list(spec.options):
            return False
        return bool(draft.question.strip())
    except (ValueError, AttributeError):
        return False


def template(spec: QuestionSpec) -> str:
    if spec.kind == 'destination_choice':
        return 'Bạn thích điểm đến nào? Bạn cũng có thể nhờ mình chọn giúp hoặc gợi ý danh sách khác.'
    if spec.constraint_proposal:
        return ('Bạn có đồng ý điều chỉnh các ràng buộc trong đề xuất đính kèm để tìm '
                'điểm đến phù hợp không?')
    from ai.orchestration.request_parser import LABELS
    if all(path in LABELS for path in spec.fields):
        return ' '.join(LABELS[path] for path in spec.fields)
    return 'Bạn có thể bổ sung thông tin để mình xác minh điểm đến và tư vấn chính xác hơn không?'


def prepare_question(spec: QuestionSpec, *, draft: PendingQuestion | dict | None = None) -> PendingQuestion:
    """No identity or budget is assigned during validation or fallback."""
    try:
        candidate = PendingQuestion.model_validate(draft) if draft is not None else None
    except (ValidationError, ValueError, TypeError):
        candidate = None
    wording = candidate.question if candidate is not None and validate_draft(candidate, spec) else template(spec)
    return PendingQuestion(question=wording, fields=list(spec.fields), kind=spec.kind,
        options=deepcopy(list(spec.options)),
        constraint_proposal=deepcopy(spec.constraint_proposal))


def destination_draft(result: DestinationResult, spec: QuestionSpec) -> PendingQuestion | None:
    """Agent owns wording; CODE supplies the exact fields, options and proposal."""
    wording = (result.choice_question if spec.kind == 'destination_choice' else
        result.recovery.question if result.recovery else
        next((info.question for info in result.information_requests
              if info.purpose == spec.kind and tuple(info.fields) == spec.fields), None))
    if not wording:
        return None
    return PendingQuestion(question=wording, fields=list(spec.fields), kind=spec.kind,
        options=list(spec.options), constraint_proposal=spec.constraint_proposal)


def attach_identity(question: PendingQuestion, *, question_id: UUID, episode_id: UUID,
                    intent_snapshot: SelectionIntent, round: int) -> PendingQuestion:
    """Only CODE calls this when issuing the already validated question."""
    if question.status != 'legacy' or question.question_id is not None:
        raise ValueError('Question already has an identity')
    return PendingQuestion.model_validate(question.model_dump() | dict(
        question_id=question_id, episode_id=episode_id, intent_snapshot=intent_snapshot,
        round=round, status='open'))

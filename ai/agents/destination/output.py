"""Strict provider output shape for destination consultation."""
import json
from typing import Literal

from pydantic import Field

from shared.contracts import (CandidateRegion, DestinationResult, InformationRequest,
                              Model, NonEmpty, Region)


class PathValue(Model):
    path: NonEmpty
    value_json: str


class ConstraintProposalOutput(Model):
    proposal_id: NonEmpty
    fields: list[NonEmpty] = Field(min_length=1)
    current_values: list[PathValue] | None = None
    proposed_values: list[PathValue]
    reason: NonEmpty


class DestinationRecoveryOutput(Model):
    reason: NonEmpty
    fields: list[NonEmpty] = Field(min_length=1)
    constraint_proposal: ConstraintProposalOutput | None = None
    question: NonEmpty | None = None


class DestinationAgentOutput(Model):
    request_type: Literal['EXPLICIT', 'IMPLICIT', 'AMBIGUOUS', 'INSUFFICIENT']
    selected_region: Region | None
    selection_status: Literal['selected', 'needs_user_choice', 'no_valid_candidate', 'needs_more_info']
    selection_reason: str
    candidate_regions: list[CandidateRegion]
    missing_fields: list[str]
    information_requests: list[InformationRequest] = Field(default_factory=list)
    recovery: DestinationRecoveryOutput | None = None
    selected_candidate_id: NonEmpty | None = None
    destination_source: Literal['USER', 'AGENT_DELEGATED', 'SYSTEM_DEFAULT'] | None = None
    selection_method: Literal['USER_EXPLICIT', 'USER_CHOICE', 'AGENT_DELEGATED', 'SYSTEM_DEFAULT'] | None = None
    choice_question: NonEmpty | None = None
    schema_version: str = Field(default='1.0', pattern=r'^1\.\d+$')

    def to_destination_result(self) -> DestinationResult:
        data = self.model_dump(mode='python')
        proposal = data.get('recovery', {}).get('constraint_proposal') if data.get('recovery') else None
        if proposal is not None:
            for name in ('current_values', 'proposed_values'):
                entries = proposal[name]
                if entries is None:
                    continue
                values = {}
                for entry in entries:
                    path = entry['path']
                    if path in values:
                        raise ValueError(f'duplicate {name} path: {path}')
                    values[path] = json.loads(entry['value_json'])
                proposal[name] = values
        return DestinationResult.model_validate(data)

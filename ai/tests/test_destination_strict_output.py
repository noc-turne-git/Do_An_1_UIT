"""Strict destination transport and lossless business-contract conversion."""
import asyncio
import pytest
from pydantic import TypeAdapter, ValidationError

from ai.agents.destination.output import DestinationAgentOutput
from ai.agents.destination.agent import DestinationAgent
from ai.agents.llm import LLMRequest, ProviderError
from ai.agents.llm.openai import OpenAILLMAdapter, strict_schema
from ai.orchestration.request_parser import ParserOutput
from ai.orchestration.request_parser import empty_request
from ai.orchestration.destination_response import DestinationWording
from shared.contracts import DestinationResult


def test_destination_output_schema_is_strict_compatible():
    schema = TypeAdapter(DestinationAgentOutput).json_schema()
    strict_schema(schema)
    assert DestinationAgentOutput.model_fields.keys() == DestinationResult.model_fields.keys()
    assert TypeAdapter(DestinationResult).json_schema()['$defs']['ConstraintProposal']['properties']['proposed_values']['additionalProperties']
    strict_schema(TypeAdapter(ParserOutput).json_schema())
    strict_schema(TypeAdapter(DestinationWording).json_schema())


def test_conversion_rejects_duplicate_or_invalid_values():
    base = {'request_type': 'IMPLICIT', 'selected_region': None,
            'selection_status': 'no_valid_candidate', 'selection_reason': '',
            'candidate_regions': [], 'missing_fields': [],
            'recovery': {'reason': 'No match', 'fields': ['budget.amount'],
                'constraint_proposal': {'proposal_id': 'p', 'fields': ['budget.amount'],
                    'current_values': None, 'proposed_values': [{'path': 'budget.amount', 'value_json': '1'}],
                    'reason': 'More budget'}}}
    assert DestinationAgentOutput.model_validate(base).to_destination_result().recovery.constraint_proposal.current_values is None
    base['recovery']['constraint_proposal']['proposed_values'].append({'path': 'budget.amount', 'value_json': '2'})
    with pytest.raises(ValueError, match='duplicate proposed_values path'):
        DestinationAgentOutput.model_validate(base).to_destination_result()
    base['recovery']['constraint_proposal']['proposed_values'] = [{'path': 'budget.amount', 'value_json': '1'}]
    base['recovery']['constraint_proposal']['fields'] = ['trip.start_date']
    with pytest.raises(ValidationError, match='proposal values must match unique fields'):
        DestinationAgentOutput.model_validate(base).to_destination_result()
    base['recovery']['constraint_proposal']['fields'] = ['budget.amount']
    base['recovery']['constraint_proposal']['proposed_values'][0]['value_json'] = '{invalid'
    with pytest.raises(ValueError):
        DestinationAgentOutput.model_validate(base).to_destination_result()


def test_destination_agent_uses_transport_model_and_returns_business_contract(monkeypatch):
    async def generate(self, name, prompt, schema, data):
        assert name == 'destination_agent'
        assert schema is DestinationAgentOutput
        return schema.model_validate({'request_type': 'IMPLICIT', 'selected_region': None,
            'selection_status': 'no_valid_candidate', 'selection_reason': 'No match',
            'candidate_regions': [], 'missing_fields': []})

    monkeypatch.setattr(DestinationAgent, '_generate', generate)
    result = asyncio.run(DestinationAgent(None).select(empty_request()))
    assert isinstance(result, DestinationResult)

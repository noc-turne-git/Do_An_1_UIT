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


def test_constraint_values_round_trip_without_inference():
    raw = {
        'request_type': 'IMPLICIT', 'selected_region': None,
        'selection_status': 'no_valid_candidate', 'selection_reason': 'Budget conflict',
        'candidate_regions': [], 'missing_fields': [],
        'recovery': {'reason': 'Budget conflict', 'fields': ['budget.amount', 'preferences.interests'],
            'constraint_proposal': {'proposal_id': 'p1',
                'fields': ['budget.amount', 'preferences.interests'],
                'current_values': [
                    {'path': 'budget.amount', 'value_json': 'null'},
                    {'path': 'preferences.interests', 'value_json': '["food", "beach"]'}],
                'proposed_values': [
                    {'path': 'budget.amount', 'value_json': '5000000'},
                    {'path': 'preferences.interests', 'value_json': '[]'}],
                'reason': 'Expand search'}}}
    output = DestinationAgentOutput.model_validate(raw)
    result = output.to_destination_result()
    assert isinstance(result, DestinationResult)
    proposal = result.recovery.constraint_proposal
    assert proposal.current_values == {'budget.amount': None, 'preferences.interests': ['food', 'beach']}
    assert proposal.proposed_values == {'budget.amount': 5000000, 'preferences.interests': []}
    assert result.model_dump(mode='json')['recovery']['constraint_proposal']['fields'] == raw['recovery']['constraint_proposal']['fields']


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


def test_adapter_rejects_dynamic_schema_before_provider_call():
    class Client:
        def __init__(self):
            self.responses = self
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            raise AssertionError('provider must not be called')

    client = Client()
    adapter = OpenAILLMAdapter(model='test', client=client)
    request = LLMRequest(messages=[{'role': 'user', 'content': 'test'}], tools=[],
        output_schema=TypeAdapter(DestinationResult).json_schema())
    with pytest.raises(ProviderError) as caught:
        asyncio.run(adapter.respond(request))
    assert caught.value.code == 'LLM_ADAPTER_ERROR'
    assert '$/$defs/ConstraintProposal/properties/current_values/anyOf/0' in caught.value.diagnostic['message']
    assert client.calls == 0


def test_adapter_rejects_object_without_explicit_closed_properties():
    with pytest.raises(ValueError, match=r'\$/properties/nested'):
        strict_schema({'type': 'object', 'additionalProperties': False,
            'properties': {'nested': {'type': 'object', 'properties': {'x': {'type': 'string'}}}}})

"""Destination consultation and wording through the existing bounded harness."""
from uuid import uuid4

from ai.agents.contracts import AgentContext, AgentDefinition, AgentStatus, ExecutionLimits
from ai.agents.runtime.context import execution_identity
from ai.agents.runtime.factory import create_agent_harness
from ai.agents.destination.prompts import PROMPT, CONFIRMATION_PROMPT
from ai.agents.destination.output import DestinationAgentOutput
from ai.orchestration.destination_response import DestinationWording, trip_facts
from shared.errors import ApplicationError


class DestinationAgent:
    def __init__(self, settings):
        self.settings = settings

    async def _generate(self, name, prompt, schema, data):
        definition = AgentDefinition(name=name, description='Destination consultation',
            system_prompt=prompt, output_schema=schema,
            limits=ExecutionLimits(max_steps=1, max_tool_calls=0, max_retries=1,
                timeout=self.settings.llm_timeout_seconds * 2 + 2,
                llm_timeout=self.settings.llm_timeout_seconds))
        harness = create_agent_harness(definition, self.settings)
        identity = execution_identity.get() or {}
        try:
            result = await harness.run(definition, AgentContext(
                request_id=identity.get('request_id') or str(uuid4()),
                metadata=identity.get('metadata', {}), input_data=data))
            if result.status != AgentStatus.SUCCESS:
                raise ApplicationError('llm_output_invalid', 'Destination consultation could not complete')
            return result.output
        finally:
            close = getattr(harness.llm, 'aclose', None)
            if close:
                await close()

    async def select(self, request, *, context=None):
        output = await self._generate('destination_agent', PROMPT, DestinationAgentOutput,
            dict(request=request.model_dump(mode='json'), context=context or {}))
        try:
            return output.to_destination_result()
        except ValueError as exc:
            raise ApplicationError('llm_output_invalid', 'Destination consultation output is invalid') from exc

    async def confirmation(self, request, result):
        return await self._generate('destination_confirmation', CONFIRMATION_PROMPT,
            DestinationWording, dict(facts=trip_facts(request),
                decision_source=result.destination_source, reason=result.selection_reason))

"""Opt-in mock integration that retains existing component/domain behavior."""
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from app.core.errors import ApplicationError
from app.models.contracts import TripRequest, DestinationResult, TimeConstraints, PlaceCandidate, BudgetResult
from app.services.mock_workflow import mock_components
from app.agents.runtime.context import execution_identity
from app.agents.contracts import AgentDefinition, AgentContext, AgentStatus
from app.agents.tools import ToolDefinition, ToolRegistry
from app.agents.skills import SkillDefinition, SkillRegistry
from app.agents.runtime.harness import AgentHarness
from app.agents.llm import LLMResponse, ToolCall

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request: TripRequest

class PlaceInput(Input):
    destination: DestinationResult
    time_constraints: TimeConstraints
    max_candidates: int = Field(ge=1)
    exclude_place_ids: list[str]

class BudgetInput(Input):
    places: list[PlaceCandidate]
    must_visit_place_ids: list[str]

class MockToolLLMAdapter:
    """No reasoning: request the configured mock tool, then return its typed data."""
    def __init__(self, tool_name):
        self.tool_name = tool_name

    async def respond(self, request):
        results = [m for m in request.messages if m['role'] == 'tool']
        if results:
            if results[-1]['error']:
                # Harness captures this as a technical LLM failure. No raw exceptions escape.
                raise RuntimeError('Mock tool failed')
            return LLMResponse(kind='final', output=results[-1]['output'])
        data = next(m['content'] for m in request.messages if m['role'] == 'user')
        return LLMResponse(kind='tools', tool_calls=[ToolCall(id='mock-1',name=self.tool_name,arguments=data)])

class RuntimeComponent:
    def __init__(self, definition, harness, skill):
        self.definition, self.harness, self.skill = definition, harness, skill

    async def execute(self, data):
        identity = execution_identity.get() or {'request_id':str(uuid4())}
        result = await self.harness.run(self.definition, AgentContext(**identity,input_data=data),skills=[self.skill])
        if result.status == AgentStatus.FAILED:
            raise ApplicationError(result.error.code, result.error.message, retryable=result.error.retryable)
        if result.status == AgentStatus.NEEDS_INPUT:
            # Domain clarification is represented by existing business output schemas.
            raise ApplicationError('runtime_needs_input', 'Runtime requires input; use domain clarification output')
        return result.output

class RuntimeDestinationAgent(RuntimeComponent):
    async def select(self, request):
        return await self.execute({'request':request.model_dump(mode='json')})

class RuntimeRecommendationAgent(RuntimeComponent):
    async def find(self, request, destination, time_constraints, *, max_candidates, exclude_place_ids):
        return await self.execute(dict(request=request.model_dump(mode='json'),
            destination=destination.model_dump(mode='json'), time_constraints=time_constraints.model_dump(mode='json'),
            max_candidates=max_candidates, exclude_place_ids=exclude_place_ids))

class RuntimeBudgetAgent(RuntimeComponent):
    async def estimate(self, request, places, *, must_visit_place_ids):
        return await self.execute(dict(request=request.model_dump(mode='json'),
            places=[p.model_dump(mode='json') for p in places], must_visit_place_ids=must_visit_place_ids))


def runtime_mock_components(*, limits=None):
    """Inject through LangGraphOrchestrator(components=...). No providers or DB required."""
    components = mock_components()
    destination, recommendation, budget = components.destination_agent, components.place_agent, components.budget_module
    tools, skills = ToolRegistry(), SkillRegistry()
    async def details(data):
        return await destination.select(data.request)
    async def search(data):
        return await recommendation.find(data.request, data.destination, data.time_constraints,
            max_candidates=data.max_candidates, exclude_place_ids=data.exclude_place_ids)
    async def estimate(data):
        return await budget.estimate(data.request, data.places, must_visit_place_ids=data.must_visit_place_ids)
    specs = [
        ('destination_agent','get_place_details',Input,DestinationResult,details,'destination_research',RuntimeDestinationAgent),
        ('place_agent','search_places',PlaceInput,list[PlaceCandidate],search,'place_recommendation',RuntimeRecommendationAgent),
        ('budget_module','estimate_place_cost',BudgetInput,BudgetResult,estimate,'budget_analysis',RuntimeBudgetAgent),
    ]
    for name, tool, input_schema, output_schema, handler, skill, adapter in specs:
        tools.register(ToolDefinition(name=tool,description='Offline fixture lookup',input_schema=input_schema,
            output_schema=output_schema,handler=handler,side_effects=False))
        skills.register(SkillDefinition(name=skill, description='Mock instructions',
            instructions='Use registered mock data only. Return the existing business schema.'))
        definition = AgentDefinition(name=name, description='Mock runtime component', system_prompt='Use the mock tool.',
            allowed_tools={tool}, allowed_skills={skill}, output_schema=output_schema,
            **({'limits':limits} if limits is not None else {}))
        setattr(components,name,adapter(definition,AgentHarness(MockToolLLMAdapter(tool),tools,skills),skill))
    return components

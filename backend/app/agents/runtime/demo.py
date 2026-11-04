"""Run the opt-in mock runtime through the existing graph: python -m app.agents.runtime.demo."""
import asyncio
from datetime import date
from app.models.contracts import TripRequest
from app.services.graph_workflow import LangGraphOrchestrator
from app.services.mock_workflow import fixture
from app.agents.adapters.mock import runtime_mock_components

async def main():
    graph = LangGraphOrchestrator(runtime_mock_components(), defaults=fixture('planner_defaults'))
    result = await graph.run(TripRequest.model_validate(fixture('trip_request')), current_date=date(2026,11,4))
    print(f'Status: {result.state.status}; transitions: {result.transitions}; artifacts: {len(result.artifacts)}')
    for name in ('destination_agent','place_agent','budget_module'):
        component = getattr(graph.components,name)
        print(f'{name}: {component.definition.name} / tools: {sorted(component.definition.allowed_tools)}')
    if result.state.status != 'completed':
        raise RuntimeError('Mock runtime demonstration did not complete')

if __name__ == '__main__':
    asyncio.run(main())

"""Composition only. No execution loop or business agent selection."""
from app.agents.llm import MockLLMAdapter
from app.agents.runtime.harness import AgentHarness


def create_agent_harness(definition, settings, *, tools=None, skills=None,
                         llm=None, mock_responses=(), client=None):
    if llm is None:
        if settings.llm_provider == 'mock':
            llm = MockLLMAdapter(mock_responses)
        elif settings.llm_provider == 'openai':
            from app.agents.llm.openai import OpenAILLMAdapter
            key = settings.openai_api_key or settings.llm_api_key
            if key is None and client is None:
                raise ValueError('OPENAI_API_KEY or LLM_API_KEY is required')
            model = settings.openai_model or settings.llm_model
            if model == 'mock-model':
                raise ValueError('Configure OPENAI_MODEL or LLM_MODEL for OpenAI')
            llm = OpenAILLMAdapter(model=model, base_url=settings.openai_base_url,
                api_key=key.get_secret_value() if key else None,
                timeout=settings.llm_timeout_seconds, client=client)
        else:
            raise ValueError('Unsupported LLM provider')
    return AgentHarness(llm, tools, skills)

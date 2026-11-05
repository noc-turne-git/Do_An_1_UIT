"""Canonical modules and the runtime package API import in either order."""
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('module', ['contracts', 'tools', 'skills', 'llm', 'adapters.mock'])
@pytest.mark.parametrize('runtime_first', [False, True])
def test_canonical_import_in_fresh_process(module, runtime_first):
    script = f'''
import importlib
if {runtime_first!r}:
    importlib.import_module('ai.agents.runtime')
canonical = importlib.import_module('ai.agents.{module}')
legacy = importlib.import_module('ai.agents.runtime')
exports = {{
    'contracts': ('AgentDefinition', 'AgentContext', 'ExecutionLimits'),
    'tools': ('ToolDefinition', 'ToolRegistry', 'ToolExecutor', 'ToolResult'),
    'skills': ('SkillDefinition', 'SkillRegistry', 'SkillLoader', 'SkillActivationError'),
    'llm': ('LLMAdapter', 'LLMRequest', 'LLMResponse', 'ToolCall', 'MockLLMAdapter', 'TransientLLMError'),
    'adapters.mock': ('RuntimeComponent', 'RuntimeDestinationAgent', 'RuntimeRecommendationAgent', 'RuntimeBudgetAgent', 'runtime_mock_components'),
}}
if '{module}' == 'adapters.mock':
    # Adapters are implementations, not part of the runtime package facade.
    importlib.import_module('ai.orchestration.graph_workflow')
    assert canonical.runtime_mock_components().destination_agent is not None
    raise SystemExit(0)
for name in exports['{module}']:
    assert getattr(canonical, name) is getattr(legacy, name), name
'''
    subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[2],
                   check=True, capture_output=True, text=True)

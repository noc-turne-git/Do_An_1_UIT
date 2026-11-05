"""Skills are validated instruction data, never executable plugins."""
import json
from pathlib import Path
from typing import Any
from pydantic import Field
from ai.agents.contracts import Contract

class SkillDefinition(Contract):
    name: str = Field(min_length=1, pattern=r'^[a-z][a-z0-9_]*$')
    description: str = Field(min_length=1)
    instructions: str = Field(min_length=1, pattern=r'\S')
    metadata: dict[str, Any] = Field(default_factory=dict)
    required_tools: frozenset[str] = frozenset()

class SkillLoader:
    @staticmethod
    def from_markdown(text: str):
        # JSON front matter keeps loading dependency free and forbids YAML object tags.
        parts = text.split('---', 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError('Expected --- JSON metadata --- followed by Markdown instructions')
        data = json.loads(parts[1])
        if not isinstance(data, dict) or 'instructions' in data:
            raise ValueError('Invalid skill metadata')
        return SkillDefinition(**data, instructions=parts[2].strip())

    @classmethod
    def load(cls, path: str | Path):
        return cls.from_markdown(Path(path).read_text(encoding='utf-8-sig'))

class SkillActivationError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

class SkillRegistry:
    def __init__(self):
        self._skills = {}

    def register(self, skill: SkillDefinition):
        if skill.name in self._skills:
            raise ValueError(f'Duplicate skill: {skill.name}')
        self._skills[skill.name] = skill.model_copy(deep=True)

    def lookup(self, name):
        skill = self._skills.get(name)
        return skill.model_copy(deep=True) if skill else None

    def list(self):
        return tuple(s.model_copy(deep=True) for s in self._skills.values())

    def activate(self, names, *, allowed_skills):
        selected = []
        for name in dict.fromkeys(names):
            if name not in allowed_skills:
                raise SkillActivationError('SKILL_NOT_ALLOWED')
            skill = self.lookup(name)
            if skill is None:
                raise SkillActivationError('SKILL_NOT_FOUND')
            selected.append(skill)
        return selected

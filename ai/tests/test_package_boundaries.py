import ast
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError
from shared.contracts import TripRequest
from shared.validation import validate_trip_request
from ai.orchestration.mock_workflow import fixture


def test_ai_does_not_import_backend():
    for path in Path(__file__).resolve().parents[1].rglob('*.py'):
        if 'tests' in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('app.'), path
            elif isinstance(node, ast.Import):
                assert not any(alias.name.startswith('app.') for alias in node.names), path

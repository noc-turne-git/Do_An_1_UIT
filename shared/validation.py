"""Validate the versioned wire contract, independently of internal Pydantic models."""
import json
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker


@lru_cache
def trip_request_validator():
    schema = json.loads((Path(__file__).parent / 'schemas' / 'trip_request.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_trip_request(payload):
    trip_request_validator().validate(payload)

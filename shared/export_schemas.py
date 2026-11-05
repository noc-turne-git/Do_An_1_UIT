"""Regenerate public wire schemas: python -m shared.export_schemas."""
import json
import re
from pathlib import Path
from shared import contracts


def export():
    target = Path(__file__).parent / 'schemas'
    target.mkdir(exist_ok=True)
    for name in ('TripRequest', 'DestinationResult', 'PlaceCandidate', 'CostedPlaceCandidate',
                 'TimeConstraints', 'PlanningInput', 'Itinerary', 'ValidationResult', 'WorkflowState'):
        schema = getattr(contracts, name).model_json_schema()
        schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
        filename = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower() + '.json'
        (target / filename).write_text(json.dumps(schema, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    export()

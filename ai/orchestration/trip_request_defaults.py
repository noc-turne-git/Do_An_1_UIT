"""Apply the closed TripRequest default table only to exhausted trip requirements."""
from copy import deepcopy

from shared.contracts import TRIP_NEVER_DEFAULT, TripRequest
from shared.errors import ApplicationError


def apply_trip_defaults(request, requirements, *, policy, exhausted, question_open):
    if not exhausted or question_open:
        return request
    fields = {field for spec in requirements if spec.kind == 'trip_request'
              for field in spec.fields if not field.startswith('destination.')}
    data = request.model_dump()
    unresolved = []
    for path in sorted(fields):
        parts = path.split('.')
        if len(parts) != 2 or parts[0] not in data or parts[1] not in data[parts[0]]:
            unresolved.append(path)
            continue
        value = data[parts[0]][parts[1]]
        if value is not None and value != '':
            continue  # User values, including zero and empty lists, are constraints.
        if path in TRIP_NEVER_DEFAULT:
            unresolved.append(path)
        elif path == 'budget.amount':
            # No monetary default and no fabricated user provenance.
            data['meta'].setdefault('field_decisions', {})[path] = 'UNKNOWN'
        elif path in policy.default_table:
            data[parts[0]][parts[1]] = deepcopy(policy.default_table[path])
            data['meta']['field_sources'][path] = 'default'
            data['meta']['field_confidences'].pop(path, None)
        else:
            unresolved.append(path)
    if unresolved:
        raise ApplicationError('planning_input_inconsistent',
            'Required trip information remains unresolved after clarification: ' + ', '.join(unresolved))
    return TripRequest.model_validate(data)

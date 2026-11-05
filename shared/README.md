Public JSON contracts live in `schemas/`; sample wire payloads live in `samples/`.

`contracts.py` is the single Python implementation of those contracts, imported by both Backend and AI. Regenerate JSON Schema with `python -m shared.export_schemas`; the drift test and CI keep the schema and Python models consistent. `validation.validate_trip_request` enforces the JSON wire schema at AI entry points; Pydantic additionally enforces date consistency and other cross-field rules.

API request/response models stay in Backend. Agent execution, tool, skill and provider models stay in AI. They are internal types, not additional public wire contracts.

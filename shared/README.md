Public JSON contracts live in `schemas/`; sample wire payloads live in `samples/`.

`contracts.py` is the single Python implementation of those contracts, imported by both Backend and AI. Regenerate JSON Schema with `python -m shared.export_schemas`; the drift test and CI keep the schema and Python models consistent. `validation.validate_trip_request` enforces the JSON wire schema at AI entry points; Pydantic additionally enforces date consistency and other cross-field rules.

API request/response models stay in Backend. Agent execution, tool, skill and provider models stay in AI. They are internal types, not additional public wire contracts.

Canonical clarification contracts include `DestinationEpisode`, `PendingQuestion`,
`QuestionOption` and `AnswerHistory`. `WorkflowState.destination_episode` owns the
destination budget; its top-level destination counters are checked projections.
Legacy deserialization defaults to UNSPECIFIED/none and question status `legacy`.
Use `require_actionable()` and `AnswerHistory.validate_for(question)` at operation
boundaries; successful deserialization alone is not permission to accept a choice.
`DestinationResult.require_canonical_recovery()` requires structured routing data
before a legacy result can drive a new clarification. Cross-field invariants are
enforced by Pydantic in addition to the exported JSON Schema shape checks.

# Context and tool output

- Before investigating behavior across modules, consult `docs/architecture/Architecture.md` for entry points, ownership boundaries, and the first file/function to read for the symptom. Follow its links only when the issue needs deeper policy or workflow detail.
- Update architecture documentation only when the implemented architecture or ownership boundaries actually change; ordinary fixes and new investigation findings do not require a documentation edit.
- IDE-provided open-file snippets and selections may be incidental. Use those relevant to the task; avoid reprinting attached logs. IDE attachment controls belong in the Codex composer, not in these instructions.
- For workflow investigations, start with `python -B -m ai.trace_view --run-id <run_id> --mode summary`. Narrow with `--step` or `--agent`, then use `--mode verbose` or inspect referenced payloads when needed. Preserve event sequence numbers and payload paths for follow-up.
- Scope `rg` searches to relevant files or modules. Locate symbols, then read complete relevant functions/classes and their callers or dependencies as needed. Avoid unscoped recursive searches through dependencies, build/database artifacts, generated schemas, or all conversation logs.
- Reduce output at the command: select JSON fields, aggregate records, filter searches, or paginate results. Return locations and omitted-result counts when available. If output is truncated, retrieve the missing relevant portion before concluding.
- Reuse sufficient information from unchanged code already read in the session. Read again when files change, comparison is necessary, or evidence is incomplete.
- These are starting strategies, not hard limits on files, lines, reads, or tool calls. Expand to full source files and raw logs whenever the investigation requires them.
- Context optimization must preserve raw-log recording. Do not change the Codex model, reasoning effort, or `tool_output_token_limit` without explicit authorization.

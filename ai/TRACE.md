Runtime chat traces are enabled automatically at the FastAPI ASGI boundary for
`POST /api/v1/chat/messages`. Importing modules and offline calls cannot write
traces. Set `TRAVELIO_TRACE_MODE=off` to disable, or `testing` in a test server's
environment (including tests that launch a separate server process).

Each `ai/logs/conversations/<conversation_id>/runs/<run_id>/` contains:

- `summary.md`: ordered Markdown, state changes, decisions and turn totals.
- `events.jsonl`: structured events with trace/span ancestry and separate HTTP
  request, workflow, trip and turn IDs.
- `payloads/<sha256>.json`: redacted content stored once per run; `$payload`
  references can contain further references.

Read without starting the application:

```powershell
python -m ai.trace_view --run-id <run-id>
python -m ai.trace_view --conversation-id <conversation-id> --mode detailed
python -m ai.trace_view --run-id <run-id> --mode verbose --agent chat_request_parser
python -m ai.trace_view --run-id <run-id> --step destination_agent
```

`python -m ai.logging` supports the same options. The viewer resolves payload
references, accepts `--root`, and can read older inline JSONL events.
Summary omits SQL; detailed includes SQL and parameters. SQL completion means
execution, while transaction events report commit/rollback separately. Turn
totals distinguish business DB events from SQL statements. LLM counts include
attempts/retries; token totals cover responses with reported usage.

Pytest/unittest processes, TestClient and HTTPX ASGITransport are disabled at the
write boundary; test configuration skips logger setup. Custom test transports or
tests against a separate running server must use `TRAVELIO_TRACE_MODE=testing`.
No retention deletion occurs. Redaction covers credential patterns, sensitive
keys and emails; arbitrary personal information in prose still needs care.
Writes are best effort and process-local; this is not a distributed trace store.

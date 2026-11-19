"""Read-only trace viewer. Never initializes the application or writes logs."""
import argparse
import hashlib
import json
from pathlib import Path


def resolve(value, directory):
    if isinstance(value, dict):
        if set(value) == {'$payload'}:
            digest = value['$payload']
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                return value
            return resolve(json.loads((directory / 'payloads' / (digest + '.json')).read_text(encoding='utf-8')), directory)
        return {k: resolve(v, directory) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, directory) for v in value]
    return value


def short(value, limit=350):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace('\n', ' ').replace('\r', ' ')
    return text if len(text) <= limit else text[:limit] + '… [see detailed trace]'


def summary_line(event):
    kind, phase = event.get('event_type', ''), event.get('phase')
    data = event.get('result') or {}
    incoming = event.get('input') or {}
    if not isinstance(data, dict):
        data = {'output': data}
    if not isinstance(incoming, dict):
        incoming = {'input': incoming}
    # Provider and adapter events remain available in verbose, without repeating
    # every prompt, schema, lifecycle marker and SQL statement in the summary.
    if kind == 'database.statement' or (kind == 'span' and phase == 'started'):
        return ''
    if kind in {'workflow.node', 'workflow.validation', 'workflow.run'} and phase == 'started':
        return ''
    if kind == 'agent.event' and phase not in {'failed', 'cancelled', 'needs_input', 'llm_retry'}:
        return ''
    if kind == 'llm.request':
        return ''  # Actual provider messages below are authoritative.
    if kind in {'llm.provider_raw_response', 'agent.execution'} or (kind == 'llm.attempt' and phase == 'started'):
        return ''
    if kind == 'agent.tool' and phase == 'called':
        return ''
    label = f"- {event.get('sequence', '?')}. **{event.get('step_name') or event.get('step')} · {phase}**"
    if kind == 'chat.turn' and phase == 'conversation_loaded':
        detail = {'user_input': data.get('user_input'), 'previous_context': incoming}
    elif kind == 'workflow.route':
        detail = {'current_node': data.get('current_node'), 'next_node': data.get('target'),
                  'reason': data.get('reason'), 'missing_fields': data.get('missing_fields'),
                  'pending_questions': data.get('pending_questions'), 'evaluated': data.get('evaluated')}
    elif kind == 'state.update':
        lines = [label + f" ({short(data.get('component'))}; {short(data.get('reason'))})"]
        for change in data.get('changes', []):
            lines.append(f"  - `{change['field']}`: {short(change['old_value'], 160)} → {short(change['new_value'], 160)}")
        return '\n'.join(lines)
    elif kind == 'code.transformation':
        detail = {'source': data.get('source'), 'changes': data.get('changes')}
    elif kind == 'llm.provider_request':
        provider = incoming.get('provider_payload', {})
        messages = []
        for message in provider.get('input', []):
            content = message.get('content', message)
            if message.get('role') == 'system':
                encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode('utf-8')
                digest = hashlib.sha256(encoded).hexdigest()
                prompt = (f'[system prompt {digest[:12]}](payloads/{digest}.json)'
                          if len(encoded) >= 256 and event.get('schema_version', 2) >= 3 else short(content, 100))
                messages.append(prompt)
            else:
                messages.append(f"{message.get('role') or message.get('type')}: {short(content, 180)}")
        return (label + f" model={provider.get('model')} provider={data.get('provider', 'openai-compatible')} · "
                + ' · '.join(messages))
    elif kind == 'llm.provider_response':
        detail = data
    elif kind == 'workflow.stage_input':
        detail = {'component': incoming.get('component'), 'arguments': incoming.get('arguments')}
    elif kind == 'database.read':
        detail = data
    elif kind == 'chat.turn' and phase == 'response_staged':
        detail = {'status': data.get('workflow_status') or data.get('parser_status'),
                  'assistant': data.get('assistant_message'), 'questions': data.get('question_ids')}
    elif kind == 'span':
        detail = {'duration_ms': event.get('duration_ms'), 'error': event.get('error')}
    elif kind.startswith('database.'):
        detail = {'operation': data.get('operation') or incoming.get('operation') or event.get('step'),
                  'transaction_status' if kind == 'database.transaction' else 'stage': phase,
                  'error': event.get('error')}
    else:
        detail = data or incoming
    return label + ' ' + short(detail, 900 if kind == 'http.turn' else 500) + (
        ' ERROR: ' + short(event['error']) if event.get('error') else '')


def main():
    from ai.logging import DEFAULT_TRACE_ROOT, trace_paths
    parser = argparse.ArgumentParser(description='Read Travelio traces (no runtime execution)')
    parser.add_argument('--conversation-id')
    parser.add_argument('--run-id')
    parser.add_argument('--root', type=Path, default=DEFAULT_TRACE_ROOT)
    parser.add_argument('--mode', choices=('summary', 'detailed', 'verbose'), default='summary')
    parser.add_argument('--step')
    parser.add_argument('--agent')
    args = parser.parse_args()
    if not args.conversation_id and not args.run_id:
        parser.error('Provide --conversation-id or --run-id')
    for path in trace_paths(conversation_id=args.conversation_id, run_id=args.run_id, root=args.root):
        print(f'\n# {path.parent}\n')
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                event = resolve(json.loads(line), path.parent)
            except (ValueError, OSError):
                continue  # An interrupted final append must not hide earlier events.
            if args.step and args.step not in (event.get('step') or ''):
                continue
            result = event.get('result')
            agent = event.get('agent') or (result.get('agent') if isinstance(result, dict) else None)
            if args.agent and args.agent != agent:
                continue
            rendered = summary_line(event) if args.mode == 'summary' else json.dumps(event, ensure_ascii=False, indent=2)
            if rendered:
                print(rendered)


if __name__ == '__main__':
    main()

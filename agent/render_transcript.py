#!/usr/bin/env python3
"""Turn a `claude -p --output-format stream-json` log into a readable transcript, the final report and a summary of receipts."""
import sys, json, os

out = sys.argv[1]
import glob
rows = []
parts = [os.path.join(out, 'transcript.jsonl')] + sorted(glob.glob(os.path.join(out, 'transcript_resume*.jsonl')))
for pi, path in enumerate(parts):
    if pi > 0:                                                  # a marker row: the session was cut off and continued with this exact message
        msg = open(os.path.join(out, f'RESUME_PROMPT_{pi}.md')).read().strip() if os.path.exists(os.path.join(out, f'RESUME_PROMPT_{pi}.md')) else ''
        rows.append(dict(type='resume', part=pi + 1, message=msg))
    for l in open(path):
        l = l.strip()
        if l:
            try:
                rows.append(json.loads(l))
            except Exception:
                pass
md = ['# Agent session transcript', '', '**Prompt** (exact):', '', '```', open(os.path.join(out, 'PROMPT.md')).read().strip(), '```', '']
calls = {}; n_tool = {}; final = None; model = None; result = None; results = []; seen_init = False
for r in rows:
    t = r.get('type')
    if t == 'resume':
        md += ['---', '', f'**The session was cut off here by a usage limit.** It was continued later in the same conversation with this exact message:', '', '```', r['message'], '```', '']
    elif t == 'system' and r.get('subtype') == 'init' and seen_init:
        continue
    elif t == 'system' and r.get('subtype') == 'init':
        seen_init = True
        model = r.get('model'); md += [f'*Model: `{model}` · tools offered: {", ".join(x for x in r.get("tools", []) if "windmirror" in x or x == "Read")}*', '']
    elif t == 'assistant':
        for c in r['message'].get('content', []):
            if c['type'] == 'text' and c['text'].strip():
                md += [c['text'].strip(), '']; final = c['text'].strip()
            elif c['type'] == 'tool_use':
                name = c['name'].replace('mcp__windmirror__', '')
                n_tool[name] = n_tool.get(name, 0) + 1; calls[c['id']] = name
                md += [f'**→ {name}**', '', '```json', json.dumps(c['input'], indent=1)[:2500], '```', '']
    elif t == 'user':
        for c in r['message'].get('content', []) if isinstance(r['message'].get('content'), list) else []:
            if c.get('type') == 'tool_result':
                body = c.get('content')
                if isinstance(body, list):
                    body = '\n'.join(x.get('text', '[image]') if isinstance(x, dict) else str(x) for x in body)
                body = str(body)
                md += [f'**← {calls.get(c.get("tool_use_id"), "result")}**', '', '```', body[:3000] + ('\n… (cut)' if len(body) > 3000 else ''), '```', '']
    elif t == 'result':
        result = r; results.append(r)
open(os.path.join(out, 'TRANSCRIPT.md'), 'w').write('\n'.join(md))
summ = dict(model=model, tool_calls=n_tool)
if result:
    summ['parts'] = len(results)
    summ['is_error'] = bool(result.get('is_error'))
    for k in ('duration_ms', 'duration_api_ms', 'num_turns', 'total_cost_usd'):
        summ[k] = round(sum(x.get(k, 0) or 0 for x in results), 4)
    summ['output_tokens'] = sum((x.get('usage') or {}).get('output_tokens', 0) for x in results)
    summ['input_tokens_incl_cache'] = sum(sum((x.get('usage') or {}).get(k, 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')) for x in results)
    final = result.get('result') or final
mc = os.path.join(out, 'mcp_calls.jsonl')
if os.path.exists(mc):
    C = [json.loads(l) for l in open(mc)]
    summ['solver_runs'] = sum(1 for c in C if c['tool'] == 'solve')
    summ['solver_seconds'] = round(sum(c['result'].get('solver', {}).get('seconds', 0) for c in C if c['tool'] == 'solve'), 1)
    summ['bodies_screened'] = sum((c['result'].get('n_sampled') or 0) for c in C if c['tool'] == 'search') + sum((c['result'].get('n') or 0) for c in C if c['tool'] == 'check')
    summ['tool_seconds'] = round(sum(c['seconds'] for c in C), 1)
json.dump(summ, open(os.path.join(out, 'summary.json'), 'w'), indent=1)
open(os.path.join(out, 'REPORT.md'), 'w').write((final or '(no final message)') + '\n')
print(json.dumps(summ, indent=1))

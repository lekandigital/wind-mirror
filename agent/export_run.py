#!/usr/bin/env python3
"""Turn an agent run's tool-call log into a small JSON the replay page (web/agent.html) plays back.
Usage: python agent/export_run.py <run_dir> <out.json>"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'engine', 'windtunnel'))
import bodies as B
from engine import spec_pose

run, out = sys.argv[1], sys.argv[2]
C = [json.loads(l) for l in open(os.path.join(run, 'mcp_calls.jsonl'))]
summ = json.load(open(os.path.join(run, 'summary.json')))
ev = []; n_solve = 0; screened = 0; best = None; base = None
for c in C:
    r, a = c['result'], c.get('args') or {}
    if 'error' in r:
        continue
    if c['tool'] == 'search':
        screened += r.get('n_sampled', 0)
        bs = r['best_sure'][0]['push_kg_at_100kmh'] if r.get('best_sure') else None
        bu = r['best_unsure'][0]['push_kg_at_100kmh'] if r.get('best_unsure') else None
        ev.append(dict(tool='search', n=r['n_sampled'], ok=r['n_meeting_constraints'], sure=r['n_sure'], best_sure_kg=bs, best_unsure_kg=bu, screened=screened, seconds=c['seconds']))
    elif c['tool'] == 'check':
        screened += r.get('n', 0)
        ev.append(dict(tool='check', n=r.get('n', 0), screened=screened, seconds=c['seconds']))
    elif c['tool'] == 'solve':
        n_solve += 1
        s, mb = r['solver'], r['model_before']
        kg = s['push_kg_at_100kmh']
        pose = B.pose_to_list(spec_pose(a['body']))
        if base is None:
            base = kg
        elif best is None or kg < best:
            best = kg
        ev.append(dict(tool='solve', k=n_solve, solver_kg=kg, model_kg=round(mb['drag_area_m2'] * 48.193, 2), bound_pct=mb['error_bound_pct'], sure=mb['sure'], err_pct=mb['actual_error_pct'],
                       solver_s=s['seconds'], pose=[[round(x, 4) for x in v] for v in pose], body=a['body'].get('body'), best_kg=best, base_kg=base, screened=screened))
    elif c['tool'] == 'learn':
        ev.append(dict(tool='learn', n=len(a.get('run_ids', [])), version=r.get('model_version'), runs=r.get('runs_in_model'), screened=screened))
    elif c['tool'] == 'render':
        ev.append(dict(tool='render', screened=screened))
prompt = open(os.path.join(run, 'PROMPT.md')).read()
task = [l for l in prompt.split('\n') if l.startswith('Task:')]
json.dump(dict(run=os.path.basename(os.path.abspath(run)), model=summ.get('model'), task=task[0] if task else '', events=ev, solver_runs=n_solve, screened=screened, best_kg=best, base_kg=base,
               wall_s=round(summ.get('duration_ms', 0) / 1000), cost_usd=summ.get('total_cost_usd'), parts=summ.get('parts', 1)), open(out, 'w'))
print('events', len(ev), 'solves', n_solve, 'screened', screened, 'best', best, 'base', base)

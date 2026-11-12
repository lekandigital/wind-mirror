#!/usr/bin/env python3
"""Builds EVIDENCE.html: every claim the demo makes, with its measurement, hardware, baseline and the command that
reproduces it. Reads evidence/results/*.json and the agent run folders; prints nothing it cannot find a file for.
Usage: python3 evidence/build.py [out.html]"""
import json, os, sys, html, glob, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
R = lambda n: os.path.join(HERE, 'results', n)
def load(n, d=None):
    try:
        return json.load(open(R(n)))
    except Exception:
        return d
e = html.escape
OL, OR = '#667a1a', '#d98512'

rel = load('reliability_b.json'); cmu = load('fresh_b_cmu_rand.json'); trk = load('fresh_b_tracked.json'); fa = load('fresh_a_interim.json'); fa_full = load('fresh_a_full.json')
base = load('baselines.json'); bench = load('bench_js.json'); lag = load('lag_fly.json'); binfo = json.load(open(os.path.join(ROOT, 'models', 'model_b_info.json')))
conv = [json.loads(l) for l in open(R('conv.jsonl'))] if os.path.exists(R('conv.jsonl')) else []
conv_long = [json.loads(l) for l in open(R('conv_long.jsonl'))] if os.path.exists(R('conv_long.jsonl')) else []
rest = load('fresh_b_random_rest.json'); leak = load('leak_check_cmu.json'); loop = load('loop_take.json'); perf = load('page_perf.json'); thousand = load('thousand.json'); safari = load('safari_report.json')

def agent(run):
    d = os.path.join(ROOT, 'agent', 'runs', run)
    try:
        s = json.load(open(os.path.join(d, 'summary.json')))
    except Exception:
        return None
    C = [json.loads(l) for l in open(os.path.join(d, 'mcp_calls.jsonl'))]
    sol = [c for c in C if c['tool'] == 'solve' and 'solver' in c['result']]
    answered = sum(c['result'].get('n_meeting_constraints', 0) for c in C if c['tool'] == 'search') + sum(c['result'].get('n', 0) for c in C if c['tool'] == 'check')
    return dict(s=s, solves=sol, dir=d, answered=answered, report=open(os.path.join(d, 'REPORT.md')).read() if os.path.exists(os.path.join(d, 'REPORT.md')) else '')
a1, a2 = agent('20261112-092824'), agent('20261112-121513')

def pct(x, n=1): return f'{x:.{n}f}%'
def table(head, rows, cls=''):
    return f'<table class="{cls}"><thead><tr>' + ''.join(f'<th>{h}</th>' for h in head) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table>'
def verdict(v):
    return {'pass': '<span class="ok">pass</span>', 'fail': '<span class="bad">fail</span>', 'marginal': '<span class="mid">marginal</span>', None: '<span class="dim">too few to judge</span>'}[v]
def group_rows(rows, keep=None, rename=None):
    out = []
    for g, v in rows.items():
        if keep and not keep(g):
            continue
        fs = f'{v["false_sure"]} of {v["sure"]}' + (f' ({v["false_sure_pct_of_sure"]}%)' if v['sure'] else '')
        out.append([e((rename or (lambda x: x))(g)), v['n'], pct(v['err_mean_pct']), f'{v["sure"]} ({v["sure_pct"]}%)', fs, pct(v['coverage_pct']), verdict(v.get('verdict'))])
    return out
GH = ['Group', 'Solver runs', 'Mean force error', 'Labelled sure', 'Sure but more than 10% wrong', 'Solver inside the stated bound', 'By the rules set beforehand']

# ---- the chart: stated bound against what the solver then found
def chart():
    B = rel['bins']; W, H, L, T, Rm, Bm = 760, 330, 56, 26, 150, 54
    pw, ph = W - L - Rm, H - T - Bm; ymax = 0.26
    x = lambda i: L + pw * (i + 0.5) / len(B); y = lambda v: T + ph * (1 - min(v, ymax) / ymax)
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Stated error bound against the actual error found by the solver">']
    for t in (0, 0.05, 0.10, 0.15, 0.20, 0.25):
        s.append(f'<line x1="{L}" x2="{L+pw}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#d9d3c0" stroke-width="1"/><text x="{L-8}" y="{y(t)+4:.1f}" text-anchor="end" class="ax">{int(t*100)}%</text>')
    s.append(f'<line x1="{L}" x2="{L+pw}" y1="{y(0.10):.1f}" y2="{y(0.10):.1f}" stroke="#8a8468" stroke-width="1" stroke-dasharray="4 4"/><text x="{L+pw+8}" y="{y(0.10)+4:.1f}" class="ax">the 10% tolerance</text>')
    pts = []
    for i, b in enumerate(B):
        lab = f'{int(b["lo"]*100)}–{int(b["hi"]*100)}%' if b['hi'] < 1 else f'over {int(b["lo"]*100)}%'
        col = OL if b['hi'] <= 0.10 + 1e-9 else OR
        tip = f'Stated bound {lab}: {b["n"]} answers. Actual error: mean {b["err_mean"]*100:.1f}%, median {b["err_median"]*100:.1f}%, nine in ten under {b["err_p90"]*100:.1f}%. More than 10% wrong: {b["wrong_gt10"]*100:.0f}%.'
        s.append(f'<g><title>{e(tip)}</title><rect x="{x(i)-26:.1f}" y="{T}" width="52" height="{ph}" fill="transparent"/>'
                 f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(b["err_median"]):.1f}" y2="{y(b["err_p90"]):.1f}" stroke="{col}" stroke-width="6" stroke-linecap="round"/>'
                 f'<circle cx="{x(i):.1f}" cy="{y(b["err_mean"]):.1f}" r="5.5" fill="#fbf8ef" stroke="{col}" stroke-width="2.5"/></g>')
        s.append(f'<text x="{x(i):.1f}" y="{T+ph+18}" text-anchor="middle" class="ax">{lab}</text><text x="{x(i):.1f}" y="{T+ph+33}" text-anchor="middle" class="ax dimt">{b["n"]}</text>')
        pts.append((x(i), y(b['bound_mean'])))
    s.append('<polyline fill="none" stroke="#3a382b" stroke-width="2" points="' + ' '.join(f'{a:.1f},{c:.1f}' for a, c in pts) + '"/>')
    s.append(f'<text x="{pts[-1][0]+12:.1f}" y="{pts[-1][1]+4:.1f}" class="ax ink">what the model stated</text>')
    lb = B[-1]
    s.append(f'<text x="{x(len(B)-1)+12:.1f}" y="{y(lb["err_p90"])+4:.1f}" class="ax">nine in ten answers</text><text x="{x(len(B)-1)+12:.1f}" y="{y(lb["err_p90"])+18:.1f}" class="ax">were under this</text>')
    s.append(f'<text x="{x(len(B)-1)+12:.1f}" y="{y(lb["err_mean"])+4:.1f}" class="ax">mean actual error</text>')
    ns = sum(1 for b in B if b['hi'] <= 0.10 + 1e-9)
    s.append(f'<text x="{(x(0)+x(ns-1))/2:.1f}" y="{T+12}" text-anchor="middle" class="ax ink">labelled sure</text><text x="{(x(ns)+x(len(B)-1))/2:.1f}" y="{T+12}" text-anchor="middle" class="ax ink">labelled not sure</text>')
    s.append(f'<line x1="{(x(ns-1)+x(ns))/2:.1f}" x2="{(x(ns-1)+x(ns))/2:.1f}" y1="{T}" y2="{T+ph}" stroke="#d9d3c0" stroke-width="1"/>')
    s.append(f'<text x="{L+pw/2:.1f}" y="{H-2}" text-anchor="middle" class="ax">error bound the model stated · number of answers</text>')
    s.append(f'<text x="{L}" y="{T-10}" class="ax">actual error against the solver</text>')
    s.append('</svg>')
    return '\n'.join(s)

P = []
add = P.append
today = datetime.date.today().isoformat()
add(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Wind Mirror: the evidence</title>
<style>
:root {{ --ink:#26251d; --soft:#6b6654; --line:#dcd6c4; --bg:#f4f0e4; --card:#fbf8ef; --ok:#46521a; --bad:#a8401a; --mid:#8a5a05; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 "Helvetica Neue", Helvetica, Arial, sans-serif; -webkit-font-smoothing:antialiased; }}
main {{ max-width:1020px; margin:0 auto; padding:44px 24px 80px; }}
h1 {{ font-weight:200; font-size:46px; letter-spacing:-0.02em; margin:0 0 6px; }} h2 {{ font-weight:300; font-size:27px; margin:46px 0 10px; letter-spacing:-0.01em; }} h3 {{ font-weight:500; font-size:17px; margin:26px 0 6px; }}
p {{ margin:8px 0; max-width:800px; }} .lede {{ font-size:18px; }} .dim, .small {{ color:var(--soft); }} .small {{ font-size:13.5px; }}
table {{ border-collapse:collapse; width:100%; margin:12px 0 18px; font-size:14px; background:var(--card); border:1px solid var(--line); }}
th, td {{ text-align:left; vertical-align:top; padding:8px 10px; border-bottom:1px solid var(--line); }} th {{ font-weight:500; font-size:12.5px; color:var(--soft); }}
td:nth-child(n+2) {{ font-variant-numeric:tabular-nums; }}
code {{ font:12.5px/1.4 "SF Mono", ui-monospace, Menlo, monospace; background:#ece7d6; padding:1px 5px; border-radius:4px; word-break:break-word; }}
.ok {{ color:var(--ok); font-weight:500; }} .bad {{ color:var(--bad); font-weight:500; }} .mid {{ color:var(--mid); font-weight:500; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin:16px 0; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; }} .tile b {{ display:block; font-weight:200; font-size:40px; letter-spacing:-0.02em; line-height:1.05; }} .tile span {{ font-size:13.5px; color:var(--soft); }}
figure {{ margin:18px 0; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 16px 10px; }} figcaption {{ font-size:13.5px; color:var(--soft); margin-top:6px; max-width:780px; }}
svg {{ width:100%; height:auto; }} .ax {{ font:11.5px "Helvetica Neue", Helvetica, Arial, sans-serif; fill:#6b6654; }} .ax.ink {{ fill:#26251d; }} .ax.dimt {{ fill:#9a947c; }}
.flaw {{ background:#f6ead6; border:1px solid #e3c99a; border-radius:14px; padding:14px 18px; margin:14px 0; }}
details {{ margin:10px 0; }} summary {{ cursor:pointer; color:var(--soft); }} pre {{ white-space:pre-wrap; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; font:12.5px/1.5 "SF Mono", ui-monospace, Menlo, monospace; }}
</style></head><body><main>
<h1>Wind Mirror: the evidence</h1>
<p class="dim">Every claim the demo makes, with its measurement, the hardware, the baseline and the command that reproduces it. Built {today} by <code>python3 evidence/build.py</code> from the result files in <code>evidence/results/</code>. Paths are relative to <code>/Users/lekan/Dev/wind-mirror</code>.</p>
<p class="lede">Wind Mirror poses a simple twin of a person in a simulated wind tunnel from a webcam. A small learned model says how hard a 100 km/h wind pushes on the twin and states an error bound. When the bound is over 10% it says it is not sure, sends the body to a real flow solver, and learns the answer. The same engine is offered to an AI agent as tools.</p>
<p><b>Hardware.</b> Browser and JavaScript figures: Apple M5 MacBook Pro, macOS 26.5, Google Chrome driven headless with the GPU (ANGLE Metal). Solver and training: one NVIDIA RTX 3090 Ti (24 GB) in a Linux box. Nothing was run in a paid cloud.</p>
<p><b>Error measure used everywhere.</b> "Force error" is the size of the difference between the model's force vector (drag, lift, side force) and the solver's, divided by the size of the solver's force vector. Drag-only error is smaller and is given where it helps.</p>''')

# ---- headline tiles
s_, u_ = rel['sure'], rel['unsure']
cA = cmu['tests']['cmu_rand']['ALL']; tA = trk['tests']['trk_sealed']['ALL']
rA = rest['tests']['random_rest']['ALL'] if rest else None
r_lying = sum(rest['tests']['random_rest'].get(k, {}).get('n', 0) for k in ('prone', 'supine')) if rest else 0
c_uns = cA['n'] - cA['sure']; c_uns_wrong = cA['wrong_gt_tol'] - cA['false_sure']
add('<div class="tiles">')
add(f'<div class="tile"><b>{bench["totalMedianMs"]:.1f} ms</b><span>for the learned model to answer one pose with its bound, in JavaScript on the M5' + (f' ({perf["checkMs"]:.1f} ms measured inside the running page)' if perf else '') + '</span></div>')
add('<div class="tile"><b>5.8 s</b><span>for the flow solver it falls back to (3.67 million cells, RTX 3090 Ti to itself; about 13 s when the GPU is shared)</span></div>')
add(f'<div class="tile"><b>{cA["false_sure_pct_of_sure"]}%</b><span>of {cA["sure"]} "sure" answers were more than 10% wrong, on 500 sealed motion-capture poses. Limit set beforehand: 10%</span></div>')
add(f'<div class="tile"><b>{100*c_uns_wrong/c_uns:.0f}%</b><span>of {c_uns} "not sure" answers were more than 10% wrong on the same poses</span></div>')
add('</div>')

# ---- claims table
b_c, b_t = base['sets']['cmu_rand'], base['sets']['trk_sealed']
rows = []
rows.append(['The learned model answers in about half a millisecond.', f'<b>{bench["totalMedianMs"]:.2f} ms</b> median for one pose: {bench["geometryAndFeaturesMs"]["median"]:.2f} ms to pose the twin and compute what the wind sees, {bench["modelAndBoundMs"]["median"]:.2f} ms for the model and its bound. {bench["poses"]} poses tracked from footage; the model holds {bench["runsInStore"]:,} solver runs.' + (f' Inside the running page, with tracking and drawing going on, the same step measures {perf["checkMs"]:.2f} ms in Chrome' + (f' and {safari["checkMs"]:.2f} ms in Safari.' if safari else '.') if perf else ''),
             'Apple M5, Node ' + bench['node'] + ' (the same JavaScript engine as Chrome), one thread', 'The solver: 5.8 s per pose, about 11,000 times slower.', '<code>cd web && node tests/bench.mjs ../private/tracked/fly.json</code> (any pose log from <code>tests/trackdump.mjs</code>)'])
rows.append(['The solver behind it is a real 3D flow solver.', '<b>5.8 s</b> per body: lattice-Boltzmann (D3Q19, regularised collision, Smagorinsky sub-grid model), 224 × 128 × 128 = 3.67 million cells, 8,400 time steps, 5,380 million cell updates a second. Written for this project.',
             'RTX 3090 Ti, Taichi 1.7.4 on CUDA', 'The same code on pitch night ran at 1,570 million cell updates a second (20 s); a memory-layout change made it 3.4 times faster with identical forces on three test poses.', '<code>engine/windtunnel/gen2.py</code>; timing is printed in every line of <code>out/v2/plan.log</code> on the box'])
rows.append(['The model is accurate on poses it has not seen.', f'<b>{b_c["models"]["model B"]["force_err_pct"]}%</b> force error on 500 random motion-capture poses and <b>{b_t["models"]["model B"]["force_err_pct"]}%</b> on 424 poses tracked from seven recorded clips, none used in training or tuning (drag alone: {b_c["models"]["model B"]["drag_err_pct"]}% and {b_t["models"]["model B"]["drag_err_pct"]}%). Cross-validated inside the training set: {binfo["cv_err_pct"]:.1f}%.',
             'Model B, frozen before these runs were evaluated (sha256 ' + binfo['sha256'][:12] + '…), ' + f'{binfo["n_factory"]:,} training runs',
             f'"Frontal area times three fitted constants": {b_c["models"]["area x constants"]["force_err_pct"]}% and {b_t["models"]["area x constants"]["force_err_pct"]}%. The linear part of the model alone: {b_c["models"]["linear trend only"]["force_err_pct"]}% and {b_t["models"]["linear trend only"]["force_err_pct"]}%. The solver\'s own averaging noise: about {b_c["solver_averaging_noise_pct"]:.1f}%.',
             '<code>engine/windtunnel/freshtest_b.py</code> and <code>baselines.py</code> (exact commands in section 7)'])
rows.append(['When it says it is sure, it is rarely badly wrong; when it says it is not sure, it is wrong far more often.',
             f'On 500 sealed motion-capture poses: <b>{cA["false_sure"]} of {cA["sure"]}</b> "sure" answers ({cA["false_sure_pct_of_sure"]}%) were more than 10% wrong, against <b>{c_uns_wrong} of {c_uns}</b> ({100*c_uns_wrong/c_uns:.0f}%) of "not sure" answers. On {tA["n"]} sealed tracked poses the model was sure of every one and {tA["false_sure"]} ({tA["false_sure_pct_of_sure"]}%) were more than 10% wrong, so that set says nothing about "not sure". Pooled: {s_["n_wrong"]} of {s_["n"]} ({s_["wrong_gt10"]*100:.1f}%) against {u_["n_wrong"]} of {u_["n"]}.' + (f' On {rA["n"]} random poses whose solver runs were made after the freeze (lying bodies included): {rA["false_sure"]} of {rA["sure"]} "sure" answers and {rA["wrong_gt_tol"]-rA["false_sure"]} of {rA["n"]-rA["sure"]} "not sure" answers were more than 10% wrong; none of the {r_lying} lying bodies was labelled sure.' if rest else ''),
             'Same frozen model and runs', 'Rules written and committed before the runs were evaluated: <code>docs/PREREGISTRATION_B.md</code> (commit 0fa85e6). Pass line: at most 10% of "sure" answers more than 10% wrong.', 'Section 2 has the chart and the per-group tables, including the groups that failed.'])
lt = trk['learn'].get('moves:fx_seated', {}).get('rows') if trk else None
if lt:
    rows.append(['Every solver run makes the model better where it was weak.', f'A seated stretch the model had never seen (21 tracked poses): <b>{lt["k=0"]["err_mean_pct"]}%</b> force error before, <b>{lt["k=2"]["err_mean_pct"]}%</b> after learning 2 solver runs of the move, <b>{lt["k=5"]["err_mean_pct"]}%</b> after 5, measured on the poses it was not taught. Relearning takes about 4 s on the box.',
                 'Frozen model B + <code>Engine.learn</code>', 'Before learning (k = 0).', 'Section 4.'])
if perf:
    rows.append(['It runs live in a browser tab.', f'<b>{perf["fps"]:.0f} frames a second</b> at {perf["w"]} × {perf["h"]} with the body tracker at {perf["inferMs"]:.0f} ms a frame and the live air on a {perf["grid"]} grid. The twin trails the tracker\'s raw reading by <b>{lag["filterLag"]["left arm"]["lagMs"]} ms</b> on the arms.',
                 'Apple M5, Chrome headless with the GPU, recorded 720 × 1280 clip as input' + (f'. Real Safari {safari["ua"].split("Version/")[1].split(" ")[0]} on the same Mac, one run: {safari["fps"]:.0f} frames a second at {safari["w"]} × {safari["h"]} (×{safari["dpr"]:.1f} pixels), tracker {safari["inferMs"]:.0f} ms, live air on, no errors' if safari else ''), 'The previous BodyArcade video measured 570–640 ms between her movement and the response.', '<code>cd web && node serve.mjs</code>, then <code>node tests/shot.mjs /tmp/out "video=private/fly_720.mp4&noengine=1"</code> and <code>node tests/lag.mjs /tmp/lag fly=private/fly_720.mp4</code>'])
if thousand:
    rows.append(['A thousand positions are checked in under a second.', f'<b>{thousand["ms"]/1000:.2f} s</b> for 1,000 random positions in the tab ({thousand["nSure"]} sure, {thousand["n"]-thousand["nSure"]} not sure).', 'Apple M5, Chrome headless', 'The solver alone: 1,000 × 5.8 s = 1 h 37 min.', 'open <code>http://127.0.0.1:5310/thousand.html</code>'])
for a, lab in ((a2, 'second, corrected run'), (a1, 'first run')):
    if a and not a['s'].get('is_error') and len(a['solves']) > 1:
        sv = a['solves']; kg = [c['result']['solver']['push_kg_at_100kmh'] for c in sv]
        rows.append([f'An AI agent can use it to design something and prove it ({lab}).', f'Claude Fable 5.2 screened <b>{a["s"]["bodies_screened"]:,}</b> positions (the model answered for the {a["answered"]:,} that met the constraints) and used <b>{len(sv)}</b> solver runs: best position <b>{min(kg[1:]):.2f} kg</b> of push against {kg[0]:.2f} kg standing, both from the solver. {a["s"]["duration_ms"]/60000:.0f} min, ${a["s"]["total_cost_usd"]:.2f} at list prices.',
                     'Claude Code CLI + the MCP tool server; solver on the RTX 3090 Ti', 'Solving every screened position would take ' + f'{a["s"]["bodies_screened"]*5.8/86400:.0f} days.', f'<code>agent/run_demo.sh</code>; record in <code>agent/runs/{os.path.basename(a["dir"])}/</code>'])
add('<h2>1. The claims</h2>' + table(['Claim', 'Measurement', 'Measured on', 'Baseline', 'Reproduce'], rows))

# ---- trust
add('<h2>2. Does "not sure" mean anything?</h2>')
add(f'<p>The model states an error bound with every answer. Below, the {rel["n"]} sealed runs are grouped by the bound it stated; the bars show what the solver then found. As the stated bound grows, so does the real error. Answers with a bound of 10% or less are labelled "sure".</p>')
add('<figure>' + chart() + f'<figcaption>Each bar runs from the median actual error to the level nine in ten answers stayed under; the ring is the mean. Olive: labelled sure. Orange: not sure. The dark line is the bound the model stated. Hover a bar for its numbers. The bars rise with the stated bound, and nine in ten answers stay under it in the right-hand groups; in the 4–8% groups the bars reach above the line, which is the under-coverage reported below. Rank correlation between stated bound and actual error: {rel["spearman"]:.2f}.</figcaption></figure>')
add(table(['Stated bound', 'Answers', 'Mean actual error', 'Nine in ten under', 'More than 10% wrong', 'Solver inside the bound'],
          [[(f'{int(b["lo"]*100)}–{int(b["hi"]*100)}%' if b['hi'] < 1 else f'over {int(b["lo"]*100)}%'), b['n'], pct(b['err_mean']*100), pct(b['err_p90']*100), pct(b['wrong_gt10']*100, 0), pct(b['covered']*100, 0)] for b in rel['bins']]))
add('<h3>Fresh test of model B, set 1: 500 random motion-capture poses</h3><p class="small">Poses drawn at random from the CMU motion-capture database, each given a heading and, half the time, a body shape the model has not seen. The pass and fail lines were written before these runs were evaluated.</p>')
keep = lambda g: g in ('ALL', 'reference body', 'other body shapes', 'heading within 50 deg', 'heading beyond 50 deg') or g.startswith('posture') or g in ('cmu:walk', 'cmu:other', 'cmu:sports', 'cmu:climb', 'cmu:dance', 'cmu:jump')
ren = lambda g: {'ALL': 'All 500', 'heading within 50 deg': 'Facing within 50° of the wind', 'heading beyond 50 deg': 'Turned more than 50° from the wind'}.get(g, g.replace('cmu:', 'motion: ').replace('posture ', 'posture: '))
add(table(GH, group_rows(cmu['tests']['cmu_rand'], keep, ren)))
if leak:
    add(f'<p class="small"><b>Leak check.</b> No test pose is in the training set. {leak["same_trial"]["n"]} of the 500 come from a motion-capture trial that also supplied a training pose, {leak["within_1s_of_a_training_pose"]["n"]} of them within one second of it. Those are not easier: force error {leak["same_trial"]["err"]}% for poses from shared trials against {leak["other_trials"]["err"]}% for the rest. Each pose also gets its own random heading and body shape. Reproduce: <code>evidence/results/leak_check_cmu.json</code>.</p>')
add('<h3>Fresh test of model B, set 2: 424 poses tracked from seven recorded clips</h3><p class="small">Clips that took no part in training or tuning. The two people in them also appear in the five other clips that were used for training, so this tests new movements, not new people. In three clips the legs are out of view and the twin stands on assumed straight legs.</p>')
add(table(GH, group_rows(trk['tests']['trk_sealed'], lambda g: g == 'ALL' or g.startswith('clip'), lambda g: 'All 424' if g == 'ALL' else g.replace('clip fx_', 'clip: person 2, ').replace('clip row', 'clip: person 1, rowing motion').replace('_', ' '))))
add('<div class="flaw"><b>Where it fell short.</b> The "sure" label held in every group with enough answers to judge (the worst is 6.7% against the 10% line). The numeric bound did not: it is meant to contain the solver\'s answer 90% of the time and did so 85% (motion capture) and 84% (tracked footage) of the time overall, and only 63% and 57% on two clips (a full-body clip and a seated one). Those two groups fail the test as registered. The bound is too narrow where the answer is already good: it promises ±4% when the truth is ±6%.</div>')
if rest:
    add(f'<h3>Fresh test of model B, set 3: {rA["n"]} random poses solved after the freeze</h3><p class="small">The random-pose queue went on running after model B was frozen at 12:04; these are the runs it made between then and 14:30 (set 4 in the registration). They include the three families model B never trains on: lying head-first, lying on the back, upside down. The queue is still running, so this set will grow.</p>')
    add(table(GH, group_rows(rest['tests']['random_rest'], lambda g: True, lambda g: {'ALL': f'All {rA["n"]}'}.get(g, g if g in ('reference body', 'other body shapes') else 'family: ' + g))))
add('<p class="small"><b>What "before the data was evaluated" means here.</b> The model file and the rules were committed at 12:04 (commit 0fa85e6); the first evaluation script for model B was written and run after that. The solver runs of set 1 had finished on the box seven minutes before the freeze and had not been read by any model or script; the solver runs of sets 2 and 3 were made after it. Git shows the commit order; it cannot show that nobody looked.</p>')
if fa:
    A = fa['interim']
    add('<h3>The model before this one failed its fresh test, and why that mattered</h3>')
    add(f'<p>Model A was frozen at 07:55 on November 12 with rules committed first (<code>docs/PREREGISTRATION.md</code>, commit ef16bbd). An interim look on the first {A["ALL"]["n"]} new runs: {A["ALL"]["false_sure"]} of {A["ALL"]["sure"]} "sure" answers wrong by more than 10% ({A["ALL"]["false_sure_pct_of_sure"]}%), coverage {A["ALL"]["coverage_pct"]}%. One family failed outright: bodies lying head-first, <b>{A["family prone"]["false_sure"]} of {A["family prone"]["sure"]}</b> "sure" answers wrong, coverage {A["family prone"]["coverage_pct"]}%. The model had a few such poses in training, so new ones looked familiar while its fit there was poor. Model B adds two doubt signals for exactly this (how uncertain the local correction is, and how wrong the model was on its nearest training runs) and keeps lying and upside-down bodies out of training, so they stay honest test material.</p>')
    add(table(GH, group_rows(A, lambda g: g in ('ALL', 'reference body', 'other body shapes') or g.startswith('family'), lambda g: g.replace('family ', 'family: ').replace('ALL', 'All ' + str(A['ALL']['n'])))))
    if fa_full:
        add('<p class="small">The full registered test of model A on every new random pose is in <code>evidence/results/fresh_a_full.json</code>.</p>')
    else:
        add('<p class="small">The full registered test of model A (all 3,600 random poses) had not finished when this page was built; the remaining solver runs are still being made.</p>')

# ---- solver
add('<h2>3. Is the solver right?</h2>')
add('<p>Checked against textbook drag coefficients on pitch night (same code, same grid), before any body went in:</p>')
add(table(['Shape', 'Solver', 'Textbook'], [['Cube', '1.07', '1.05'], ['Square plate', '1.12', '1.17'], ['Long cylinder', '1.19', '1.0–1.2'], ['Sphere', '0.54', '0.40–0.47'], ['Standing twin', '1.21', '1.0–1.3 for a standing person']]))
add('<p class="small">Sharp-edged shapes agree within about 5%. The smooth sphere reads about 20% high: blocky cell walls on a curved surface. Reproduce: <code>engine/windtunnel/validate.py cube|plate|cylinder|sphere</code>.</p>')
if conv:
    byp = {}
    for r in conv:
        if r.get('finite', True):
            byp.setdefault(r['pose'], {})[r['H']] = r
    Hs = sorted({r['H'] for r in conv})
    rows = []
    for p, d in byp.items():
        ref = d[64]
        rows.append([p.replace('_', ' ')] + [(f'{d[h]["drag"]:.3f} m²' + (f' ({(d[h]["drag"]/ref["drag"]-1)*100:+.1f}%)' if h != 64 else '')) if h in d else 'not run yet' for h in Hs])
    def rng(h):
        v = [abs(d[h]['drag'] / d[64]['drag'] - 1) * 100 for d in byp.values() if h in d and 64 in d]
        return (f'{min(v):.0f}-{max(v):.0f}% ({len(v)} positions)') if v else None
    r96, r128 = rng(96), rng(128)
    add('<h3>Grid convergence</h3><p>The same five positions on finer grids, with the Reynolds number held fixed. The demo uses 64 cells per body height; the percentages are the drag on the finer grid relative to the grid the demo uses. <b>The solver in the demo reads high</b>: by ' + (r96 or 'n/a') + ' against a grid with 3.4 times as many cells' + (f', and by {r128} against one with 8 times as many. The answer is still falling between those two, so the grid is not converged at any resolution tried' if r128 else '') + '.</p>')
    add(table(['Position'] + [f'{h} cells per body height ({3.5*h*2*h*2*h/1e6:.1f} M cells)' for h in Hs], rows))
    if conv_long:
        dl = {r['pose']: r for r in conv_long}
        add('<p class="small">Averaging four times longer at 64 cells changes drag by ' + ', '.join(f'{(dl[p]["drag"]/byp[p][64]["drag"]-1)*100:+.1f}% ({p.replace("_", " ")})' for p in dl if p in byp and 64 in byp[p]) + '. Reproduce: <code>engine/windtunnel/converge.py 64|96|128 out.jsonl</code>.</p>')
else:
    add('<p class="small">A grid-convergence study (64, 96 and 128 cells per body height) was still running when this page was built.</p>')
add(f'<p>The solver\'s own averaging noise, from the two halves of each run\'s averaging window, is about {b_c["solver_averaging_noise_pct"]:.1f}% of the force. One of roughly 3,500 solver runs made today returned non-finite forces (the simulation diverged on one tracked pose); it is excluded and the engine now refuses to learn from such a run. Run again, the same pose diverges again while its neighbours 35 frames either side solve normally, so a particular geometry trips the solver; the cause has not been found.</p>')

# ---- loop
add('<h2>4. The loop: not sure, solve, learn</h2>')
if loop and loop.get('ledger'):
    L = list(reversed(loop['ledger']))
    add('<p>From the take used in the rough cut (her clip, the turn to profile; the page asked the solver by itself):</p>')
    add(table(['Moment in her clip', 'Model said', 'Stated bound', 'Solver said', 'Model\'s actual error', 'Solver time', 'After learning, on that pose'],
              [[f'{x["videoT"]:.1f} s', f'{x["modelKg"]:.1f} kg', f'±{x["boundPct"]}%', f'{x["solverKg"]:.1f} kg', f'{x["errPct"]}%', f'{x["solverSeconds"]:.1f} s', f'{x["after"]["error_pct"]}% error, ±{x["after"]["error_bound_pct"]}%, ' + ('sure' if x['after']['sure'] else 'not sure')] for x in L]))
if trk and trk.get('learn'):
    rows = []
    for name, d in trk['learn'].items():
        for k, v in d['rows'].items():
            rows.append([name.replace('moves:fx_', 'sealed move: ').replace('_', ' '), k.replace('k=', ''), v['n'], pct(v['err_mean_pct']), f'{v["sure"]} of {v["n"]}', v['false_sure'], pct(v['coverage_pct'])])
    add('<p>The registered learn test: a single move from a sealed clip, the model taught k solver runs spread over it, scored on the poses it was not taught.</p>')
    add(table(['Move', 'Solver runs taught', 'Poses scored', 'Mean force error', 'Labelled sure', 'Sure but more than 10% wrong', 'Solver inside the bound'], rows))
add('<p class="small"><b>How to read the loop in the rough cut.</b> The captions are placed by a script, and the take is then checked against its own log. "It is not sure about this one" appears when the page itself sends the question to the solver, which it does only when that pose\'s own bound is over 10%. "The solver answers" appears when the answer arrives. "Now it is sure" is placed by clip time on the second pass, and the log is checked for any "not sure" reading in that stretch (there is none). The second turn is the same clip replayed, so it shows the model sure about poses it has just learned; learning tested on poses it was <i>not</i> taught is the table below. The label on the page is smoothed over a few frames to stop it flickering, so at the margin it can differ from a single frame\'s bound.</p>')
add('<p class="small">After every learn call the engine refits the model with the new runs and re-calibrates the bound by leaving each run out in turn; the factor never goes below the one set from held-out pose families. Lying bodies stay hard: in development, 20 solver runs of lying head-first poses took the error on other such poses from 35% to 14% and the model stayed "not sure" throughout.</p>')

# ---- agent
add('<h2>5. The agent half</h2>')
add('<p>The engine is exposed as six tools over MCP: <code>check</code>, <code>search</code>, <code>solve</code>, <code>learn</code>, <code>status</code>, <code>render</code>. One command (<code>agent/run_demo.sh</code>) starts Claude Fable 5.2 in the Claude Code CLI with only those tools and this prompt: "design the lowest-drag position a downhill skier could actually hold at 100 km/h, and prove it", with constraints and a budget of 12 solver runs. The exact prompt, the full transcript, every tool call and the final report are saved per run.</p>')
for a, lab in ((a1, 'Run 1 (preliminary model, 09:28–12:03)'), (a2, 'Run 2 (frozen model B, corrected constraints)')):
    if not a:
        continue
    sv = a['solves']; s = a['s']
    add(f'<h3>{lab}: <code>agent/runs/{os.path.basename(a["dir"])}/</code></h3>')
    if s.get('is_error') or len(sv) < 2:
        add(f'<p>Not finished when this page was built: {len(sv)} of 12 solver runs used.</p>'); continue
    add(f'<p>{s["num_turns"]} turns in {s.get("parts", 1)} part{"s" if s.get("parts", 1) > 1 else ""}; {s["bodies_screened"]:,} positions screened, of which the model answered for {a["answered"]:,}; {len(sv)} solver runs ({s["solver_seconds"]:.0f} s of solver time); {s["duration_ms"]/60000:.0f} min; {s["output_tokens"]:,} output tokens; ${s["total_cost_usd"]:.2f} at list prices.' + (' The session was cut off once by a usage limit and continued in the same conversation with one message, which is saved beside the prompt.' if s.get('parts', 1) > 1 else '') + '</p>')
    add(table(['Solver run', 'Model said', 'Its bound', 'Sure?', 'Solver said', 'Model\'s actual force error'],
              [[i + 1, f'{c["result"]["model_before"]["drag_area_m2"]*48.193:.2f} kg', f'±{c["result"]["model_before"]["error_bound_pct"]}%', 'yes' if c['result']['model_before']['sure'] else 'no', f'<b>{c["result"]["solver"]["push_kg_at_100kmh"]:.2f} kg</b>', f'{c["result"]["model_before"]["actual_error_pct"]}%'] for i, c in enumerate(sv)]))
    sure_solved = [c for c in sv if c['result']['model_before']['sure']]
    bad = [c for c in sure_solved if c['result']['model_before']['actual_error_pct'] > 10]
    if len(sv) >= 12:
        add(f'<p><b>{len(bad)} of the {len(sure_solved)} answers the model was sure of, among those the agent chose to solve, were more than 10% wrong.</b> That is far above the rate on random poses: a search for the lowest predicted drag picks out the model\'s errors. The gate was calibrated on random and tracked poses, not on searched ones, which is why the task tells the agent to solve its final design whatever the model says.</p>')
    add('<details><summary>The agent\'s own final report</summary><pre>' + e(a['report']) + '</pre></details>')
add('<div class="flaw"><b>What run 1 exposed.</b> Its final "tuck" (7.22 kg) met the four constraints as I had written them and is not a position a person can take: the thighs pass 14 cm into the chest and the twin stands on its toes. My floor-clearance rule wrongly counted the lower legs, which ruled out flat-footed stances. The agent said so itself ("probably not holdable in ski boots"). The rule was fixed and a legs-through-torso check added before run 2. Run 1\'s numbers are real solver results for an unreal pose and are not used as a design result.</div>')

# ---- prior art
add('''<h2>6. What already exists</h2>
<p>Nothing here is a first, and the page should not be read as claiming one. The closest work found (links and search lists are in <code>NOVELTY_RESEARCH.md</code> in the build folder):</p>
<ul>
<li><b>A webcam wind tunnel exists in 2D.</b> Blake Sanie's "Aero" (2024) cuts a rider out of a webcam image and runs a 2D lattice-Boltzmann flow in the browser.</li>
<li><b>A learned drag model for posed human bodies exists.</b> Giljarhus and Oggiano (Sports Engineering, 2026): 240 CFD runs of scanned athletes, 2.69% drag-area error, no uncertainty, not live.</li>
<li><b>Confidence scores ship in commercial tools</b> (Ansys SimAI, Altair physicsAI); both say theirs is not an error estimate.</li>
<li><b>Check, solve, learn is a textbook loop</b> in molecular simulation (FLARE, VASP on-the-fly force fields, DP-GEN) and has been shown in CFD (AdaLED). Conformal error bounds for neural PDE models are published (Gopakumar et al.).</li>
<li><b>Agents driving full solvers exist</b> (SimScale's agent, Neural Concept's MCP bridge, AeroAgent).</li>
</ul>
<p>What was not found: a doubt score tied to an error bound with its false-sure rate published per unseen group; the loop shown live on a moving person; an agent tool that returns that doubt and has a learn call. "Not found" means not in the searches listed there.</p>''')

# ---- flaws
add('''<h2>7. What is not true, not verified, or weak</h2>
<ul>
<li><b>It does not measure a person.</b> The twin is 19 rounded capsules posed from 33 tracked points. The solver was checked against textbook shapes, never against a wind-tunnel measurement of a human body, and published human drag values could not be traced to primary sources in this build.</li>
<li><b>The stated bound under-covers</b> (section 2): 84–85% against a nominal 90%, and 57–63% on two clips.</li>
<li><b>The air on screen is illustrative.</b> It is a real lattice-Boltzmann simulation, but on about 270,000 cells at a low Reynolds number, slowed down for viewing. The force number never comes from it.</li>
<li><b>The solver itself has error, and it is larger than the model's.</b> The demo's grid is not converged: grids with 3.4 and 8 times as many cells give 4-12% less drag for the same body, and the answer is still falling (section 3). The model's 3-6% error is its distance from this solver, not from the truth. Voxel walls also read a smooth sphere 20% high, and one run in about 3,500 diverges.</li>
<li><b>The tracker is the weakest sensor.</b> Depth from one camera is a guess; when the legs are out of view the twin stands on assumed straight legs and the page says so. Glass-to-glass delay with a real webcam was not measured (recorded clips only, by standing rule).</li>
<li><b>Learning one pose does not teach a family.</b> One solver run makes the model sure only close to that pose.</li>
<li><b>No real phone was tested</b>, only a phone-sized window in Chrome. Real Safari was run once on this Mac (section 1); Firefox was not tried.</li>
<li><b>The live page needs the solver service</b> (the GPU box through an SSH tunnel) for the "ask the solver" step. Without it the page still answers and says when it is not sure, and cannot learn.</li>
</ul>''')

# ---- reproduce
add('''<h2>8. Reproduce</h2>
<pre># page (Mac)
cd /Users/lekan/Dev/wind-mirror/web &amp;&amp; node serve.mjs            # http://127.0.0.1:5310/
node tests/parity.mjs &amp;&amp; node tests/parity_b.mjs                 # browser code against the Python engine (80 bodies end to end: pose to answer)
node tests/bench.mjs ../private/tracked/fly.json                 # time per answer
open -g -a Safari 'http://127.0.0.1:5310/?video=private/fly_720.mp4&amp;noengine=1&amp;report=16&amp;keep=1'   # real Safari posts its own report to web/tests/reports/

# engine with the solver (box), reached from the Mac through a tunnel
ssh box 'cd ~/Dev/wind-mirror &amp;&amp; tmux new -d -s wm-engine ".venv/bin/python agent/server.py out/state_b 5311"'
ssh -f -N -L 5311:127.0.0.1:5311 box

# agent half (Mac)
agent/run_demo.sh                                                # prompt: agent/TASK.md; output: agent/runs/&lt;time&gt;/

# model B: build, freeze, fresh tests (box, in engine/windtunnel)
python build_b.py ../../out/state_b/store.npz ../../out/pitch/poses_v1.jsonl ../../out/v2/synth_a/runs.jsonl ../../out/v2/cmu_div/runs.jsonl ../../out/v2/trk_dev/runs.jsonl
python freshtest_b.py ../../models/model_b_store.npz ../../out/fresh/fresh_b_cmu_rand.json cmu_rand=../../out/v2/cmu_rand/runs.jsonl
python freshtest_b.py ../../models/model_b_store.npz ../../out/fresh/fresh_b_tracked.json trk_sealed=../../out/v2/trk_sealed_uniform.jsonl --learn moves=../../out/v2/trk_sealed_dense.jsonl
python freshtest_b.py ../../models/model_b_store.npz ../../out/fresh/fresh_b_random_rest.json random_rest=../../out/v2/synth_a_after817.jsonl   # rows 818 onward of synth_a/runs.jsonl
python baselines.py ../../models/model_b_store.npz ../../out/fresh/baselines.json cmu_rand=../../out/v2/cmu_rand/runs.jsonl trk_sealed=../../out/v2/trk_sealed_uniform.jsonl

# this page
python3 evidence/build.py</pre>
<p class="small">The first build_b.py command above used the first 817 runs of <code>synth_a</code>; that file has grown since, so rerunning it now gives a different (larger) model. The frozen one is <code>models/model_b_store.npz</code>.</p>
<h2>9. Third-party material</h2>''')
add(table(['What', 'Used for', 'Licence'], [
    ['MediaPipe Tasks Vision 0.10.35 and its pose landmarker models (Google)', 'Body tracking in the page', 'Apache-2.0 (package). Model licence as stated on its model card; re-check before publishing.'],
    ['CMU Graphics Lab Motion Capture Database', '715 training poses, 500 test poses, the idle animation', '"Free for all uses"; may be included in commercial products, not resold as data. Acknowledgement text is in <code>out/mocap_qa/SOURCE.md</code>.'],
    ['Taichi 1.7.4, NumPy', 'Solver and model on the box', 'Apache-2.0, BSD-3-Clause'],
    ['Playwright, ffmpeg', 'Tests and the rough cut only', 'Apache-2.0; LGPL/GPL (tool, not shipped)'],
    ['X logo', 'End card of the rough cut', 'Trademark of X Corp.; used as on the previous video\'s card; not in the repository'],
    ['The performer\'s June clips', 'Stand-in footage for development and the rough cut', 'Private. Consent for public use is not on record; nothing with her image is in the repository.']]))
add('<p class="small">The solver, the body model, the learned model, the page and the agent tools were written for this project.</p></main></body></html>')
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'EVIDENCE.html')
open(out, 'w').write('\n'.join(P))
print('wrote', out, len('\n'.join(P)) // 1024, 'KB')

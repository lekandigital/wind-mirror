"""Baselines and the solver's own noise, for the evidence page.
 - 'frontal area x three constants' (the rule of thumb), fitted on the factory set, scored on the sealed sets
 - the linear trend alone (no local correction), same sets
 - the solver's averaging noise: half the difference between the two halves of each run's averaging window
Usage: python baselines.py <store.npz> <out.json> <label>=<runs.jsonl> [...]"""
import sys, json
import numpy as np
import data as D
from surrogate import verr
from model_b import ModelB

z = np.load(sys.argv[1], allow_pickle=False)
X, y, yp = z['X'], z['y'], z['yp']
cd0 = np.median(y / X[:, :1], axis=0)
kw = dict(ell=float(z['ell']), noise=float(z['noise']), k=int(z['k']))
trend = ModelB(X, y, yp, use_gp=False, **kw)
full = ModelB(X, y, yp, **kw)
out = dict(rule_of_thumb_coeffs=cd0.tolist(), sets={})
for a in sys.argv[3:]:
    label, path = a.split('=', 1)
    S = D.load(path, path.replace('.jsonl', '_feat.npz'))
    yy = S['y']
    rows = {}
    for name, p in (('area x constants', cd0[None] * S['X'][:, :1]), ('linear trend only', trend.predict(S['X'])), ('model B', full.predict(S['X']))):
        rows[name] = dict(force_err_pct=round(float(verr(p, yy).mean() * 100), 2), drag_err_pct=round(float((np.abs(p[:, 0] - yy[:, 0]) / yy[:, 0]).mean() * 100), 2),
                          lift_abs_err_m2=round(float(np.abs(p[:, 1] - yy[:, 1]).mean()), 4), side_abs_err_m2=round(float(np.abs(p[:, 2] - yy[:, 2]).mean()), 4))
    hv = np.array([[r['F_halves'][0], r['F_halves'][1]] for r in S['R'] if r.get('F_halves')])
    noise = None
    if len(hv):
        d = (hv[:, 0, :] - hv[:, 1, :])[:, [0, 2, 1]]                    # halves are [drag, side, lift]
        noise = round(float(np.median(np.linalg.norm(d, axis=1) / 2 / np.linalg.norm(yy[:len(hv)], axis=1)) * 100), 2)
    out['sets'][label] = dict(n=int(S['n']), models=rows, solver_averaging_noise_pct=noise)
    print(label, S['n'], json.dumps(rows), 'solver noise %', noise)
json.dump(out, open(sys.argv[2], 'w'), indent=1)

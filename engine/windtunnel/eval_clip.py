"""Score a trained pair against solver runs of a clip. Usage: eval_clip.py <pair.pt> <forces.jsonl> [out.npz]"""
import sys, json
import numpy as np
from check import Check
from train import load, verr

R, X, y = load(sys.argv[2])
ck = Check(sys.argv[1])
r = ck.check_features(X)
P = np.stack([r['CdA'], r['lift'], r['side']], 1)
e = verr(P, y); de = np.abs(P[:, 0] - y[:, 0]) / y[:, 0]
base = ck_cd0 = None
import torch
cd0 = torch.load(sys.argv[1], weights_only=False)['cd0']
be = verr(cd0[None, :] * X[:, -1:], y)
a = r['sure']
order = np.argsort([q['t'] for q in R])
print(json.dumps(dict(n=len(R), vector_err_pct=round(float(e.mean() * 100), 2), drag_err_pct=round(float(de.mean() * 100), 2), max_vector_err_pct=round(float(e.max() * 100), 1),
                      rule_of_thumb_vector_err_pct=round(float(be.mean() * 100), 2), answered_instantly_pct=round(float(a.mean() * 100), 1),
                      err_of_answered_pct=round(float(e[a].mean() * 100), 2) if a.any() else None, err_of_answered_max_pct=round(float(e[a].max() * 100), 1) if a.any() else None,
                      err_of_escalated_pct=round(float(e[~a].mean() * 100), 2) if (~a).any() else None)))
if '--rows' in sys.argv:
    for i in order:
        print('t=%5.1fs solver drag %.3f lift %+.3f | model drag %.3f lift %+.3f | err %5.1f%% doubt %6.2f %s' % (R[i]['t'], y[i, 0], y[i, 1], P[i, 0], P[i, 1], e[i] * 100, r['doubt'][i], 'sure' if a[i] else 'ASK SOLVER'))
if len(sys.argv) > 3 and not sys.argv[3].startswith('--'):
    np.savez(sys.argv[3], t=np.array([q['t'] for q in R]), y=y, pred=P, err=e, doubt=r['doubt'], sure=a, tau=ck.tau)

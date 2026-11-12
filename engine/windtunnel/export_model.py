"""Write a saved surrogate (npz) as JSON for the browser, and optionally a set of parity cases for the JavaScript tests.
Usage: python export_model.py <model.npz> <out.json> [parity_cases.json]"""
import sys, json, numpy as np
import bodies as B, geom as G
from model_io import Model

z = np.load(sys.argv[1], allow_pickle=False)
r6 = lambda a: [float(f'{x:.9g}') for x in np.asarray(a, float).ravel()]
out = dict(names=[str(n) for n in z['names']], tol=float(z['tol']), alpha=float(z['alpha']), k=int(z['k']), doubt_q=float(z['doubt_q']),
           doubt_w=r6(z['doubt_w']), doubt_use=[int(u) for u in z['doubt_use']])
for k in ('full_mu', 'full_sd', 'full_W', 'full_Ainv', 'glob_mu', 'glob_sd', 'glob_W', 'parts_mu', 'parts_sd', 'parts_W'):
    out[k] = r6(z[k])
out['Zref'] = [float(f'{x:.6g}') for x in z['Zref'].ravel()]
json.dump(out, open(sys.argv[2], 'w'), separators=(',', ':'))
print('wrote', sys.argv[2])
if len(sys.argv) > 3:
    M = Model(sys.argv[1]); rng = np.random.default_rng(7); cases = []
    import sample2
    fams = list(sample2.FAMILIES)
    for i in range(60):
        pose, fam = sample2.sample(rng, fams[i % len(fams)])
        body = B.sample_shape(rng) if i % 2 else None
        X = G.features(pose, body); r = M.check(X[None])
        caps = G.body_capsules(pose, body)
        cases.append(dict(family=fam, pose=B.pose_to_list(pose), body=body, has_lh='lh' in pose, features=X.tolist(),
                          capsules=[dict(a=a.tolist(), b=b.tolist(), r=r_, part=p) for a, b, r_, p in caps],
                          force=r['force'][0].tolist(), parts=r['parts'][0].ravel().tolist(), signals=r['signals'][0].tolist(), bound=float(r['bound'][0]), sure=bool(r['sure'][0])))
    json.dump(cases, open(sys.argv[3], 'w'))
    print('wrote', len(cases), 'parity cases')

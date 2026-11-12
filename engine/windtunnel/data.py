"""Load solver runs (pitch-night format and dataset v2 format) into arrays, with the wind's-eye features cached on disk.

Every row becomes: X (geometric features, geom.NAMES), J (the pitch-night joint features, 40 numbers, for comparison),
y (drag, lift, side force areas in m^2, blockage-corrected), yp (per-part forces, 10 x 3 in the same order), and metadata.
"""
import json, os, hashlib
import numpy as np
import bodies as B
import geom as G


def force_vec(r):
    F = np.array(r['F_parts'], float).sum(0) * r['corr']
    return [F[0], F[2], F[1]]


def part_forces(r):
    F = np.array(r['F_parts'], float) * r['corr']
    return F[:, [0, 2, 1]]


def _feat(args):
    pose_list, body = args
    pose = B.pose_from_list(pose_list)
    g = G.features(pose, body)
    j = B.full_features(pose, g[0]) if True else None
    return np.concatenate([g, j])


def featurise(rows, cache=None, procs=12):
    """Geometric + joint features for a list of rows (each with 'pose' and optional 'body'). Cached by content hash."""
    keys = [hashlib.sha1(json.dumps([r['pose'], r.get('body')], sort_keys=True).encode()).hexdigest() for r in rows]
    store = {}
    if cache and os.path.exists(cache):
        z = np.load(cache, allow_pickle=False)
        store = dict(zip(z['keys'].tolist(), z['vals']))
    todo = [i for i, k in enumerate(keys) if k not in store]
    if todo:
        args = [(rows[i]['pose'], rows[i].get('body')) for i in todo]
        if len(todo) > 40 and procs > 1:
            from multiprocessing import Pool
            with Pool(procs) as pool:
                vals = pool.map(_feat, args, chunksize=8)
        else:
            vals = [_feat(a) for a in args]
        for i, v in zip(todo, vals):
            store[keys[i]] = v
        if cache:
            np.savez(cache, keys=np.array(list(store.keys())), vals=np.array(list(store.values())))
    V = np.array([store[k] for k in keys])
    return V[:, :len(G.NAMES)], V[:, len(G.NAMES):]


def load(path, cache=None, source=None):
    R = []
    for l in open(path):
        r = json.loads(l)
        if 'F_parts' in r and np.isfinite(np.array(r['F_parts'], float)).all():      # a diverged solver run (NaN forces) is not data
            R.append(r)
    X, J = featurise(R, cache)
    y = np.array([force_vec(r) for r in R], float)
    yp = np.array([part_forces(r) for r in R], float)
    fam = np.array([str(r.get('family', source or '')) for r in R])
    split = np.array([str(r.get('split', '')) for r in R])
    noise = np.array([abs(r['CdA_halves'][0] - r['CdA_halves'][1]) / max(r['CdA'], 1e-9) for r in R])
    return dict(R=R, X=X, J=J, y=y, yp=yp, fam=fam, split=split, noise=noise, n=len(R))


def cat(*Ds):
    out = {}
    for k in ('X', 'J', 'y', 'yp', 'fam', 'split', 'noise'):
        out[k] = np.concatenate([d[k] for d in Ds])
    out['R'] = sum([d['R'] for d in Ds], [])
    out['n'] = len(out['R'])
    return out

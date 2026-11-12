"""Freeze 'model A': trained and calibrated on the pitch-night runs only, before any dataset-v2 result is evaluated.

Writes out/frozen_a/model_a.npz (weights, calibration, the leave-family-out scores it was calibrated on) and prints its sha256.
The fresh test (freshtest.py) loads this file and nothing else.
"""
import json, hashlib, numpy as np
import data as D, geom as G
from surrogate import Surrogate, Doubt, verr

TOL, ALPHA = 0.10, 0.10


def lofo_scores(P):
    fams = sorted(set(P['fam']))
    S = np.zeros((P['n'], 4)); E = np.zeros(P['n'])
    for f in fams:
        te = P['fam'] == f; tr = ~te
        m = Surrogate(P['X'][tr], P['y'][tr], P['yp'][tr])
        p, s = m.signals(P['X'][te]); S[te] = s; E[te] = verr(p, P['y'][te])
    rng = np.random.default_rng(0)
    idx = np.where(np.isin(P['fam'], ['stand', 'tuck', 'wide']))[0]; rng.shuffle(idx)
    S_in = np.zeros((len(idx), 4)); E_in = np.zeros(len(idx))
    for kf in range(5):
        sel = np.arange(len(idx))[kf::5]; te = idx[sel]; tr = np.setdiff1d(idx, te)
        m = Surrogate(P['X'][tr], P['y'][tr], P['yp'][tr])
        p, s = m.signals(P['X'][te]); S_in[sel] = s; E_in[sel] = verr(p, P['y'][te])
    return np.concatenate([S, S_in]), np.concatenate([E, E_in])


def save(path, m, d):
    np.savez(path, names=np.array(G.NAMES), full_mu=m.full.mu, full_sd=m.full.sd, full_W=m.full.W, full_Ainv=m.full.Ainv, full_lam=m.full.lam,
             glob_mu=m.glob.mu, glob_sd=m.glob.sd, glob_W=m.glob.W, glob_lam=m.glob.lam,
             parts_mu=m.parts.mu, parts_sd=m.parts.sd, parts_W=m.parts.W, parts_lam=m.parts.lam,
             Zref=m.Zref.astype(np.float32), k=m.k, doubt_w=d.w, doubt_q=d.q, doubt_use=np.array(d.use), alpha=d.alpha, tol=TOL)


if __name__ == '__main__':
    import os
    os.makedirs('../../out/frozen_a', exist_ok=True)
    P = D.load('../../out/pitch/poses_v1.jsonl', '../../out/pitch/feat_cache.npz')
    Scal, Ecal = lofo_scores(P)
    d = Doubt(Scal, Ecal, use=(0, 1, 2, 3), alpha=ALPHA)
    m = Surrogate(P['X'], P['y'], P['yp'])
    save('../../out/frozen_a/model_a.npz', m, d)
    np.savez('../../out/frozen_a/calibration_scores.npz', S=Scal, E=Ecal)
    h = hashlib.sha256(open('../../out/frozen_a/model_a.npz', 'rb').read()).hexdigest()
    info = dict(sha256=h, n_train=int(P['n']), n_features=len(G.NAMES), doubt_w=[float(x) for x in d.w], doubt_q=float(d.q), alpha=ALPHA, tol=TOL,
                ridge_lam=dict(full=float(m.full.lam), glob=float(m.glob.lam), parts=float(m.parts.lam)))
    json.dump(info, open('../../out/frozen_a/info.json', 'w'), indent=1)
    print(json.dumps(info, indent=1))

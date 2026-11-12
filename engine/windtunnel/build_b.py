"""Build model B's store: the factory training set, the kriging settings and the doubt calibration.

Factory training set = every run given on the command line whose family is not in the never-train list
(lying and upside-down bodies stay unseen, so the doubt and the learn step have something real to be tested on).
Doubt calibration = leave-one-family-out scores of all families (never-train ones included, as held-out groups)
 + five-fold scores inside the factory set + 'a few runs of a new family' scores (k = 2, 5, 10).
Usage: python build_b.py <out_store.npz> <runs.jsonl> [<runs.jsonl> ...]
"""
import sys, json, time, hashlib
import numpy as np
import data as D
from surrogate import Doubt, verr, auroc
from model_b import ModelB, SIG_NAMES

TOL, ALPHA = 0.10, 0.10
KW = dict(ell=5.0, noise=0.3, k=40)
NEVER = ['prone', 'supine', 'inverted', 'cmu_low', 'cmu_inverted', 'move']
# Single moves in the recorded clips that the factory model must never see (clip -> seconds). They are kept for the
# 'learn a move from a few solver runs' experiment and so that the demo's "not sure" moments are real.
MOVES = {'fly': (19.0, 24.5), 'puppet': (14.0, 18.8), 'fx_crouch_stand': (8.0, 16.0), 'fx_lean_fb': (10.0, 17.0), 'fx_seated': (20.0, 26.0)}


def family_of(r, default=''):
    f = str(r.get('family', default))
    if f in ('side', 'back'):
        return 'turn'
    if f.startswith('trk:'):
        w = MOVES.get(r.get('clip'))
        return 'move' if w and w[0] <= r.get('t', -1) <= w[1] else f
    if f.startswith('cmu:'):
        post = r.get('posture', 'upright')
        return f if post == 'upright' else 'cmu_' + post
    return f


def calibration_scores(X, y, yp, fam, seed=0, log=print):
    fams = sorted(set(fam)); n = len(X)
    factory = ~np.isin(fam, NEVER)
    S, E = [], []
    by_family = {}
    for f in fams:                                              # leave one family out
        te = fam == f
        if te.sum() < 8 or f == 'move':
            continue
        m = ModelB(X[~te], y[~te], yp[~te], **KW)
        p, s = m.signals(X[te]); e = verr(p, y[te])
        S.append(s); E.append(e); by_family[f] = (s, e)
    idx = np.where(factory)[0]; rng = np.random.default_rng(seed); rng.shuffle(idx)
    S_in = np.zeros((n, len(SIG_NAMES))); E_in = np.zeros(n)
    for kf in range(5):                                         # five folds inside the factory set
        te = idx[kf::5]; tr = np.setdiff1d(idx, te)
        m = ModelB(X[tr], y[tr], yp[tr], **KW)
        p, s = m.signals(X[te]); S_in[te] = s; E_in[te] = verr(p, y[te])
    S.append(S_in[idx]); E.append(E_in[idx])
    few = {}
    for f in [x for x in NEVER if (fam == x).sum() >= 24 and x != 'move']:     # a new family after a few solver runs
        fi = np.where(fam == f)[0]; r2 = np.random.default_rng(seed + 1); r2.shuffle(fi)
        for kk in (2, 5, 10):
            tr = np.concatenate([idx, fi[:kk]]); te = fi[kk:]
            m = ModelB(X[tr], y[tr], yp[tr], **KW)
            p, s = m.signals(X[te]); e = verr(p, y[te])
            S.append(s); E.append(e); few[(f, kk)] = (s, e)
    return np.concatenate(S), np.concatenate(E), by_family, (S_in[idx], E_in[idx]), few


def main():
    out = sys.argv[1]
    t0 = time.time()
    parts = [D.load(p, p.replace('.jsonl', '_feat.npz')) for p in sys.argv[2:]]
    A = D.cat(*parts)
    fam = np.array([family_of(r) for r in A['R']])
    X, y, yp = A['X'], A['y'], A['yp']
    print('runs', A['n'], {f: int((fam == f).sum()) for f in sorted(set(fam))}, flush=True)
    clip = np.array([str(r.get('clip', '')) for r in A['R']])
    Scal, Ecal, byfam, (S_in, E_in), few = calibration_scores(X, y, yp, fam)
    # the held-out moves, one clip at a time: factory model first, then after k solver runs of that move (spread over it)
    base = np.where(~np.isin(fam, NEVER))[0]
    mS, mE = [], []
    for c in sorted(set(clip[fam == 'move'])):
        mi = np.where((fam == 'move') & (clip == c))[0]
        mi = mi[np.argsort([A['R'][i]['t'] for i in mi])]
        for kk in (0, 2, 5):
            teach = mi[np.linspace(0, len(mi) - 1, kk).round().astype(int)] if kk else mi[:0]
            te = np.setdiff1d(mi, teach)
            m = ModelB(X[np.concatenate([base, teach])], y[np.concatenate([base, teach])], yp[np.concatenate([base, teach])], **KW)
            p, s = m.signals(X[te]); e = verr(p, y[te])
            mS.append(s); mE.append(e); few[('move ' + c, kk)] = (s, e)
    if mS:
        Scal = np.concatenate([Scal] + mS); Ecal = np.concatenate([Ecal] + mE)
    d = Doubt(Scal, Ecal, use=tuple(range(len(SIG_NAMES))), alpha=ALPHA, fit_floor=True)
    print('doubt weights', dict(zip(SIG_NAMES + ['bias'], np.round(d.w, 3))), 'q', round(d.q, 3), 'floor s0', d.s0)
    b_in = d.bound(S_in)
    print(f'in-family folds: n={len(E_in)} err {E_in.mean()*100:.2f}%  sure {np.mean(b_in<=TOL)*100:.1f}%  false-sure {int(((b_in<=TOL)&(E_in>TOL)).sum())}/{int((b_in<=TOL).sum())}  coverage {np.mean(E_in<=b_in)*100:.1f}%')
    for f, (s, e) in byfam.items():
        b = d.bound(s)
        print(f'  leave-out {f:22s} n={len(e):4d} err {e.mean()*100:5.1f}%  sure {int((b<=TOL).sum()):4d}  false-sure {int(((b<=TOL)&(e>TOL)).sum()):3d}  covered {np.mean(e<=b)*100:5.1f}%')
    for (f, kk), (s, e) in few.items():
        b = d.bound(s)
        print(f'  few-shot  {f:14s} k={kk:2d}  n={len(e):4d} err {e.mean()*100:5.1f}%  sure {int((b<=TOL).sum()):4d}  false-sure {int(((b<=TOL)&(e>TOL)).sum()):3d}  covered {np.mean(e<=b)*100:5.1f}%')
    factory = ~np.isin(fam, NEVER)
    qid = np.array([str(r.get('qid', r.get('i', ''))) for r in A['R']])
    np.savez(out, X=X[factory], y=y[factory], yp=yp[factory], fam=fam[factory], qid=qid[factory], ell=KW['ell'], noise=KW['noise'], k=KW['k'],
             doubt_w=d.w, doubt_q=d.q, doubt_s0=d.s0, doubt_use=np.array(d.use), tol=TOL, alpha=ALPHA, sig_names=np.array(SIG_NAMES),
             cal_S=Scal, cal_E=Ecal)
    h = hashlib.sha256(open(out, 'rb').read()).hexdigest()
    info = dict(sha256=h, n_factory=int(factory.sum()), n_all=int(A['n']), families={f: int((fam == f).sum()) for f in sorted(set(fam))}, never=NEVER, kriging=KW,
                doubt_w=[float(v) for v in d.w], doubt_q=float(d.q), doubt_s0=float(d.s0), tol=TOL, alpha=ALPHA, sources=sys.argv[2:], seconds=round(time.time() - t0, 1),
                cv_err_pct=float(E_in.mean() * 100))
    json.dump(info, open(out.replace('.npz', '_info.json'), 'w'), indent=1)
    print(json.dumps({k: info[k] for k in ('sha256', 'n_factory', 'n_all', 'doubt_q', 'cv_err_pct', 'seconds')}))


if __name__ == '__main__':
    main()

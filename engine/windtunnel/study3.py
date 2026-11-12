"""Study 3: model B (trend + local kriging) and its doubt gate on the larger dataset.

 A. accuracy: 5-fold inside the factory families; leave-one-family-out; the performer's clips
 B. gate: doubt fitted on leave-family-out + in-family folds, false-sure and coverage by family
 C. the learn step: a never-seen family gets k solver runs; is the model better on the rest, and is the gate still honest?
Usage: python study3.py [extra_runs.jsonl ...]
"""
import sys, json, time
import numpy as np
import data as D, geom as G
from surrogate import Doubt, verr, auroc
from model_b import ModelB, SIG_NAMES

TOL, ALPHA = 0.10, 0.10
NEVER = ['prone', 'supine', 'inverted']


def run(Xtr, ytr, yptr, Xte, **kw):
    m = ModelB(Xtr, ytr, yptr, **kw)
    return m.signals(Xte)


def main():
    t0 = time.time()
    P = D.load('../../out/pitch/poses_v1.jsonl', '../../out/pitch/feat_cache.npz')
    S = D.load('../../out/v2/synth_a/runs.jsonl', '../../out/v2/synth_a_feat.npz')
    parts = [P, S]
    for extra in sys.argv[1:]:
        parts.append(D.load(extra, extra.replace('.jsonl', '_feat.npz')))
    A = D.cat(*parts)
    fam = A['fam'].copy()
    fam[np.isin(fam, ['side', 'back'])] = 'turn'              # the pitch's side-on and back-to-wind runs are headings of 'turn'
    X, y, yp = A['X'], A['y'], A['yp']
    fams = sorted(set(fam))
    print('runs', A['n'], {f: int((fam == f).sum()) for f in fams}, f'({time.time()-t0:.0f}s)', flush=True)
    clips = {c: D.load(f'../../out/pitch/clip_{c}.jsonl', '../../out/pitch/feat_cache.npz', source='clip_' + c) for c in ('fly', 'puppet', 'row')}
    factory = ~np.isin(fam, NEVER)
    rng = np.random.default_rng(0)
    out = {}

    # ---- A. accuracy, and the kriging settings
    idx = np.where(factory)[0]; rng.shuffle(idx)
    folds = [idx[k::5] for k in range(5)]
    print('\nA. 5-fold error inside the factory families (%), by kriging setting:')
    best = None
    for name, kw in [('trend only', dict(use_gp=False)), ('ell 3', dict(ell=3.0)), ('ell 5', dict(ell=5.0)), ('ell 8', dict(ell=8.0)), ('ell 5, noise 0.3', dict(ell=5.0, noise=0.3)),
                     ('ell 8, noise 0.3', dict(ell=8.0, noise=0.3)), ('ell 12, noise 0.3', dict(ell=12.0, noise=0.3)), ('ell 8, noise 0.03', dict(ell=8.0, noise=0.03))]:
        e = np.zeros(A['n'])
        for te in folds:
            tr = np.setdiff1d(idx, te)
            p, _ = run(X[tr], y[tr], yp[tr], X[te], **kw)
            e[te] = verr(p, y[te])
        ec = {}
        m = ModelB(X[idx], y[idx], yp[idx], **kw)
        for c, C in clips.items():
            ec[c] = round(float(verr(m.predict(C['X']), C['y']).mean() * 100), 2)
        score = float(e[idx].mean() * 100)
        print(f'  {name:20s} mean {score:5.2f}  median {np.median(e[idx])*100:5.2f}  p90 {np.percentile(e[idx],90)*100:5.2f}   clips (not trained on): {ec}', flush=True)
        if name != 'trend only' and (best is None or score < best[0]):
            best = (score, name, kw)
    kw = best[2]; out['kriging'] = dict(name=best[1], cv_err_pct=best[0])
    print('  chosen:', best[1])

    # ---- leave-one-family-out with the chosen setting (signals + errors), and in-family folds
    Sig = np.zeros((A['n'], len(SIG_NAMES))); E = np.zeros(A['n']); Etrend = np.zeros(A['n'])
    for f in fams:
        te = fam == f; tr = ~te & (factory | np.isin(fam, [x for x in NEVER if x != f]))
        tr = ~te                                                # train on every other family
        p, s = run(X[tr], y[tr], yp[tr], X[te], **kw); Sig[te] = s; E[te] = verr(p, y[te])
        p0, _ = run(X[tr], y[tr], yp[tr], X[te], use_gp=False); Etrend[te] = verr(p0, y[te])
    Sig_in = np.zeros_like(Sig); E_in = np.full(A['n'], np.nan)
    for te in folds:
        tr = np.setdiff1d(idx, te)
        p, s = run(X[tr], y[tr], yp[tr], X[te], **kw); Sig_in[te] = s; E_in[te] = verr(p, y[te])
    print('\nleave-one-family-out error (%), model B | trend only:')
    for f in fams:
        mk = fam == f
        print(f'  {f:9s} n={mk.sum():4d}  {E[mk].mean()*100:6.1f} | {Etrend[mk].mean()*100:6.1f}')
    print('signals vs "more than 10% wrong" (AUROC), leave-family-out:', {n: round(auroc(Sig[:, i], E > TOL), 3) for i, n in enumerate(SIG_NAMES)})
    print('signals vs "more than 10% wrong" (AUROC), in-family folds :', {n: round(auroc(Sig_in[idx, i], E_in[idx] > TOL), 3) for i, n in enumerate(SIG_NAMES)})

    # ---- B. the gate
    Scal = np.concatenate([Sig, Sig_in[idx]]); Ecal = np.concatenate([E, E_in[idx]])
    print('\nB. gate (doubt fitted on leave-family-out + in-family scores; tolerance 10%, alpha 0.10)')
    for label, use in (('all six', (0, 1, 2, 3, 4, 5)), ('model A four', (0, 1, 2, 3)), ('four + loc', (0, 1, 2, 3, 5)), ('four + gsd', (0, 1, 2, 3, 4))):
        d = Doubt(Scal, Ecal, use=use, alpha=ALPHA)
        b, b_in = d.bound(Sig), d.bound(Sig_in[idx])
        print(f'  {label:13s} w={np.round(d.w,2)} q={d.q:.2f} | LOFO: sure {np.mean(b<=TOL)*100:4.1f}% false-sure {int(((b<=TOL)&(E>TOL)).sum())}/{int((b<=TOL).sum())} coverage {np.mean(E<=b)*100:4.1f}% AUROC {auroc(b,E>TOL):.3f}'
              f' | in-family: sure {np.mean(b_in<=TOL)*100:4.1f}% false-sure {int(((b_in<=TOL)&(E_in[idx]>TOL)).sum())}/{int((b_in<=TOL).sum())} coverage {np.mean(E_in[idx]<=b_in)*100:4.1f}%')
        if label == 'all six':
            dbt = d
            for f in fams:
                mk = fam == f
                print(f'       {f:9s} n={mk.sum():4d} err {E[mk].mean()*100:5.1f}%  sure {int((b[mk]<=TOL).sum()):4d}  false-sure {int(((b[mk]<=TOL)&(E[mk]>TOL)).sum()):3d}  covered {np.mean(E[mk]<=b[mk])*100:5.1f}%')

    # ---- C. the learn step on never-seen families
    print('\nC. learning a never-seen family from k solver runs (factory model + k runs; tested on the rest of that family)')
    base = np.where(factory)[0]
    res_c = {}
    for f in NEVER:
        fi = np.where(fam == f)[0]
        r2 = np.random.default_rng(1); r2.shuffle(fi)
        hold = fi[40:] if len(fi) > 60 else fi[len(fi) // 2:]
        pool = fi[:40] if len(fi) > 60 else fi[:len(fi) // 2]
        rows = []
        for kk in (0, 1, 2, 5, 10, 20, 40):
            if kk > len(pool):
                continue
            tr = np.concatenate([base, pool[:kk]])
            p, s = run(X[tr], y[tr], yp[tr], X[hold], **kw)
            e = verr(p, y[hold]); b = dbt.bound(s)
            rows.append(dict(k=kk, err=float(e.mean() * 100), sure=int((b <= TOL).sum()), false_sure=int(((b <= TOL) & (e > TOL)).sum()), n=len(hold), coverage=float(np.mean(e <= b) * 100)))
            print(f'  {f:9s} k={kk:2d}  err {e.mean()*100:5.1f}%  sure {int((b<=TOL).sum()):3d}/{len(hold)}  false-sure {int(((b<=TOL)&(e>TOL)).sum()):3d}  covered {np.mean(e<=b)*100:5.1f}%', flush=True)
        res_c[f] = rows
    out['learn'] = res_c

    # ---- the performer's clips with the factory model
    m = ModelB(X[base], y[base], yp[base], **kw)
    print('\nperformer clips (factory model B, not trained or calibrated on them):')
    for c, C in clips.items():
        p, s = m.signals(C['X']); e = verr(p, C['y']); b = dbt.bound(s)
        print(f'  {c:7s} n={C["n"]:3d} err {e.mean()*100:5.1f}% (max {e.max()*100:5.1f})  sure {int((b<=TOL).sum()):3d}  false-sure {int(((b<=TOL)&(e>TOL)).sum())}  covered {np.mean(e<=b)*100:5.1f}%')
    json.dump(out, open('../../out/study3.json', 'w'), indent=1)
    print(f'\ndone in {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()

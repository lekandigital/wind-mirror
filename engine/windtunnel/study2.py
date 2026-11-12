"""Study 2 (pitch-night data only): the doubt gate, calibrated by leaving whole pose families out.

For each of the seven pose families in the pitch-night runs, the model is trained on the other six and scored on the one
left out. Pooled, those scores say how wrong the model is on kinds of pose it has never seen, and how well each signal
predicts it. The doubt formula and its conformal factor are fitted on those leave-family-out scores, then applied (without
any change) to the performer's three clips, which took no part in training or calibration.
"""
import json, numpy as np
import data as D, geom as G
from surrogate import Surrogate, Doubt, verr, auroc, SIG_NAMES

TOL, ALPHA = 0.10, 0.10


def main():
    P = D.load('../../out/pitch/poses_v1.jsonl', '../../out/pitch/feat_cache.npz')
    clips = {c: D.load(f'../../out/pitch/clip_{c}.jsonl', '../../out/pitch/feat_cache.npz', source='clip_' + c) for c in ('fly', 'puppet', 'row')}
    fams = sorted(set(P['fam']))
    print('families', {f: int((P['fam'] == f).sum()) for f in fams})
    S_all = np.zeros((P['n'], 4)); E_all = np.zeros(P['n']); pred = np.zeros((P['n'], 3))
    for f in fams:
        te = P['fam'] == f; tr = ~te
        m = Surrogate(P['X'][tr], P['y'][tr], P['yp'][tr])
        p, S = m.signals(P['X'][te])
        S_all[te] = S; E_all[te] = verr(p, P['y'][te]); pred[te] = p
    # in-family reference: 5-fold inside the three familiar families
    rng = np.random.default_rng(0)
    fam3 = np.isin(P['fam'], ['stand', 'tuck', 'wide']); idx = np.where(fam3)[0]; rng.shuffle(idx)
    S_in = np.zeros((P['n'], 4)); E_in = np.full(P['n'], np.nan)
    for kf in range(5):
        te = idx[kf::5]; tr = np.setdiff1d(idx, te)
        m = Surrogate(P['X'][tr], P['y'][tr], P['yp'][tr])
        p, S = m.signals(P['X'][te]); S_in[te] = S; E_in[te] = verr(p, P['y'][te])
    print('\nleave-family-out error by family (%):', {f: round(float(E_all[P['fam'] == f].mean() * 100), 1) for f in fams})
    print('5-fold error inside the familiar families (%):', round(float(np.nanmean(E_in) * 100), 2))
    print('\nhow well each signal ranks answers that are more than 10% wrong (leave-family-out, all 351): ',
          {n: round(auroc(S_all[:, i], E_all > TOL), 3) for i, n in enumerate(SIG_NAMES)})
    print('rank correlation with error:', {n: round(float(np.corrcoef(np.argsort(np.argsort(S_all[:, i])), np.argsort(np.argsort(E_all)))[0, 1]), 3) for i, n in enumerate(SIG_NAMES)})

    # calibration set: leave-family-out scores of every family, plus the in-family folds (so sigma is anchored at both ends)
    Scal = np.concatenate([S_all, S_in[idx]]); Ecal = np.concatenate([E_all, E_in[idx]])
    out = {}
    for label, use in (('all four', (0, 1, 2, 3)), ('lev+knn+dis', (0, 1, 2)), ('lev only', (0,)), ('knn only', (1,)), ('dis only', (2,)), ('par only', (3,))):
        d = Doubt(Scal, Ecal, use=use, alpha=ALPHA)
        b_lofo = d.bound(S_all); b_in = d.bound(S_in[idx])
        row = dict(w=[round(float(x), 3) for x in d.w], q=round(d.q, 3),
                   auroc_bound=round(auroc(b_lofo, E_all > TOL), 3),
                   coverage_lofo=round(float((E_all <= b_lofo).mean()), 3), coverage_in=round(float((E_in[idx] <= b_in).mean()), 3),
                   sure_in=round(float((b_in <= TOL).mean()), 3), sure_lofo=round(float((b_lofo <= TOL).mean()), 3),
                   false_sure_lofo=int(((b_lofo <= TOL) & (E_all > TOL)).sum()), n_bad_lofo=int((E_all > TOL).sum()),
                   false_sure_in=int(((b_in <= TOL) & (E_in[idx] > TOL)).sum()), n_bad_in=int((E_in[idx] > TOL).sum()))
        out[label] = row
        print(f'\n{label}: {row}')
        if label == 'all four':
            best = d
            print('   by family (leave-family-out):')
            for f in fams:
                mk = P['fam'] == f
                print(f'     {f:9s} n={mk.sum():3d} err {E_all[mk].mean()*100:5.1f}%  bound median {np.median(b_lofo[mk])*100:6.1f}%  sure {int((b_lofo[mk] <= TOL).sum()):3d}  false-sure {int(((b_lofo[mk] <= TOL) & (E_all[mk] > TOL)).sum())}  covered {float((E_all[mk] <= b_lofo[mk]).mean())*100:5.1f}%')

    # the performer's clips: model trained on ALL pitch-night random poses (familiar + the four held-out families), doubt formula untouched
    m = Surrogate(P['X'], P['y'], P['yp'])
    turn_frames = {450, 465, 510, 525, 540}
    print('\nperformer clips (never trained or calibrated on), model trained on all 351 random poses:')
    for c, C in clips.items():
        p, S = m.signals(C['X']); e = verr(p, C['y']); b = best.bound(S)
        groups = {'all': np.ones(C['n'], bool)}
        if c == 'puppet':
            t = np.array([r['frame'] in turn_frames for r in C['R']]); groups = {'ordinary': ~t, 'side-on turn': t}
        for g, mk in groups.items():
            print(f'  {c:7s} {g:13s} n={mk.sum():3d} err {e[mk].mean()*100:5.1f}% (max {e[mk].max()*100:5.1f})  bound median {np.median(b[mk])*100:5.1f}%  sure {int((b[mk] <= TOL).sum()):3d}  false-sure {int(((b[mk] <= TOL) & (e[mk] > TOL)).sum())}  covered {float((e[mk] <= b[mk]).mean())*100:5.1f}%')
    # the pitch's failure scenario: add the Fly clip's 77 runs to training, then look at the Puppet turn frames
    F = clips['fly']
    m2 = Surrogate(np.concatenate([P['X'], F['X']]), np.concatenate([P['y'], F['y']]), np.concatenate([P['yp'], F['yp']]))
    print('\nafter learning the Fly clip (the step where the pitch-night gate let 3 wrong answers through):')
    for c in ('puppet', 'row'):
        C = clips[c]; p, S = m2.signals(C['X']); e = verr(p, C['y']); b = best.bound(S)
        t = np.array([r['frame'] in turn_frames for r in C['R']]) if c == 'puppet' else np.zeros(C['n'], bool)
        for g, mk in (('ordinary', ~t), ('side-on turn', t)):
            if mk.any():
                print(f'  {c:7s} {g:13s} n={mk.sum():3d} err {e[mk].mean()*100:5.1f}% (max {e[mk].max()*100:5.1f})  bound median {np.median(b[mk])*100:5.1f}%  sure {int((b[mk] <= TOL).sum()):3d}  false-sure {int(((b[mk] <= TOL) & (e[mk] > TOL)).sum())}')
    json.dump(out, open('../../out/study2.json', 'w'), indent=1)


if __name__ == '__main__':
    main()

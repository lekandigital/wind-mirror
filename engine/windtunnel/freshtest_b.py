"""The fresh test of frozen model B (docs/PREREGISTRATION_B.md).

Loads models/model_b_store.npz (factory runs + calibration, nothing learned since) and sealed solver runs, and reports per
group: force error, share labelled sure, false-sure, coverage of the stated bound. With --learn it also runs the learn test
on single moves: teach k = 2 and 5 solver runs spread over the move through Engine.learn, test on the rest.

Usage: python freshtest_b.py <store.npz> <out.json> <label>=<runs.jsonl> [...] [--learn <label>=<runs.jsonl>]
"""
import sys, json, os, tempfile, shutil
import numpy as np
import data as D
from surrogate import verr, auroc
from engine import Engine

TOL = 0.10


def stats(e, b, drag_err=None):
    s = b <= TOL; ns = int(s.sum()); fs = int((s & (e > TOL)).sum())
    cov = float((e <= b).mean() * 100)
    verdict = None
    if ns >= 20:
        share = 100.0 * fs / ns
        verdict = 'pass' if (share <= 10 and cov >= 80) else ('fail' if (share > 20 or cov < 70) else 'marginal')
    return dict(n=int(len(e)), err_mean_pct=round(float(e.mean() * 100), 2), err_median_pct=round(float(np.median(e) * 100), 2), err_p90_pct=round(float(np.percentile(e, 90) * 100), 2),
                drag_err_mean_pct=None if drag_err is None else round(float(drag_err.mean() * 100), 2),
                wrong_gt_tol=int((e > TOL).sum()), sure=ns, sure_pct=round(100.0 * ns / len(e), 1), false_sure=fs,
                false_sure_pct_of_sure=round(100.0 * fs / ns, 1) if ns else None, err_of_sure_mean_pct=round(float(e[s].mean() * 100), 2) if ns else None,
                err_of_sure_max_pct=round(float(e[s].max() * 100), 2) if ns else None, coverage_pct=round(cov, 1), bound_median_pct=round(float(np.median(b) * 100), 1),
                auroc_bound_for_wrong=round(auroc(b, e > TOL), 3), verdict=verdict)


def show(title, rows):
    print(f'\n== {title} ==')
    print(f'{"group":30s} {"n":>5s} {"err%":>6s} {"sure":>5s} {"sure%":>6s} {"false-sure":>10s} {"of sure%":>8s} {"coverage%":>9s} {"bound med%":>10s}  verdict')
    for g, v in rows.items():
        print(f'{g:30s} {v["n"]:5d} {v["err_mean_pct"]:6.1f} {v["sure"]:5d} {v["sure_pct"]:6.1f} {v["false_sure"]:10d} {str(v["false_sure_pct_of_sure"]):>8s} {v["coverage_pct"]:9.1f} {v["bound_median_pct"]:10.1f}  {v["verdict"] or "-"}')


def main():
    store, out = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    learn_sets = []
    if '--learn' in args:
        i = args.index('--learn'); learn_sets = args[i + 1:]; args = args[:i]
    tmp = tempfile.mkdtemp()
    E = Engine(tmp, store=store)
    report = dict(store=store, runs_in_model=int(E.n_runs), conformal_factor=E.doubt.q, floor=E.doubt.s0, tests={}, learn={})
    raw = {}
    for a in args:
        label, path = a.split('=', 1)
        S = D.load(path, path.replace('.jsonl', '_feat.npz'), source=label)
        p, b, sig, _ = E.check_features(S['X'])
        e = verr(p, S['y']); de = np.abs(p[:, 0] - S['y'][:, 0]) / S['y'][:, 0]
        R = S['R']
        groups = {'ALL': np.ones(S['n'], bool)}
        shaped = np.array([bool(r.get('body')) for r in R])
        if shaped.any():
            groups['reference body'] = ~shaped; groups['other body shapes'] = shaped
        for key, name in (('posture', 'posture'), ('family', ''), ('clip', 'clip')):
            vals = sorted(set(str(r.get(key)) for r in R if r.get(key) is not None))
            if 1 < len(vals) <= 30 or (key == 'clip' and vals):
                for v in vals:
                    groups[(name + ' ' if name else '') + v] = np.array([str(r.get(key)) == v for r in R])
        if any('yaw_deg' in r for r in R):
            yaw = np.array([abs(r.get('yaw_deg', 0.0)) for r in R])
            groups['heading within 50 deg'] = yaw <= 50; groups['heading beyond 50 deg'] = yaw > 50
        rows = {g: stats(e[m], b[m], de[m]) for g, m in groups.items() if m.sum() > 0}
        report['tests'][label] = rows
        raw[label] = dict(err=e, bound=b, drag_err=de, sig=sig)
        show(f'{label}: {S["n"]} sealed runs', rows)
    for a in learn_sets:
        label, path = a.split('=', 1)
        S = D.load(path, path.replace('.jsonl', '_feat.npz'), source=label)
        clips = sorted(set(r.get('clip') for r in S['R']))
        for c in clips:
            idx = np.array([i for i, r in enumerate(S['R']) if r.get('clip') == c])
            idx = idx[np.argsort([S['R'][i]['t'] for i in idx])]
            rows = {}
            for k in (0, 2, 5):
                tmp2 = tempfile.mkdtemp(); E2 = Engine(tmp2, store=store)
                teach = idx[np.linspace(0, len(idx) - 1, k).round().astype(int)] if k else idx[:0]
                if k:
                    E2.learn([dict(features=[float(v) for v in S['X'][i]], force=[float(v) for v in S['y'][i]], parts=S['yp'][i].tolist()) for i in teach])
                te = np.setdiff1d(idx, teach)
                p, b, _, _ = E2.check_features(S['X'][te])
                rows[f'k={k}'] = dict(stats(verr(p, S['y'][te]), b), conformal_factor=round(E2.doubt.q, 3))
                shutil.rmtree(tmp2, ignore_errors=True)
            ok = rows['k=5']['err_mean_pct'] <= rows['k=0']['err_mean_pct'] and (rows['k=5']['sure'] == 0 or rows['k=5']['false_sure'] / rows['k=5']['sure'] <= 0.10)
            report['learn'][f'{label}:{c}'] = dict(rows=rows, passes=bool(ok))
            show(f'learn test, move in {c} ({len(idx)} poses): {"PASS" if ok else "FAIL"}', rows)
    json.dump(report, open(out, 'w'), indent=1)
    np.savez(out.replace('.json', '_raw.npz'), **{f'{k}_{kk}': vv for k, v in raw.items() for kk, vv in v.items()})
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()

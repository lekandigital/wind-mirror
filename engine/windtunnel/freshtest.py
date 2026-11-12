"""The fresh test of frozen model A (see docs/PREREGISTRATION.md). Loads models/model_a.npz and dataset-v2 runs it has
never seen, and reports, per pose family: force error, the share of answers labelled 'sure', how many of those were wrong
by more than the tolerance (false-sure), and how often the solver's answer fell inside the stated bound (coverage).

Usage: python freshtest.py <model.npz> <label>=<runs.jsonl> [<label>=<runs.jsonl> ...] [--out report.json]
"""
import sys, json, numpy as np
import data as D
from model_io import Model
from surrogate import verr, auroc


def evaluate(model, Dset, groups):
    r = model.check(Dset['X'])
    e = verr(r['force'], Dset['y']); b = r['bound']; s = r['sure']
    tol = model.tol
    rows = {}
    for g, mk in groups.items():
        if mk.sum() == 0:
            continue
        ns = int(s[mk].sum())
        rows[g] = dict(n=int(mk.sum()), err_mean_pct=round(float(e[mk].mean() * 100), 2), err_median_pct=round(float(np.median(e[mk]) * 100), 2),
                       drag_err_mean_pct=round(float((np.abs(r['force'][mk, 0] - Dset['y'][mk, 0]) / Dset['y'][mk, 0]).mean() * 100), 2),
                       wrong_gt_tol=int((e[mk] > tol).sum()), sure=ns, sure_pct=round(100 * ns / int(mk.sum()), 1),
                       false_sure=int((s[mk] & (e[mk] > tol)).sum()),
                       false_sure_pct_of_sure=round(100 * float((s[mk] & (e[mk] > tol)).sum()) / ns, 1) if ns else None,
                       err_of_sure_mean_pct=round(float(e[mk][s[mk]].mean() * 100), 2) if ns else None,
                       err_of_sure_max_pct=round(float(e[mk][s[mk]].max() * 100), 2) if ns else None,
                       coverage_pct=round(float((e[mk] <= b[mk]).mean() * 100), 1), bound_median_pct=round(float(np.median(b[mk]) * 100), 1),
                       auroc_bound_for_wrong=round(auroc(b[mk], e[mk] > tol), 3))
    return rows, dict(err=e, bound=b, sure=s)


def main():
    model = Model(sys.argv[1])
    out = None
    report = {}
    for a in sys.argv[2:]:
        if a == '--out':
            continue
        if sys.argv[sys.argv.index(a) - 1] == '--out':
            out = a; continue
        label, path = a.split('=', 1)
        Dset = D.load(path, path.replace('.jsonl', '_feat.npz'), source=label)
        fam = Dset['fam']
        shaped = np.array([bool(r.get('body')) for r in Dset['R']])
        groups = {'ALL': np.ones(Dset['n'], bool), 'reference body': ~shaped, 'other body shapes': shaped}
        groups.update({'family ' + f: fam == f for f in sorted(set(fam))})
        rows, raw = evaluate(model, Dset, groups)
        report[label] = rows
        print(f'\n== {label}: {Dset["n"]} runs ==')
        print(f'{"group":22s} {"n":>5s} {"err%":>6s} {"sure":>5s} {"sure%":>6s} {"false-sure":>10s} {"of sure%":>8s} {"err of sure%":>12s} {"coverage%":>9s} {"bound med%":>10s} {"AUROC":>6s}')
        for g, v in rows.items():
            print(f'{g:22s} {v["n"]:5d} {v["err_mean_pct"]:6.1f} {v["sure"]:5d} {v["sure_pct"]:6.1f} {v["false_sure"]:10d} {str(v["false_sure_pct_of_sure"]):>8s} {str(v["err_of_sure_mean_pct"]):>12s} {v["coverage_pct"]:9.1f} {v["bound_median_pct"]:10.1f} {v["auroc_bound_for_wrong"]:6.3f}')
        if out:
            np.savez(out.replace('.json', f'_{label}.npz'), err=raw['err'], bound=raw['bound'], sure=raw['sure'], fam=fam, shaped=shaped, y=Dset['y'])
    if out:
        json.dump(report, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main()

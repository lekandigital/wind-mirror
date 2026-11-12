"""Before/after numbers for the learning loop on her held-out clips, split into ordinary frames and the turn to profile.
Usage: loop_report.py <before.npz> <after_rule1.npz> <after_rule2.npz>"""
import sys, json
import numpy as np
out = {}
for name, p in zip(('before', 'after_rule1', 'after_rule2'), sys.argv[1:4]):
    d = np.load(p)
    t, e, s, y, pr = d['t'], d['err'], d['sure'], d['y'], d['pred']
    de = np.abs(pr[:, 0] - y[:, 0]) / y[:, 0]
    turn = np.zeros(len(t), bool); turn[:12] = (t[:12] >= 14.9) & (np.abs(t[:12] - 16.5) > 0.01)       # the first 12 rows are the Puppet clip
    def blk(m):
        a = s[m]
        return dict(n=int(m.sum()), force_err_pct=round(float(e[m].mean() * 100), 1), drag_err_pct=round(float(de[m].mean() * 100), 1),
                    answered=int(a.sum()), answered_force_err_pct=round(float(e[m][a].mean() * 100), 1) if a.any() else None,
                    answered_worst_pct=round(float(e[m][a].max() * 100), 1) if a.any() else None,
                    wrong_by_more_than_10pct=int((e[m] > 0.10).sum()), wrong_and_answered=int(((e[m] > 0.10) & a).sum()),
                    doubt_range=[round(float(d['doubt'][m].min()), 2), round(float(d['doubt'][m].max()), 2)])
    out[name] = dict(tau=round(float(d['tau']), 3), ordinary=blk(~turn), turn=blk(turn))
print(json.dumps(out, indent=1))

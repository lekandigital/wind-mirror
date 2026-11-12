"""Diverse (farthest-point) and random subsets of cmu_all.jsonl, plus cmu_stats.json.

Usage: python subsets.py <out dir containing cmu_all.jsonl> [--n 4000] [--seed 0]
Writes cmu_diverse_4000.jsonl (in selection order, 'rank' 0..n-1), cmu_random_4000.jsonl (sorted by idx), cmu_stats.json.
Every subset line is the cmu_all record plus 'idx' (0-based line number in cmu_all.jsonl).
Pose space: the 12 unit vectors flattened (36 numbers), Euclidean distance.
FPS starts from the cmu_all pose nearest to bodies.NAMED['standing'] (bodies.make_pose(), facing the wind).
"""
import sys, os, json, argparse, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'windtunnel'))
import bodies
import categories


def load(path):
    recs = [json.loads(l) for l in open(path)]
    X = np.array([np.asarray(r['pose'], float).reshape(-1) for r in recs])
    return recs, X


def fps_select(X, start, n):
    sel = [start]
    d = np.linalg.norm(X - X[start], axis=1)
    radius = []
    for _ in range(n - 1):
        i = int(np.argmax(d))
        radius.append(float(d[i]))
        sel.append(i)
        d = np.minimum(d, np.linalg.norm(X - X[i], axis=1))
    return sel, radius


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir')
    ap.add_argument('--n', type=int, default=4000)
    ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args()
    recs, X = load(os.path.join(a.outdir, 'cmu_all.jsonl'))
    N = len(recs)
    assert X.shape[1] == 36, X.shape

    stand = np.asarray(bodies.pose_to_list(bodies.make_pose(**bodies.NAMED['standing'])), float).reshape(-1)
    d0 = np.linalg.norm(X - stand, axis=1)
    start = int(np.argmin(d0))
    print(f'{N} poses; FPS start = idx {start} {recs[start]["id"]} "{recs[start]["desc"]}" (distance to bodies standing pose {d0[start]:.3f})')
    sel, radius = fps_select(X, start, a.n)
    print(f'FPS covering radius after {a.n}: {radius[-1]:.3f} (first pick {radius[0]:.3f})')

    rng = np.random.default_rng(a.seed)
    pool = np.setdiff1d(np.arange(N), np.array(sel))
    rnd = np.sort(rng.choice(pool, size=a.n, replace=False))
    assert not set(rnd.tolist()) & set(sel)

    with open(os.path.join(a.outdir, f'cmu_diverse_{a.n}.jsonl'), 'w') as f:
        for k, i in enumerate(sel):
            f.write(json.dumps(dict(recs[i], idx=int(i), rank=k), separators=(',', ':')) + '\n')
    with open(os.path.join(a.outdir, f'cmu_random_{a.n}.jsonl'), 'w') as f:
        for i in rnd:
            f.write(json.dumps(dict(recs[i], idx=int(i)), separators=(',', ':')) + '\n')

    # stats
    trials = collections.OrderedDict()
    for r in recs:
        trials.setdefault((r['subject'], r['trial']), r)
    prim_poses = collections.Counter(r['coarse'] for r in recs)
    prim_trials = collections.Counter(r['coarse'] for r in trials.values())
    multi_trials = collections.Counter(c for r in trials.values() for c in categories.all_categories(r['desc'], r['cat']))
    multi_poses = collections.Counter()
    for r in recs:
        multi_poses.update(categories.all_categories(r['desc'], r['cat']))
    tu = np.array([r['torso_up'] for r in recs])
    edges = np.round(np.linspace(-1, 1, 21), 3)
    hist, _ = np.histogram(tu, bins=edges)
    ph = np.array([r['pelvis_h'] for r in recs])
    div_tu, _ = np.histogram(tu[sel], bins=edges)
    stats = dict(
        n_trials=len(trials), n_poses=N, n_subjects=len(set(r['subject'] for r in recs)),
        sample_hz=2.0, edge_skip_s=0.25,
        n_trials_desc_unknown=sum(1 for r in trials.values() if r['desc'] == 'unknown'),
        n_poses_desc_unknown=int(sum(1 for r in recs if r['desc'] == 'unknown')),
        n_poses_fps_assumed=int(sum(1 for r in recs if r['fps_assumed'])),
        n_poses_heading_fallback=int(sum(1 for r in recs if r['heading_fallback'])),
        category_rule='primary = first matching keyword rule in categories.RULES order, applied to the trial description; '
                      'if none matches (or it is unknown), applied to the subject description; else other',
        category_order=categories.CATEGORIES,
        trials_per_category=dict(prim_trials.most_common()),
        poses_per_category=dict(prim_poses.most_common()),
        trials_per_category_multilabel=dict(multi_trials.most_common()),
        poses_per_category_multilabel=dict(multi_poses.most_common()),
        diverse_poses_per_category=dict(collections.Counter(recs[i]['coarse'] for i in sel).most_common()),
        torso_up_hist=dict(bin_edges=edges.tolist(), counts_all=hist.tolist(), counts_diverse=div_tu.tolist()),
        torso_up_below_0=int((tu < 0).sum()), torso_up_below_0p5=int((tu < 0.5).sum()),
        pelvis_h_quantiles={str(q): round(float(np.quantile(ph, q)), 4) for q in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)},
        fps_start=dict(idx=start, id=recs[start]['id'], desc=recs[start]['desc'], dist_to_bodies_standing=round(float(d0[start]), 4)),
        fps_radius_first=round(radius[0], 4), fps_radius_last=round(radius[-1], 4),
        random_seed=a.seed,
    )
    json.dump(stats, open(os.path.join(a.outdir, 'cmu_stats.json'), 'w'), indent=1)
    print(json.dumps({k: stats[k] for k in ('n_trials', 'n_poses', 'n_subjects', 'trials_per_category', 'poses_per_category',
                                            'diverse_poses_per_category', 'torso_up_below_0', 'n_poses_heading_fallback')}, indent=1))


if __name__ == '__main__':
    main()

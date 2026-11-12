"""'A thousand designs': check N random body positions at once and time it.
Usage: thousand.py <pair.pt> <N> <out.json> [seed]"""
import sys, json, time
import numpy as np
from multiprocessing import Pool
import torch
import bodies as B
from check import Check, pose_features


def make(i):
    rng = np.random.default_rng(900000 + i)
    if i % 8 == 7:
        pose, fam = B.sample_ood(rng, ['prone', 'side', 'back', 'inverted'][(i // 8) % 4])
    else:
        pose, fam = B.sample_pose(rng)
    _, info = B.voxelize(pose, (224, 128, 128), 64)
    return B.pose_to_list(pose), pose_features(pose, info['area_m2']), str(fam)


if __name__ == '__main__':
    N = int(sys.argv[2])
    t0 = time.perf_counter()
    with Pool(16) as p:
        out = p.map(make, range(N), chunksize=32)
    t_geo = time.perf_counter() - t0
    X = np.array([o[1] for o in out], float)
    fam = [o[2] for o in out]
    ck = Check(sys.argv[1])
    torch.set_num_threads(1)
    ck.check_features(X[:10])
    best = 1e9
    for _ in range(5):
        t0 = time.perf_counter(); r = ck.check_features(X); best = min(best, time.perf_counter() - t0)
    t0 = time.perf_counter(); r2 = ck.check_features(X, with_distance=False); t_nodist = time.perf_counter() - t0
    known = [f in ('stand', 'tuck', 'wide') for f in fam]
    known = np.array(known)
    res = dict(N=N, check_ms_total_cpu_1thread=round(best * 1000, 2), check_microseconds_each=round(best / N * 1e6, 1),
               two_models_only_ms_total=round(t_nodist * 1000, 2), geometry_s_16_cores=round(t_geo, 2),
               sure=int(r['sure'].sum()), sent_to_solver=int((~r['sure']).sum()),
               sure_among_familiar_pct=round(float(r['sure'][known].mean() * 100), 1), sure_among_never_seen_pct=round(float(r['sure'][~known].mean() * 100), 1),
               n_familiar=int(known.sum()), n_never_seen=int((~known).sum()))
    json.dump(dict(summary=res, poses=[o[0] for o in out], CdA=r['CdA'].tolist(), doubt=r['doubt'].tolist(), sure=r['sure'].tolist(), family=fam), open(sys.argv[3], 'w'))
    print(json.dumps(res))

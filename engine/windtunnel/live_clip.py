"""Run the check on every frame of a tracked clip (30 per second), the way it would run live.
Usage: live_clip.py <poses_30fps.json> <pair.pt> <out.npz>"""
import sys, json, time
import numpy as np
from multiprocessing import Pool
import bodies as B
from check import Check, pose_features


def area(pl):
    pose = B.pose_from_list(pl)
    _, info = B.voxelize(pose, (224, 128, 128), 64)
    return pose_features(pose, info['area_m2'])


if __name__ == '__main__':
    items = json.load(open(sys.argv[1]))
    t0 = time.perf_counter()
    with Pool(16) as p:
        A = p.map(area, [it['pose'] for it in items], chunksize=16)
    t_geo = time.perf_counter() - t0
    X = np.array(A, float)
    ck = Check(sys.argv[2])
    t0 = time.perf_counter()
    r = ck.check_features(X)
    t_chk = time.perf_counter() - t0
    np.savez(sys.argv[3], t=np.array([it['t'] for it in items]), frame=np.array([it['frame'] for it in items]), CdA=r['CdA'], doubt=r['doubt'],
             sure=r['sure'], area=X[:, -1], tau=ck.tau, **{'sig_' + k: v for k, v in r['signals'].items()})
    print(json.dumps(dict(frames=len(items), sure_pct=round(float(r['sure'].mean() * 100), 1), check_ms_per_frame=round(t_chk / len(items) * 1000, 4),
                          geometry_s_total_16_cores=round(t_geo, 2), CdA_min=round(float(r['CdA'].min()), 3), CdA_max=round(float(r['CdA'].max()), 3))))

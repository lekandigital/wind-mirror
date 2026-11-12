"""What an agent calls. Three tools, all returning JSON:

  check   --poses poses.json            -> for each pose: drag area, doubt score, verdict (sure / ask the solver)
  solve   --poses poses.json --out DIR  -> runs the real flow solver on each pose (about 20 s each on the 3090 Ti)
  learn   --data a.jsonl [b.jsonl ...]  -> retrains the two small models on every solver run so far (seconds, CPU)

A pose is a dict of named angles (degrees), the arguments of bodies.make_pose:
  {"lean": 60, "head_ext": 40, "arms": [[70, 80, 110, 60], [70, 80, 110, 60]], "legs": [[75, 5, 120], [75, 5, 120]], "yaw": 0}
"""
import sys, json, time, os, argparse
import numpy as np
import bodies as B
from check import pose_features


def to_pose(spec):
    kw = dict(spec)
    kw.pop('name', None)
    if 'arms' in kw:
        kw['arms'] = tuple(tuple(a) for a in kw['arms'])
    if 'legs' in kw:
        kw['legs'] = tuple(tuple(a) for a in kw['legs'])
    return B.make_pose(**kw)


def _feat(spec):
    p = to_pose(spec)
    _, info = B.voxelize(p, (224, 128, 128), 64)
    return pose_features(p, info['area_m2'])


def featurise(specs):
    from multiprocessing import Pool
    if len(specs) < 64:
        return np.array([_feat(s) for s in specs], float)
    with Pool(16) as pool:
        return np.array(pool.map(_feat, specs, chunksize=64), float)


def cmd_check(a):
    from check import Check
    specs = json.load(open(a.poses))
    t0 = time.perf_counter()
    X = featurise(specs)
    t1 = time.perf_counter()
    ck = Check(a.model)
    t2 = time.perf_counter()
    r = ck.check_features(X)
    t3 = time.perf_counter()
    out = [dict(i=i, name=s.get('name'), CdA=round(float(r['CdA'][i]), 4), lift=round(float(r['lift'][i]), 4), doubt=round(float(r['doubt'][i]), 2), sure=bool(r['sure'][i]),
                area_m2=round(float(X[i, -1]), 4)) for i, s in enumerate(specs)]
    res = dict(n=len(specs), n_sure=int(r['sure'].sum()), geometry_wall_s=round(t1 - t0, 2),
               model_and_signals_ms_total=round((t3 - t2) * 1000, 2), model_and_signals_ms_per_pose=round((t3 - t2) / len(specs) * 1000, 4), results=out)
    json.dump(res, open(a.out, 'w')) if a.out else None
    brief = {k: v for k, v in res.items() if k != 'results'}
    print(json.dumps(brief))
    if a.show:
        for label, keep in (('lowest drag among answers the model is sure of', True), ('lowest drag among answers it is NOT sure of', False)):
            order = sorted([o for o in out if o['sure'] == keep], key=lambda o: o['CdA'])
            print(f'  {label} ({len(order)} poses):')
            for o in order[:a.show]:
                print(f"    #{o['i']:<5d} drag area {o['CdA']:.3f}  doubt {o['doubt']:5.2f}  {o['name'] or ''}")


def cmd_solve(a):
    import taichi as ti
    ti.init(arch=ti.cuda, default_fp=ti.f32, device_memory_GB=6, offline_cache=True)
    from lbm import Tunnel
    NX, NY, NZ, H, U, NU = 224, 128, 128, 64, 0.08, 4e-4
    specs = json.load(open(a.poses))
    idx = [int(x) for x in a.only.split(',')] if a.only else range(len(specs))
    T = Tunnel(NX, NY, NZ, U=U, nu=NU, nparts=len(B.PARTS))
    FT = int(NX / U)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    f = open(a.out, 'a')
    for i in idx:
        s = specs[i]
        pose = to_pose(s)
        mask, info = B.voxelize(pose, (NX, NY, NZ), H)
        T.set_solid(mask)
        ti.sync(); t0 = time.time()
        F, series = T.run(int(1.25 * FT), int(1.75 * FT), chunk=200)
        ti.sync(); dt = time.time() - t0
        q = 0.5 * U * U; dx = info['dx_m']; k = dx * dx / q; corr = (1 - info['blockage']) ** 2
        h = len(series) // 2
        rec = dict(i=i, name=s.get('name'), spec=s, split='agent', family='agent', pose=B.pose_to_list(pose), feat=[float(x) for x in B.features(pose)],
                   area_m2=info['area_m2'], blockage=info['blockage'], corr=corr, F_parts=(F * k).tolist(),
                   CdA=float(F[:, 0].sum() * k * corr), ClA=float(F[:, 2].sum() * k * corr),
                   CdA_halves=[float(series[:h].mean() * k * corr), float(series[h:].mean() * k * corr)], seconds=dt)
        f.write(json.dumps(rec) + '\n'); f.flush()
        print(json.dumps(dict(i=i, name=s.get('name'), CdA=round(rec['CdA'], 4), area_m2=round(info['area_m2'], 4), seconds=round(dt, 1))), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    c = sub.add_parser('check'); c.add_argument('--poses', required=True); c.add_argument('--model', default='../out/trust/pair.pt'); c.add_argument('--out'); c.add_argument('--show', type=int, default=0)
    s = sub.add_parser('solve'); s.add_argument('--poses', required=True); s.add_argument('--out', required=True); s.add_argument('--only')
    a = ap.parse_args()
    dict(check=cmd_check, solve=cmd_solve)[a.cmd](a)

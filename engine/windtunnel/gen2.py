"""Dataset v2 runner: reads a queue of {qid, pose, body, family, source, ...}, runs the solver on each, appends one JSON line
per run to <out_dir>/runs.jsonl and (with --fields) saves the mean flow field to <out_dir>/fields/<qid>.npy
(float16, 112 x 64 x 64 x 4: mean velocity in units of the wind speed, and mean (density - 1) x 1000).

Resumable: rerun the same command and finished qids are skipped. Same grid, wind and averaging protocol as the pitch-night runs.

Usage: python gen2.py <queue.jsonl> <out_dir> [--fields] [--limit N]
"""
import sys, json, time, os
import numpy as np
import taichi as ti
from lbm import Tunnel, ti_init
ti_init()
import bodies as B

NX, NY, NZ, H = 224, 128, 128, 64
U, NU = 0.08, 4e-4
WARM_FT, AVG_FT = 1.25, 1.75
PROTOCOL = dict(grid=[NX, NY, NZ], H=H, U=U, nu=NU, warm_ft=WARM_FT, avg_ft=AVG_FT, cs_smag=0.14)


def solve_one(T, pose, body, fields=False):
    mask, info = B.voxelize(pose, (NX, NY, NZ), H, body=body)
    if info['x_range'] is None or info['x_range'][0] < 8 or info['x_range'][1] > NX - 40:
        return None, info, None
    ys = np.where(mask.any(axis=(0, 2)))[0]; zs = np.where(mask.any(axis=(0, 1)))[0]
    if ys.min() < 3 or ys.max() > NY - 4 or zs.max() > NZ - 4:
        return None, info, None
    FT = int(NX / U)
    T.set_solid(mask)
    ti.sync(); t0 = time.time()
    F, series = T.run2(int(WARM_FT * FT), int(AVG_FT * FT), chunk=100, fields=fields)
    ti.sync(); dt = time.time() - t0
    q = 0.5 * U * U
    k = info['dx_m'] ** 2 / q
    corr = (1 - info['blockage']) ** 2
    h = len(series) // 2
    tot = F.sum(0) * k * corr                                   # [drag, side, lift] force areas, m^2, blockage-corrected
    halves = [(series[:h].mean(0) * k * corr).tolist(), (series[h:].mean(0) * k * corr).tolist()]
    rec = dict(area_m2=info['area_m2'], blockage=info['blockage'], corr=corr, F_parts=(F * k).tolist(),
               CdA=float(tot[0]), CyA=float(tot[1]), ClA=float(tot[2]), CdA_halves=[halves[0][0], halves[1][0]], F_halves=halves,
               seconds=dt, pelvis_height_m=info['pelvis_height_m'])
    rec['diverged'] = bool(not np.isfinite(F).all())
    fld = None
    if fields:
        a = T.mean_fields(2)
        a[..., :3] /= U
        a[..., 3] *= 1000.0
        fld = a.astype(np.float16)
    return rec, info, fld


def main():
    qpath, out = sys.argv[1], sys.argv[2]
    fields = '--fields' in sys.argv
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 10 ** 9
    os.makedirs(out + '/fields', exist_ok=True)
    runs = out + '/runs.jsonl'
    done = set()
    if os.path.exists(runs):
        for l in open(runs):
            try:
                done.add(json.loads(l)['qid'])
            except Exception:
                pass
    Q = [json.loads(l) for l in open(qpath)]
    T = Tunnel(NX, NY, NZ, U=U, nu=NU, nparts=len(B.PARTS))
    f = open(runs, 'a')
    n = 0
    for it in Q:
        if it['qid'] in done or n >= limit:
            continue
        pose = B.pose_from_list(it['pose'])
        rec, info, fld = solve_one(T, pose, it.get('body'), fields)
        if rec is None:
            f.write(json.dumps(dict(qid=it['qid'], skipped='outside the tunnel', family=it.get('family'))) + '\n'); f.flush()
            continue
        rec = dict(it, **rec, protocol=PROTOCOL)
        f.write(json.dumps(rec) + '\n'); f.flush()
        if fld is not None:
            np.save(f'{out}/fields/{it["qid"]}.npy', fld)
        n += 1
        if n % 10 == 1:
            print(f'{time.strftime("%H:%M:%S")} {n} {it["qid"]} {it.get("family", ""):9s} A={rec["area_m2"]:.3f} CdA={rec["CdA"]:.3f} lift={rec["ClA"]:+.3f} side={rec["CyA"]:+.3f} {rec["seconds"]:.1f}s', flush=True)
    print('queue finished', n, 'new runs', flush=True)


if __name__ == '__main__':
    main()

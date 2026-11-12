"""Run a list of retargeted poses (from a recorded clip) through the solver. Saves forces for all, 3D fields for a few."""
import sys, json, time, os
import numpy as np
import taichi as ti
ti.init(arch=ti.cuda, default_fp=ti.f32, device_memory_GB=6, offline_cache=True)
from lbm import Tunnel
import bodies as B

NX, NY, NZ, H = 224, 128, 128, 64
U, NU = 0.08, 4e-4
WARM_FT, AVG_FT = 1.25, 1.75
src, out = sys.argv[1], sys.argv[2]
field_idx = set(int(x) for x in sys.argv[3].split(',')) if len(sys.argv) > 3 and sys.argv[3] else set()
os.makedirs(out, exist_ok=True)
items = json.load(open(src))
logp = f'{out}/forces.jsonl'
done = set(json.loads(l)['frame'] for l in open(logp)) if os.path.exists(logp) else set()
T = Tunnel(NX, NY, NZ, U=U, nu=NU, nparts=len(B.PARTS))
FT = int(NX / U)
f = open(logp, 'a')
order = sorted(range(len(items)), key=lambda k: (k not in field_idx, k))      # key frames first
for k in order:
    it = items[k]
    if it['frame'] in done:
        continue
    pose = B.pose_from_list(it['pose'])
    mask, info = B.voxelize(pose, (NX, NY, NZ), H)
    T.set_solid(mask)
    ti.sync(); t0 = time.time()
    want = k in field_idx
    F, series = T.run(int(WARM_FT * FT), int(AVG_FT * FT), chunk=200, avg_field_every=2 if want else 0)
    ti.sync(); dt = time.time() - t0
    q = 0.5 * U * U; dx = info['dx_m']; kk = dx * dx / q; corr = (1 - info['blockage']) ** 2
    h = len(series) // 2
    rec = dict(k=k, frame=it['frame'], t=it['t'], pose=it['pose'], feat=it['feat'], area_m2=info['area_m2'], blockage=info['blockage'], corr=corr,
               F_parts=(F * kk).tolist(), CdA=float(F[:, 0].sum() * kk * corr), ClA=float(F[:, 2].sum() * kk * corr),
               CdA_halves=[float(series[:h].mean() * kk * corr), float(series[h:].mean() * kk * corr)], seconds=dt)
    f.write(json.dumps(rec) + '\n'); f.flush()
    if want:
        T.macro()
        np.savez_compressed(f'{out}/field_{k:03d}.npz', mask=mask, vel=T.vel.to_numpy().astype(np.float16),
                            vavg=(T.vavg.to_numpy() / max(T.nfield, 1)).astype(np.float16), U=U, dx=dx, frame=it['frame'])
    print(k, it['frame'], f'CdA={rec["CdA"]:.3f} A={info["area_m2"]:.3f} {dt:.1f}s', flush=True)

"""Generate the dataset: random poses -> solver -> drag per body part. Resumable (appends to a JSONL file).

Every 6th sample is an out-of-distribution pose (prone, side-on, back to the wind, inverted) so the doubt
signal can be tested on poses the model never trains on.
"""
import sys, json, time, os
import numpy as np
import taichi as ti
ti.init(arch=ti.cuda, default_fp=ti.f32, device_memory_GB=6, offline_cache=True)
from lbm import Tunnel
import bodies as B

NX, NY, NZ, H = 224, 128, 128, 64
U, NU = 0.08, 4e-4
WARM_FT, AVG_FT = 1.25, 1.75
out = sys.argv[1]
n_total = int(sys.argv[2])
seed0 = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
done = 0
if os.path.exists(out):
    done = sum(1 for _ in open(out))
T = Tunnel(NX, NY, NZ, U=U, nu=NU, nparts=len(B.PARTS))
FT = int(NX / U)
OOD = ['prone', 'side', 'back', 'inverted']
f = open(out, 'a')
for i in range(done, n_total):
    rng = np.random.default_rng(seed0 + i)
    if i % 6 == 5:
        pose, fam = B.sample_ood(rng, OOD[(i // 6) % 4])
        split = 'ood'
    else:
        pose, fam = B.sample_pose(rng)
        split = 'in'
    mask, info = B.voxelize(pose, (NX, NY, NZ), H)
    if info['x_range'] is None or info['x_range'][0] < 8:
        continue
    T.set_solid(mask)
    ti.sync(); t0 = time.time()
    F, series = T.run(int(WARM_FT * FT), int(AVG_FT * FT), chunk=200)
    ti.sync(); dt = time.time() - t0
    q = 0.5 * U * U
    dx = info['dx_m']
    k = dx * dx / q
    corr = (1 - info['blockage']) ** 2
    h = len(series) // 2
    rec = dict(i=i, seed=seed0 + i, split=split, family=str(fam), pose=B.pose_to_list(pose), feat=[float(x) for x in B.features(pose)],
               area_m2=info['area_m2'], blockage=info['blockage'], corr=corr,
               F_parts=(F * k).tolist(),                       # per part: [drag, side, lift] areas in m^2, uncorrected
               CdA=float(F[:, 0].sum() * k * corr), CyA=float(F[:, 1].sum() * k * corr), ClA=float(F[:, 2].sum() * k * corr),
               CdA_halves=[float(series[:h].mean() * k * corr), float(series[h:].mean() * k * corr)],
               seconds=dt, grid=[NX, NY, NZ, H], steps=int(WARM_FT * FT) + int(AVG_FT * FT))
    f.write(json.dumps(rec) + '\n'); f.flush()
    if i % 10 == 0:
        print(f'{i} {split:3s} {fam:9s} A={info["area_m2"]:.3f} CdA={rec["CdA"]:.3f} Cd={rec["CdA"]/info["area_m2"]:.3f} {dt:.1f}s', flush=True)

"""Grid-convergence check of the solver: the same five poses at 64, 96 and 128 cells per body height (Reynolds number
held fixed), plus a four-times-longer average at 64 for the averaging noise. One resolution per process.
Usage: python converge.py <H> <out.jsonl> [avg_flow_throughs]"""
import sys, json, time
import numpy as np
import taichi as ti
from lbm import Tunnel, ti_init
ti_init()
import bodies as B

H = int(sys.argv[1]); out = sys.argv[2]; AVG = float(sys.argv[3]) if len(sys.argv) > 3 else 1.75
NX, NY, NZ = int(3.5 * H), 2 * H, 2 * H
U = 0.08; NU = 4e-4 * H / 64
T = Tunnel(NX, NY, NZ, U=U, nu=NU, nparts=len(B.PARTS))
FT = int(NX / U)
f = open(out, 'a')
for name in ('standing', 't_pose', 'ski_tuck', 'bow_45', 'side_on'):
    pose = B.make_pose(**B.NAMED[name])
    mask, info = B.voxelize(pose, (NX, NY, NZ), H)
    T.set_solid(mask)
    ti.sync(); t0 = time.time()
    F, series = T.run2(int(1.25 * FT), int(AVG * FT), chunk=100)
    ti.sync(); dt = time.time() - t0
    k = info['dx_m'] ** 2 / (0.5 * U * U); corr = (1 - info['blockage']) ** 2
    tot = F.sum(0) * k * corr
    h = len(series) // 2
    rec = dict(pose=name, H=H, grid=[NX, NY, NZ], cells=NX * NY * NZ, nu=NU, avg_ft=AVG, drag=float(tot[0]), side=float(tot[1]), lift=float(tot[2]), area=info['area_m2'],
               drag_halves=[float(series[:h, 0].mean() * k * corr), float(series[h:, 0].mean() * k * corr)], seconds=round(dt, 1), finite=bool(np.isfinite(F).all()))
    f.write(json.dumps(rec) + '\n'); f.flush()
    print(json.dumps(rec), flush=True)

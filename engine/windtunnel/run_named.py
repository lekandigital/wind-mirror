"""Run the named poses through the tunnel; print drag areas; save masks and flow slices for pictures."""
import sys, json, time, os
import numpy as np
import taichi as ti
ti.init(arch=ti.cuda, default_fp=ti.f32, device_memory_GB=6, offline_cache=True)
from lbm import Tunnel
import bodies as B

NX, NY, NZ, H = 224, 128, 128, 64
U, NU = 0.08, 4e-4
out = sys.argv[1] if len(sys.argv) > 1 else '../out/named'
os.makedirs(out, exist_ok=True)
T = Tunnel(NX, NY, NZ, U=U, nu=NU, nparts=len(B.PARTS))
FT = int(NX / U)
res = {}
names = sys.argv[2].split(',') if len(sys.argv) > 2 else list(B.NAMED)
for name in names:
    pose = B.make_pose(**B.NAMED[name])
    mask, info = B.voxelize(pose, (NX, NY, NZ), H)
    T.set_solid(mask)
    ti.sync(); t0 = time.time()
    F, series = T.run(int(1.5 * FT), int(2.0 * FT), chunk=200, avg_field_every=2)
    ti.sync(); dt = time.time() - t0
    q = 0.5 * U * U
    dx = info['dx_m']
    cda = F[:, 0] / q * dx * dx                       # m^2 per part
    corr = (1 - info['blockage']) ** 2
    T.macro()
    vel = T.vel.to_numpy()
    vavg = T.vavg.to_numpy() / max(T.nfield, 1)
    np.savez_compressed(f'{out}/{name}.npz', mask=mask, vel_mid=vel[:, NY // 2], vavg_mid=vavg[:, NY // 2],
                        vel_y=vel[:, ::2, ::2].astype(np.float16), series=series)
    r = dict(name=name, seconds=round(dt, 1), area_m2=round(info['area_m2'], 4), blockage=round(info['blockage'], 4),
             CdA_raw=round(float(cda.sum()), 4), CdA=round(float(cda.sum() * corr), 4), Cd=round(float(cda.sum() * corr / info['area_m2']), 3),
             lift_area=round(float(F[:, 2].sum() / q * dx * dx * corr), 4),
             halves=[round(float(series[:len(series)//2].mean() / q * dx * dx * corr), 4), round(float(series[len(series)//2:].mean() / q * dx * dx * corr), 4)],
             parts={p: round(float(c * corr), 4) for p, c in zip(B.PARTS, cda)})
    res[name] = r
    print(json.dumps(r), flush=True)
json.dump(res, open(f'{out}/named.json', 'w'), indent=1)

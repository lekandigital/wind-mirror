"""Check the solver against textbook drag coefficients before trusting it on a body."""
import sys, time, json
import numpy as np
import taichi as ti
ti.init(arch=ti.cuda, default_fp=ti.f32, device_memory_GB=6, offline_cache=True)
from lbm import Tunnel

def run_case(name, mask, area_cells, U=0.08, nu=4e-4, n_warm=None, n_avg=None, cs=0.14):
    nx, ny, nz = mask.shape
    t = Tunnel(nx, ny, nz, U=U, nu=nu, cs_smag=cs, nparts=4)
    t.set_solid(mask)
    ft = int(nx / U)
    n_warm = n_warm or int(1.5 * ft)
    n_avg = n_avg or int(2.0 * ft)
    ti.sync(); t0 = time.time()
    F, series = t.run(n_warm, n_avg, chunk=200)
    ti.sync(); dt = time.time() - t0
    mlups = nx * ny * nz * (n_warm + n_avg) / dt / 1e6
    q = 0.5 * U * U
    cd = F[:, 0].sum() / (q * area_cells)
    cl = F[:, 2].sum() / (q * area_cells)
    cdser = series / (q * area_cells)
    print(json.dumps(dict(case=name, grid=[nx, ny, nz], steps=n_warm + n_avg, seconds=round(dt, 1), mlups=round(mlups),
                          Cd=round(float(cd), 4), Cz=round(float(cl), 4), Cd_std=round(float(cdser.std()), 4),
                          Cd_first_half=round(float(cdser[:len(cdser)//2].mean()), 4), Cd_second_half=round(float(cdser[len(cdser)//2:].mean()), 4),
                          blockage=round(float(area_cells / (ny * nz)), 4), tau0=round(0.5 + 3 * nu, 5))), flush=True)
    return cd

def grid(nx, ny, nz):
    return np.meshgrid(np.arange(nx) + 0.5, np.arange(ny) + 0.5, np.arange(nz) + 0.5, indexing='ij')

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'sphere'
    nx, ny, nz = 224, 128, 128
    X, Y, Z = grid(nx, ny, nz)
    if which == 'sphere':
        for D in (24, 40):
            r = D / 2
            m = ((X - 80) ** 2 + (Y - ny / 2) ** 2 + (Z - nz / 2) ** 2 < r * r).astype(np.uint8)
            area = m.max(axis=0).sum()
            for nu in (4e-4, 1e-3):
                run_case(f'sphere D={D} Re={0.08*D/nu:.0f} (textbook Cd 0.40-0.47)', m, area, nu=nu)
    elif which == 'cylinder':
        D = 24
        m = ((X - 80) ** 2 + (Z - nz / 2) ** 2 < (D / 2) ** 2).astype(np.uint8)   # spans periodic y
        run_case(f'cylinder D={D} Re={0.08*D/4e-4:.0f} (textbook Cd 1.0-1.2)', m, D * ny)
    elif which == 'cube':
        L = 32
        m = ((abs(X - 80) < L / 2) & (abs(Y - ny / 2) < L / 2) & (abs(Z - nz / 2) < L / 2)).astype(np.uint8)
        run_case(f'cube L={L} (textbook Cd 1.05)', m, L * L)
    elif which == 'plate':
        L = 40
        m = ((abs(X - 80) < 2) & (abs(Y - ny / 2) < L / 2) & (abs(Z - nz / 2) < L / 2)).astype(np.uint8)
        run_case(f'square plate L={L} (textbook Cd 1.17)', m, L * L)

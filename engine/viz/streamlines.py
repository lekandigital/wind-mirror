"""Trace streamlines through a solver velocity field and write a scene description for the Blender renderer."""
import sys, json
import numpy as np
from scipy.ndimage import map_coordinates
sys.path.insert(0, '../windtunnel')
import bodies as B


def trace(vel, mask, seeds, U, h=0.6, nsteps=520, scale=(1, 1, 1)):
    """vel: (nx, ny', nz', 3) possibly coarser than the mask by integer factors `scale`. seeds: (N, 3) in cell coordinates."""
    sc = np.array(scale, float)
    comps = [np.ascontiguousarray(vel[..., i].astype(np.float32)) for i in range(3)]
    solid = (mask > 0).astype(np.float32)
    p = seeds.astype(float).copy()
    alive = np.ones(len(p), bool)
    pts = [p.copy()]
    spd = []
    lim = np.array(mask.shape) - 1.001
    for _ in range(nsteps):
        q = (p / sc).T - 0.0
        v = np.stack([map_coordinates(c, q, order=1, mode='nearest') for c in comps], 1)
        s = np.linalg.norm(v, axis=1)
        ins = map_coordinates(solid, p.T, order=0, mode='nearest') > 0.5
        alive &= (s > 0.03 * U) & ~ins
        spd.append(np.where(alive, s / U, np.nan))
        step = np.where(alive[:, None], v / np.maximum(s, 1e-9)[:, None] * h, 0.0)
        p = p + step
        out = (p < 0.5).any(1) | (p > lim).any(1)
        alive &= ~out
        p = np.clip(p, 0.5, lim)
        pts.append(np.where(alive[:, None], p, np.nan))
    return np.stack(pts, 1), np.stack(spd + [spd[-1]], 1)          # (N, T, 3), (N, T)


def build(npz_path, pose, out_json, field='vavg', nside=(9, 15), yz_extent=(0.48, 1.9), H=64, seed=0, extra=None):
    d = np.load(npz_path)
    mask = d['mask']
    nx, ny, nz = mask.shape
    if field in d:
        vel = d[field].astype(np.float32); scale = (1, 1, 1)
    else:
        vel = d['vel_y'].astype(np.float32); scale = (1, 2, 2)
    s = H / B.HEIGHT
    x0 = 1.3 * H
    J = B.joints(pose); caps = B.capsules(J, pose)
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in caps)
    rng = np.random.default_rng(seed)
    ys = np.linspace(-yz_extent[0], yz_extent[0], nside[0]); zs = np.linspace(0.06, yz_extent[1], nside[1])
    Y, Z = np.meshgrid(ys, zs, indexing='ij')
    Y = Y + rng.normal(0, 0.012, Y.shape); Z = Z + rng.normal(0, 0.012, Z.shape)
    seeds = np.stack([np.full(Y.size, 6.0), Y.ravel() * s + ny / 2, np.clip(Z.ravel() * s, 1.0, nz - 2)], 1)
    P, S = trace(vel, mask, seeds, float(d['U']) if 'U' in d else 0.08, scale=scale)
    lines = []
    for i in range(len(P)):
        ok = ~np.isnan(P[i, :, 0])
        n = int(ok.sum())
        if n < 12:
            continue
        pts = P[i, :n]
        m = np.stack([(pts[:, 0] - x0) / s, (pts[:, 1] - ny / 2) / s, pts[:, 2] / s], 1)
        lines.append(dict(p=np.round(m[::2], 4).tolist(), s=np.round(np.nan_to_num(S[i, :n][::2], nan=0.0), 3).tolist()))
    scene = dict(capsules=[dict(a=(a + [0, 0, -zmin]).tolist(), b=(b + [0, 0, -zmin]).tolist(), r=float(r), part=int(pt)) for a, b, r, pt in caps],
                 lines=lines, parts=B.PARTS, tunnel=dict(x=[-x0 / s, (nx - x0) / s], y=[-ny / 2 / s, ny / 2 / s], z=[0, nz / s]))
    if extra:
        scene.update(extra)
    json.dump(scene, open(out_json, 'w'))
    return scene


if __name__ == '__main__':
    name = sys.argv[1]
    pose = B.make_pose(**B.NAMED[name])
    res = json.load(open('../out/named/named.json'))[name]
    sc = build(f'../out/named/{name}.npz', pose, f'../out/named/{name}_scene.json', extra=dict(part_drag=res['parts'], CdA=res['CdA']))
    print(name, len(sc['lines']), 'lines')

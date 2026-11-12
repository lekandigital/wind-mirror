"""Wind's-eye-view features: what the wind 'sees' of a body, computed from geometry alone (no flow solve).

The body's capsules are ray-cast along the wind direction (+x) on a regular (y, z) grid. For every ray we keep the first
surface it meets (the windward face) and the last surface it leaves (the leeward face): depth, surface normal and body part.
From those two images come the model's inputs:

  global   frontal area; a Newtonian-impact estimate of the windward pressure force (sum of n_x * n over the windward face);
           leeward-face normal sums; mean thickness and length along the wind; silhouette width, height, perimeter and
           centroid height; how the windward depth tilts across the silhouette; side-view and top-view shadow areas
  per part windward-exposed area and Newtonian force estimate of each of the 10 body parts, and its leeward-exposed area

Nothing here knows about joints or people: the same features exist for any shape made of capsules. The JavaScript port
(web/src/geom.js) must give the same numbers; tests/test_geom_parity checks that.
"""
import numpy as np
import bodies as B

PX = 0.02                      # ray spacing, metres
YMIN, YMAX = -1.5, 1.5         # lateral window around the pelvis
ZMAX = 2.7                     # the floor is z = 0
NYP, NZP = int(round((YMAX - YMIN) / PX)), int(round(ZMAX / PX))
NPART = len(B.PARTS)
GLOBAL_NAMES = ['A', 'Nx', 'Ny', 'Nz', 'By', 'Bz', 'thick', 'len_x', 'width', 'height', 'perim', 'zc', 'depth_sd', 'tilt_y', 'tilt_z', 'A_side', 'A_top']
PART_NAMES = [f'{p}:{k}' for p in B.PARTS for k in ('A', 'Nx', 'Ny', 'Nz', 'Ab')]
NAMES = GLOBAL_NAMES + PART_NAMES
NG = len(GLOBAL_NAMES)
# mirroring a body left-right (y -> -y): which features change sign, and which parts swap
PART_SWAP = [0, 1, 4, 5, 2, 3, 8, 9, 6, 7]
_G_SIGN = np.array([1, 1, -1, 1, -1, 1, 1, 1, 1, 1, 1, 1, 1, -1, 1, 1, 1], float)
_P_SIGN = np.array([1, 1, -1, 1, 1], float)


def body_capsules(pose, body=None):
    """Capsules (a, b, r, part) in metres with the floor at z = 0 and the pelvis at y = 0."""
    J = B.joints(pose, body)
    caps = B.capsules(J, pose, body)
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in caps)
    off = np.array([0.0, 0.0, -zmin])
    return [(np.asarray(a, float) + off, np.asarray(b, float) + off, float(r), int(p)) for a, b, r, p in caps]


def _cast(caps, axis=0, want_normals=True):
    """Ray-cast capsules along `axis` on the grid of the two remaining axes. Returns front depth, back depth, front/back
    normals and parts (arrays over the image; depth is +inf / -inf where the ray misses)."""
    k = [i for i in range(3) if i != axis]
    if axis == 0:
        u0, nu, v0, nv = YMIN, NYP, 0.0, NZP
    elif axis == 1:
        u0, nu, v0, nv = -2.0, int(round(4.0 / PX)), 0.0, NZP
    else:
        u0, nu, v0, nv = -2.0, int(round(4.0 / PX)), YMIN, NYP
    front = np.full((nu, nv), np.inf); back = np.full((nu, nv), -np.inf)
    pf = np.full((nu, nv), -1, np.int16); pb = np.full((nu, nv), -1, np.int16)
    nf = np.zeros((nu, nv, 3)); nb = np.zeros((nu, nv, 3))
    for a, b, r, part in caps:
        lo_u = max(int(np.floor((min(a[k[0]], b[k[0]]) - r - u0) / PX)), 0); hi_u = min(int(np.ceil((max(a[k[0]], b[k[0]]) + r - u0) / PX)) + 1, nu)
        lo_v = max(int(np.floor((min(a[k[1]], b[k[1]]) - r - v0) / PX)), 0); hi_v = min(int(np.ceil((max(a[k[1]], b[k[1]]) + r - v0) / PX)) + 1, nv)
        if hi_u <= lo_u or hi_v <= lo_v:
            continue
        uu = u0 + (np.arange(lo_u, hi_u) + 0.5) * PX
        vv = v0 + (np.arange(lo_v, hi_v) + 0.5) * PX
        Uu, Vv = np.meshgrid(uu, vv, indexing='ij')
        O = np.zeros(Uu.shape + (3,)); O[..., k[0]] = Uu; O[..., k[1]] = Vv          # ray origins, at depth 0 along `axis`
        ba = b - a; baba = float(ba @ ba); bard = float(ba[axis])
        t_in = np.full(Uu.shape, np.inf); t_out = np.full(Uu.shape, -np.inf)
        # the two end spheres
        for c in (a, b):
            oc = O - c
            Bq = oc[..., axis]; Cq = (oc * oc).sum(-1) - r * r
            h = Bq * Bq - Cq
            ok = h > 0
            sq = np.sqrt(np.where(ok, h, 0.0))
            t_in = np.where(ok, np.minimum(t_in, -Bq - sq), t_in)
            t_out = np.where(ok, np.maximum(t_out, -Bq + sq), t_out)
        # the cylinder between them, clipped to the segment
        if baba > 1e-12:
            oa = O - a
            baoa = oa @ ba; rdoa = oa[..., axis]; oaoa = (oa * oa).sum(-1)
            Aq = baba - bard * bard
            Cq = baba * oaoa - baoa * baoa - r * r * baba
            if Aq > 1e-9 * baba:
                Bq = baba * rdoa - baoa * bard
                h = Bq * Bq - Aq * Cq
                ok = h > 0
                sq = np.sqrt(np.where(ok, h, 0.0))
                c1 = (-Bq - sq) / Aq; c2 = (-Bq + sq) / Aq
            else:                                             # axis parallel to the ray: inside the tube or not
                ok = Cq < 0
                c1 = np.full(Uu.shape, -np.inf); c2 = np.full(Uu.shape, np.inf)
            if abs(bard) > 1e-12:
                s1 = (0.0 - baoa) / bard; s2 = (baba - baoa) / bard
                lo, hi = np.minimum(s1, s2), np.maximum(s1, s2)
            else:
                inside = (baoa >= 0) & (baoa <= baba)
                lo = np.where(inside, -np.inf, np.inf); hi = np.where(inside, np.inf, -np.inf)
            e1 = np.maximum(c1, lo); e2 = np.minimum(c2, hi)
            ok = ok & (e2 > e1)
            t_in = np.where(ok, np.minimum(t_in, e1), t_in)
            t_out = np.where(ok, np.maximum(t_out, e2), t_out)
        hit = t_out > t_in
        sub = (slice(lo_u, hi_u), slice(lo_v, hi_v))
        for t, depth, parts, normals, closer in ((t_in, front, pf, nf, np.less), (t_out, back, pb, nb, np.greater)):
            upd = hit & closer(t, depth[sub])
            if not upd.any():
                continue
            depth[sub] = np.where(upd, t, depth[sub])
            parts[sub] = np.where(upd, part, parts[sub])
            if want_normals:
                P = O.copy(); P[..., axis] = np.where(upd, t, 0.0)
                s = np.clip(((P - a) @ ba) / baba, 0, 1) if baba > 1e-12 else np.zeros(Uu.shape)
                n = (P - (a + s[..., None] * ba)) / r
                normals[sub] = np.where(upd[..., None], n, normals[sub])
    return front, back, nf, nb, pf, pb


def wind_view(pose, body=None):
    caps = body_capsules(pose, body)
    return _cast(caps, 0), caps


def features_from_view(view, caps):
    front, back, nf, nb, pf, pb = view
    hit = np.isfinite(front)
    dA = PX * PX
    A = hit.sum() * dA
    g = np.zeros(NG)
    if A <= 0:
        return np.concatenate([g, np.zeros(NPART * 5)])
    w = nf[..., 0][hit]                                          # n_x on the windward face (negative: facing upwind)
    N = (w[:, None] * nf[hit]).sum(0) * dA                       # Newtonian estimate: sum of n_x * n
    Bk = nb[hit].sum(0) * dA                                     # leeward-face normal sum
    thick = (back[hit] - front[hit]).sum() * dA / A
    len_x = back[hit].max() - front[hit].min()
    ys = np.where(hit.any(1))[0]; zs = np.where(hit.any(0))[0]
    width = (ys.max() - ys.min() + 1) * PX; height = (zs.max() - zs.min() + 1) * PX
    hp = np.pad(hit, 1)
    perim = ((hp[1:, :] != hp[:-1, :]).sum() + (hp[:, 1:] != hp[:, :-1]).sum()) * PX
    iy, iz = np.nonzero(hit)
    yv = YMIN + (iy + 0.5) * PX; zv = (iz + 0.5) * PX
    zc = zv.mean(); yc = yv.mean()
    d = front[hit]; dm = d.mean()
    depth_sd = d.std()
    tilt_y = ((d - dm) * (yv - yc)).mean(); tilt_z = ((d - dm) * (zv - zc)).mean()
    A_side = np.isfinite(_cast(caps, 1, want_normals=False)[0]).sum() * dA
    A_top = np.isfinite(_cast(caps, 2, want_normals=False)[0]).sum() * dA
    g[:] = [A, N[0], N[1], N[2], Bk[1], Bk[2], thick, len_x, width, height, perim, zc, depth_sd, tilt_y, tilt_z, A_side, A_top]
    P = np.zeros((NPART, 5))
    pfh = pf[hit]; nfh = nf[hit]; pbh = pb[hit]
    for p in range(NPART):
        m = pfh == p
        if m.any():
            P[p, 0] = m.sum() * dA
            P[p, 1:4] = (w[m][:, None] * nfh[m]).sum(0) * dA
        P[p, 4] = (pbh == p).sum() * dA
    return np.concatenate([g, P.ravel()])


def features(pose, body=None):
    """The model's input vector (see NAMES) for a pose and an optional body shape."""
    view, caps = wind_view(pose, body)
    return features_from_view(view, caps)


def mirror(F):
    """Features of the left-right mirrored body, from the features of the body. Works on (..., len(NAMES)) arrays."""
    F = np.asarray(F, float)
    out = F.copy()
    out[..., :NG] = F[..., :NG] * _G_SIGN
    P = F[..., NG:].reshape(F.shape[:-1] + (NPART, 5))[..., PART_SWAP, :] * _P_SIGN
    out[..., NG:] = P.reshape(F.shape[:-1] + (NPART * 5,))
    return out


def mirror_pose(pose):
    """The left-right mirrored pose (y -> -y, left and right limbs exchanged)."""
    m = lambda v: np.asarray(v, float) * np.array([1.0, -1.0, 1.0])
    out = dict(t=m(pose['t']), h=m(pose['h']), l=-m(pose['l']))
    for a, b in (('uaL', 'uaR'), ('faL', 'faR'), ('thL', 'thR'), ('shL', 'shR')):
        out[a], out[b] = m(pose[b]), m(pose[a])
    if 'lh' in pose:
        out['lh'] = -m(pose['lh'])
    return out


if __name__ == '__main__':
    import time
    rng = np.random.default_rng(0)
    pose = B.make_pose()
    t0 = time.perf_counter()
    for _ in range(20):
        f = features(pose)
    print('ms per pose', (time.perf_counter() - t0) / 20 * 1000)
    for n, v in zip(GLOBAL_NAMES, f[:NG]):
        print(f'{n:9s} {v:8.4f}')
    _, info = B.voxelize(pose, (224, 128, 128), 64)
    print('voxel frontal area', info['area_m2'], 'side', B.proj_area(pose, 1), 'top', B.proj_area(pose, 2))
    # mirror consistency
    worst = 0
    for i in range(30):
        p, _ = B.sample_pose(rng)
        if i % 3 == 0:
            p = B.twist(p, 30)
        sh = B.sample_shape(rng) if i % 2 else None
        worst = max(worst, np.abs(mirror(features(p, sh)) - features(mirror_pose(p), sh)).max())
    print('mirror consistency, worst abs difference over 30 poses:', worst)

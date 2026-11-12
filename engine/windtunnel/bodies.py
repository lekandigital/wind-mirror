"""Capsule mannequin: pose (bone directions) + shape (proportions) -> joints -> capsules -> voxel mask with body-part labels.

World frame: wind blows toward +x, y is lateral, z is up. A person "facing the wind" faces -x, with their left at -y.

A pose is a dict of unit vectors: the 11 in BONES[:11], plus an optional 'lh' (hip line, right hip -> left hip). Without
'lh' the hips follow the shoulder line 'l', which is how every run before 2026-11-12 07:50 ET was made.
A shape is an optional dict of multipliers (see SHAPE_KEYS); None or {} is the reference body used for all earlier runs.
"""
import numpy as np

LEN = dict(torso=0.50, neck=0.10, head=0.12, sh=0.19, hip=0.085, uarm=0.29, farm=0.26, hand=0.07,
           thigh=0.44, shin=0.42, foot=0.20)
RAD = dict(head=0.105, neck=0.055, torso_c=0.125, torso_s=0.105, girdle=0.06, pelvis=0.10, uarm=0.047,
           farm=0.040, hand=0.040, thigh=0.078, shin=0.052, foot=0.042)
HEIGHT = 1.75
SHAPE_KEYS = ['g_torso', 'g_limb', 'leg', 'arm', 'sh', 'hip', 'torso']
SHAPE_RANGE = dict(g_torso=(0.85, 1.30), g_limb=(0.85, 1.25), leg=(0.92, 1.08), arm=(0.92, 1.08), sh=(0.88, 1.12), hip=(0.90, 1.15), torso=(0.93, 1.07))
_TORSO_R = ('torso_c', 'torso_s', 'girdle', 'pelvis')
_LIMB_R = ('uarm', 'farm', 'hand', 'thigh', 'shin', 'foot')


def dims(shape=None):
    """Bone lengths and capsule radii (metres) for a shape. g_torso / g_limb scale girth, leg / arm / torso scale lengths,
    sh / hip scale shoulder and hip half-widths."""
    if not shape:
        return LEN, RAD
    g = lambda k: float(shape.get(k, 1.0))
    L, R = dict(LEN), dict(RAD)
    for k in ('thigh', 'shin'):
        L[k] *= g('leg')
    for k in ('uarm', 'farm'):
        L[k] *= g('arm')
    L['sh'] *= g('sh'); L['hip'] *= g('hip'); L['torso'] *= g('torso')
    for k in _TORSO_R:
        R[k] *= g('g_torso')
    for k in _LIMB_R:
        R[k] *= g('g_limb')
    return L, R


def shape_vec(shape=None):
    return [float((shape or {}).get(k, 1.0)) for k in SHAPE_KEYS]


def sample_shape(rng):
    return {k: float(rng.uniform(*SHAPE_RANGE[k])) for k in SHAPE_KEYS}


PARTS = ['head', 'torso', 'L_upper_arm', 'L_forearm', 'R_upper_arm', 'R_forearm', 'L_thigh', 'L_shin', 'R_thigh', 'R_shin']
BONES = ['t', 'l', 'h', 'uaL', 'faL', 'uaR', 'faR', 'thL', 'shL', 'thR', 'shR', 'lh']
UP = np.array([0.0, 0.0, 1.0])


def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def hip_line(pose):
    t = unit(pose['t'])
    lh = pose.get('lh')
    lh = unit(pose['l']) if lh is None else unit(lh)
    return unit(lh - np.dot(lh, t) * t)


def joints(pose, shape=None):
    """pose: dict of unit vectors. Returns joint positions in metres, pelvis at the origin."""
    LEN, RAD = dims(shape)
    t, l, h = unit(pose['t']), unit(pose['l']), unit(pose['h'])
    l = unit(l - np.dot(l, t) * t)
    lh = hip_line(pose)
    J = {}
    J['pelvis'] = np.zeros(3)
    J['neck'] = LEN['torso'] * t
    J['head'] = J['neck'] + (LEN['neck'] + LEN['head']) * h
    for s, sg in (('L', 1.0), ('R', -1.0)):
        J['sh' + s] = J['neck'] + sg * LEN['sh'] * l
        J['el' + s] = J['sh' + s] + LEN['uarm'] * unit(pose['ua' + s])
        J['wr' + s] = J['el' + s] + LEN['farm'] * unit(pose['fa' + s])
        J['hand' + s] = J['wr' + s] + LEN['hand'] * unit(pose['fa' + s])
        J['hip' + s] = sg * LEN['hip'] * lh
        J['kn' + s] = J['hip' + s] + LEN['thigh'] * unit(pose['th' + s])
        J['an' + s] = J['kn' + s] + LEN['shin'] * unit(pose['sh' + s])
        fwd = np.cross(lh, t)
        sh = unit(pose['sh' + s])
        fd = fwd - np.dot(fwd, sh) * sh
        fd = unit(fd) if np.linalg.norm(fd) > 1e-3 else unit(np.cross(sh, lh))
        J['toe' + s] = J['an' + s] + LEN['foot'] * fd
    return J


def capsules(J, pose, shape=None):
    LEN, RAD = dims(shape)
    t, l = unit(pose['t']), unit(pose['l'])
    l = unit(l - np.dot(l, t) * t)
    lh = hip_line(pose)
    wt, wb = 0.11 * float((shape or {}).get('sh', 1.0)) * float((shape or {}).get('g_torso', 1.0)) ** 0.5, 0.075 * float((shape or {}).get('hip', 1.0))
    C = []
    C.append((J['head'], J['head'], RAD['head'], 0))
    C.append((J['neck'], J['head'], RAD['neck'], 0))
    C.append((J['pelvis'] + 0.07 * t, J['neck'] - 0.09 * t, RAD['torso_c'], 1))
    for sg in (1.0, -1.0):
        C.append((J['neck'] - 0.07 * t + sg * wt * l, J['pelvis'] + 0.03 * t + sg * wb * lh, RAD['torso_s'], 1))
    C.append((J['shL'], J['shR'], RAD['girdle'], 1))
    C.append((J['hipL'], J['hipR'], RAD['pelvis'], 1))
    for s, pu, pf, pt, ps in (('L', 2, 3, 6, 7), ('R', 4, 5, 8, 9)):
        C.append((J['sh' + s], J['el' + s], RAD['uarm'], pu))
        C.append((J['el' + s], J['wr' + s], RAD['farm'], pf))
        C.append((J['wr' + s], J['hand' + s], RAD['hand'], pf))
        C.append((J['hip' + s], J['kn' + s], RAD['thigh'], pt))
        C.append((J['kn' + s], J['an' + s], RAD['shin'], ps))
        C.append((J['an' + s], J['toe' + s], RAD['foot'], ps))
    return C


def voxelize(pose, shape, H_cells=64, x0=None, body=None):
    """shape: grid (nx, ny, nz); body: optional body-shape dict. Returns (mask uint8 with part id + 1, info dict).
    The body's lowest point rests on the floor (z = 0). H_cells / HEIGHT is the number of cells per metre."""
    nx, ny, nz = shape
    s = H_cells / HEIGHT                       # cells per metre
    J = joints(pose, body)
    caps = capsules(J, pose, body)
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in caps)
    x0 = x0 if x0 is not None else 1.3 * H_cells
    off = np.array([x0, ny / 2.0, -zmin * s])
    mask = np.zeros(shape, np.uint8)
    for a, b, r, part in caps:
        A, B, rc = a * s + off, b * s + off, r * s
        lo = np.floor(np.minimum(A, B) - rc - 1).astype(int)
        hi = np.ceil(np.maximum(A, B) + rc + 1).astype(int)
        lo = np.maximum(lo, 0)
        hi = np.minimum(hi, [nx, ny, nz])
        if np.any(hi <= lo):
            continue
        gx, gy, gz = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5, np.arange(lo[2], hi[2]) + 0.5, indexing='ij')
        P = np.stack([gx, gy, gz], -1)
        d = B - A
        dd = float(np.dot(d, d))
        tt = np.clip(((P - A) @ d) / dd, 0, 1) if dd > 1e-9 else np.zeros(P.shape[:3])
        dist = np.linalg.norm(P - (A + tt[..., None] * d), axis=-1)
        sub = mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
        inside = (dist < rc) & (sub == 0)
        sub[inside] = part + 1
    area_cells = int((mask > 0).max(axis=0).sum())
    xs = np.where(mask.any(axis=(1, 2)))[0]
    info = dict(area_m2=area_cells / s ** 2, area_cells=area_cells, blockage=area_cells / (ny * nz), dx_m=1.0 / s,
                x_range=[int(xs.min()), int(xs.max())] if len(xs) else None, pelvis_height_m=float(-zmin))
    return mask, info


def features(pose, body=None):
    """36 joint coordinates relative to the pelvis + pelvis height above the floor (metres)."""
    J = joints(pose, body)
    caps = capsules(J, pose, body)
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in caps)
    keys = ['neck', 'head', 'shL', 'shR', 'elL', 'elR', 'wrL', 'wrR', 'knL', 'knR', 'anL', 'anR']
    return np.concatenate([np.concatenate([J[k] for k in keys]), [-zmin]])


def rotz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def make_pose(yaw=0.0, lean=0.0, side_lean=0.0, head_ext=0.0, arms=((10, 0, 5, 0), (10, 0, 5, 0)), legs=((0, 4, 0), (0, 4, 0)), invert=False):
    """Angles in degrees. arms: per side (abduction, flexion, elbow, elbow swivel); legs: per side (hip angle from
    straight-down in the sagittal plane, abduction, knee flexion). Order is (left, right)."""
    d = np.deg2rad
    fwd = rotz(d(yaw)) @ np.array([-1.0, 0, 0])
    left = rotz(d(yaw)) @ np.array([0, -1.0, 0])
    t = unit(np.cos(d(lean)) * UP + np.sin(d(lean)) * fwd + np.sin(d(side_lean)) * left)
    l = unit(left - np.dot(left, t) * t)
    fwd_t = np.cross(l, t)
    th_h = d(lean - head_ext)
    h = unit(np.cos(th_h) * UP + np.sin(th_h) * fwd)
    pose = dict(t=t, l=l, h=h)
    for s, sg, (ab, fl, el, sw) in (('L', 1.0, arms[0]), ('R', -1.0, arms[1])):
        side = sg * l
        ua = unit(np.cos(d(ab)) * (-t) + np.sin(d(ab)) * (np.cos(d(fl)) * side + np.sin(d(fl)) * fwd_t))
        ref = np.cos(d(sw)) * fwd_t + np.sin(d(sw)) * t
        e = ref - np.dot(ref, ua) * ua
        if np.linalg.norm(e) < 1e-3:
            e = side - np.dot(side, ua) * ua
        e = unit(e)
        pose['ua' + s] = ua
        pose['fa' + s] = unit(np.cos(d(el)) * ua + np.sin(d(el)) * e)
    for s, sg, (hp, ab, kn) in (('L', 1.0, legs[0]), ('R', -1.0, legs[1])):
        side = sg * left
        pose['th' + s] = unit(np.cos(d(ab)) * (np.cos(d(hp)) * (-UP) + np.sin(d(hp)) * fwd) + np.sin(d(ab)) * side)
        pose['sh' + s] = unit(np.cos(d(ab)) * (np.cos(d(hp - kn)) * (-UP) + np.sin(d(hp - kn)) * fwd) + np.sin(d(ab)) * side)
    if invert:
        Rm = np.diag([1.0, -1.0, -1.0])        # rotate 180 degrees about the wind axis: a handstand
        pose = {k: Rm @ v for k, v in pose.items()}
    return pose


def sample_pose(rng, family=None):
    """Training distribution: upright-to-tucked people roughly facing the wind."""
    U = rng.uniform
    family = family or rng.choice(['stand', 'tuck', 'wide'], p=[0.4, 0.4, 0.2])
    yaw = float(np.clip(rng.normal(0, 12), -30, 30))
    def arm():
        m = rng.choice(['down', 'any', 'fwd', 'back', 'up'], p=[0.3, 0.3, 0.15, 0.1, 0.15])
        if m == 'down':
            return (U(0, 25), U(-20, 40), U(0, 40), U(0, 90))
        if m == 'fwd':
            return (U(60, 130), U(60, 110), U(0, 90), U(-30, 90))
        if m == 'back':
            return (U(10, 50), U(-60, -10), U(0, 30), U(0, 90))
        if m == 'up':
            return (U(130, 180), U(-20, 60), U(0, 50), U(0, 90))
        return (U(0, 180), U(-40, 120), U(0, 140), U(-60, 120))
    if family == 'stand':
        lean = U(0, 35)
        legs = [(U(-25, 25), U(0, 15), U(0, 25)) for _ in range(2)]
    elif family == 'tuck':
        lean = U(30, 95)
        hp = U(0, 100)
        legs = [(float(np.clip(hp + U(-12, 12), -10, 110)), U(0, 20), 0.0) for _ in range(2)]
        legs = [(a, b, float(np.clip(a * U(0.6, 1.9) + U(-10, 20), 0, 140))) for a, b, _ in legs]
    else:
        lean = U(0, 30)
        legs = [(U(-15, 15), U(10, 45), U(0, 20)) for _ in range(2)]
    arms = (arm(), arm()) if rng.random() < 0.45 else None
    if arms is None:
        a = arm()
        arms = (a, tuple(v + rng.normal(0, 6) for v in a))
    if family == 'wide':
        arms = tuple((U(50, 160), U(-20, 30), U(0, 40), U(0, 90)) for _ in range(2))
    head_ext = U(0, min(lean, 65)) if lean > 10 else U(-10, 10)
    return make_pose(yaw=yaw, lean=lean, side_lean=float(rng.normal(0, 4)), head_ext=head_ext, arms=arms, legs=tuple(legs)), family


def sample_ood(rng, kind):
    """Poses outside the training distribution, for testing the doubt signal."""
    pose, fam = sample_pose(rng)
    U = rng.uniform
    if kind == 'side':                         # side-on to the wind
        ang = U(60, 120) * rng.choice([-1, 1])
    elif kind == 'back':                       # back to the wind
        ang = U(150, 210)
    elif kind == 'inverted':                   # handstand
        return {k: np.diag([1.0, -1.0, -1.0]) @ v for k, v in pose.items()}, 'inverted'
    elif kind == 'prone':                      # lying head-first into the wind ("superman")
        legs = tuple((U(-100, -75), U(0, 12), U(0, 15)) for _ in range(2))
        a = rng.choice(['fwd', 'back'])
        arms = tuple(((U(150, 180), U(-10, 30), U(0, 20), 0) if a == 'fwd' else (U(0, 20), U(-10, 20), U(0, 15), 0)) for _ in range(2))
        return make_pose(yaw=float(rng.normal(0, 8)), lean=U(80, 95), head_ext=U(0, 40), arms=arms, legs=legs), 'prone'
    else:
        raise ValueError(kind)
    R = rotz(np.deg2rad(ang))
    return {k: R @ v for k, v in pose.items()}, kind


NAMED = {
    'standing':  dict(),
    't_pose':    dict(arms=((90, 0, 0, 0), (90, 0, 0, 0))),
    'arms_up':   dict(arms=((175, 0, 0, 0), (175, 0, 0, 0))),
    'star':      dict(arms=((120, 0, 0, 0), (120, 0, 0, 0)), legs=((0, 30, 0), (0, 30, 0))),
    'bow_45':    dict(lean=45, head_ext=30, legs=((0, 4, 0), (0, 4, 0))),
    'ski_tuck':  dict(lean=80, head_ext=55, arms=((70, 80, 110, 60), (70, 80, 110, 60)), legs=((75, 5, 120), (75, 5, 120))),
    'ski_jump':  dict(lean=75, head_ext=40, arms=((15, -25, 0, 0), (15, -25, 0, 0)), legs=((35, 4, 60), (35, 4, 60))),
    'sitting':   dict(lean=5, arms=((10, 30, 60, 0), (10, 30, 60, 0)), legs=((90, 6, 90), (90, 6, 90))),
    'prone_superman': dict(lean=90, head_ext=30, arms=((178, 0, 0, 0), (178, 0, 0, 0)), legs=((-90, 3, 0), (-90, 3, 0))),
    'side_on':   dict(yaw=90),
    'handstand': dict(invert=True, arms=((178, 0, 0, 0), (178, 0, 0, 0))),
}


def pose_to_list(pose):
    """12 vectors in BONES order; the hip line falls back to the shoulder line when the pose has none."""
    return [[float(x) for x in (pose[k] if k in pose else pose['l'])] for k in BONES]


def pose_from_list(lst):
    """Accepts 11 vectors (runs before the hip line existed) or 12."""
    return {k: np.array(v, float) for k, v in zip(BONES, lst)}


def twist(pose, deg):
    """Turn the hips (and legs) by `deg` about the torso axis relative to the shoulders. Returns a new pose with 'lh' set."""
    t = unit(pose['t']); a = np.deg2rad(deg)
    K = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
    Rm = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
    out = dict(pose)
    out['lh'] = Rm @ hip_line(pose)
    for k in ('thL', 'shL', 'thR', 'shR'):
        out[k] = Rm @ np.asarray(pose[k], float)
    return out


def proj_area(pose, drop, res=0.02, body=None):
    """Area of the body's shadow on the plane perpendicular to axis `drop` (0: seen along the wind, 1: from the side, 2: from above), m^2."""
    J = joints(pose, body); caps = capsules(J, pose, body)
    k = [i for i in range(3) if i != drop]
    lo = np.min([np.minimum(a[k], b_[k]) - r for a, b_, r, _ in caps], axis=0) - res
    hi = np.max([np.maximum(a[k], b_[k]) + r for a, b_, r, _ in caps], axis=0) + res
    n = np.ceil((hi - lo) / res).astype(int)
    U, V = np.meshgrid(lo[0] + (np.arange(n[0]) + 0.5) * res, lo[1] + (np.arange(n[1]) + 0.5) * res, indexing='ij')
    img = np.zeros(U.shape, bool)
    for a, b_, r, _ in caps:
        A, Bp = a[k], b_[k]; d = Bp - A; dd = float(d @ d)
        t = np.clip(((U - A[0]) * d[0] + (V - A[1]) * d[1]) / dd, 0, 1) if dd > 1e-12 else 0.0
        img |= (U - A[0] - t * d[0]) ** 2 + (V - A[1] - t * d[1]) ** 2 < r * r
    return float(img.sum() * res * res)


def full_features(pose, area_front):
    """Model input: 36 joint coordinates, pelvis height, side and top shadow areas, and the frontal area last (40 numbers)."""
    return list(features(pose)) + [proj_area(pose, 1), proj_area(pose, 2), float(area_front)]

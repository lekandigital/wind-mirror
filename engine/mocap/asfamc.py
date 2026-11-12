"""Minimal Acclaim ASF/AMC parser and forward kinematics (CMU Graphics Lab mocap), numpy only.

Conventions (Acclaim spec / CMU's own viewer code, column vectors):
  C      = Rz(az) Ry(ay) Rx(ax) from a bone's `axis ax ay az XYZ` line (degrees)
  M(f)   = Rz(rz) Ry(ry) Rx(rx) from the bone's AMC dof values (missing dofs are 0)
  R_bone = R_parent C M C^-1
  end    = start + length * R_bone @ direction    (direction is given in the global frame of the rest pose)
  root:  R_root = C_root M_root C_root^-1, position = (TX, TY, TZ) from the AMC
CMU files are y-up, lengths in inches * units_length (0.45), so metres = value / units_length * 0.0254.
In the CMU rest pose the subject faces +z with their left side at +x.
"""
import numpy as np

# Proper rotation (det +1) CMU (x left, y up, z forward in the rest pose) -> Wind Mirror world
# (x downwind, y lateral, z up; a person facing the wind faces -x with their left at -y):
#   CMU +z (forward) -> world -x,  CMU +x (left) -> world -y,  CMU +y (up) -> world +z.
CMU_TO_WORLD = np.array([[0.0, 0.0, -1.0],
                         [-1.0, 0.0, 0.0],
                         [0.0, 1.0, 0.0]])
assert abs(np.linalg.det(CMU_TO_WORLD) - 1.0) < 1e-12


def _rx(a):
    c, s = np.cos(a), np.sin(a)
    o, z = np.ones_like(a), np.zeros_like(a)
    return np.stack([np.stack([o, z, z], -1), np.stack([z, c, -s], -1), np.stack([z, s, c], -1)], -2)


def _ry(a):
    c, s = np.cos(a), np.sin(a)
    o, z = np.ones_like(a), np.zeros_like(a)
    return np.stack([np.stack([c, z, s], -1), np.stack([z, o, z], -1), np.stack([-s, z, c], -1)], -2)


def _rz(a):
    c, s = np.cos(a), np.sin(a)
    o, z = np.ones_like(a), np.zeros_like(a)
    return np.stack([np.stack([c, -s, z], -1), np.stack([s, c, z], -1), np.stack([z, z, o], -1)], -2)


def euler(angles_deg, order='XYZ'):
    """angles_deg (..., 3) as (ax, ay, az). order 'XYZ' means rotate about X first: R = Rz Ry Rx."""
    a = np.deg2rad(np.asarray(angles_deg, float))
    mats = {'X': _rx(a[..., 0]), 'Y': _ry(a[..., 1]), 'Z': _rz(a[..., 2])}
    R = mats[order[0]]
    for ax in order[1:]:
        R = mats[ax] @ R
    return R


class Skeleton:
    def __init__(self, path):
        self.bones = {}
        self.parent = {}
        self.children = {}
        self.units_length = 1.0
        self.angle_unit = 'deg'
        self.root_order = ['TX', 'TY', 'TZ', 'RX', 'RY', 'RZ']
        self.root_axis = 'XYZ'
        self.root_orientation = np.zeros(3)
        self.root_position = np.zeros(3)
        self._parse(path)
        self.scale = 0.0254 / self.units_length          # file units -> metres
        for name, b in self.bones.items():
            b['C'] = euler(b['axis'], b['axis_order'])
            b['Cinv'] = b['C'].T
        self.root_C = euler(self.root_orientation, self.root_axis)
        self.order = []                                     # parents before children
        stack = ['root']
        while stack:
            n = stack.pop(0)
            for c in self.children.get(n, []):
                self.order.append(c)
                stack.append(c)

    def _parse(self, path):
        lines = [ln.strip() for ln in open(path, encoding='latin-1')]
        sec, cur = None, None
        i = 0
        while i < len(lines):
            ln = lines[i]
            i += 1
            if not ln or ln.startswith('#'):
                continue
            if ln.startswith(':'):
                parts = ln.split()
                sec = parts[0][1:]
                continue
            tok = ln.split()
            if sec == 'units':
                if tok[0] == 'length':
                    self.units_length = float(tok[1])
                elif tok[0] == 'angle':
                    self.angle_unit = tok[1]
            elif sec == 'root':
                if tok[0] == 'order':
                    self.root_order = [t.upper() for t in tok[1:]]
                elif tok[0] == 'axis':
                    self.root_axis = tok[1].upper()
                elif tok[0] == 'orientation':
                    self.root_orientation = np.array([float(x) for x in tok[1:4]])
                elif tok[0] == 'position':
                    self.root_position = np.array([float(x) for x in tok[1:4]])
            elif sec == 'bonedata':
                if tok[0] == 'begin':
                    cur = dict(dof=[], axis=np.zeros(3), axis_order='XYZ', direction=np.zeros(3), length=0.0)
                elif tok[0] == 'end':
                    self.bones[cur['name']] = cur
                    cur = None
                elif tok[0] == 'name':
                    cur['name'] = tok[1]
                elif tok[0] == 'direction':
                    cur['direction'] = np.array([float(x) for x in tok[1:4]])
                elif tok[0] == 'length':
                    cur['length'] = float(tok[1])
                elif tok[0] == 'axis':
                    cur['axis'] = np.array([float(x) for x in tok[1:4]])
                    cur['axis_order'] = tok[4].upper() if len(tok) > 4 else 'XYZ'
                elif tok[0] == 'dof':
                    cur['dof'] = [t.lower() for t in tok[1:]]
            elif sec == 'hierarchy':
                if tok[0] in ('begin', 'end'):
                    continue
                self.children[tok[0]] = tok[1:]
                for c in tok[1:]:
                    self.parent[c] = tok[0]
        if self.angle_unit not in ('deg', 'degree', 'degrees'):
            raise ValueError(f'{path}: angle unit {self.angle_unit} not supported')

    def rest_height_m(self):
        """Stature proxy in metres: vertical extent from the ball of the foot (end of the foot bone) to the end of the
        head bone, with the legs straight down (rest-pose spine/neck/head y components, hip-joint drop, full femur and
        tibia lengths, foot drop). Averaged over left and right legs. The end of the CMU head bone sits a few cm below
        the top of the skull, so this slightly underestimates true stature."""
        up = 0.0
        for n in ('lowerback', 'upperback', 'thorax', 'lowerneck', 'upperneck', 'head'):
            up += self.bones[n]['length'] * self.bones[n]['direction'][1]
        downs = []
        for s in 'lr':
            hj, fe, ti, fo = (self.bones[s + n] for n in ('hipjoint', 'femur', 'tibia', 'foot'))
            downs.append(-hj['length'] * hj['direction'][1] + fe['length'] + ti['length'] - fo['length'] * fo['direction'][1])
        return float((up + np.mean(downs)) * self.scale)


def read_amc(path, skel):
    """Returns (frame_numbers (F,), dict bone -> (F, ndof) array in the order of that bone's dofs, root (F, 6))."""
    names = None
    data = {}
    frames = []
    cur = None
    with open(path, encoding='latin-1') as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or ln[0] in '#:':
                continue
            if ln.isdigit():
                frames.append(int(ln))
                continue
            tok = ln.split()
            data.setdefault(tok[0], []).append([float(x) for x in tok[1:]])
    F = len(frames)
    out = {}
    for k, v in data.items():
        if len(v) != F:
            raise ValueError(f'{path}: bone {k} has {len(v)} rows for {F} frames')
        out[k] = np.array(v, float)
    return np.array(frames), out


def fk(skel, motion, idx=None):
    """Forward kinematics. motion: dict from read_amc. idx: optional frame indices (0-based rows) to evaluate.
    Returns dict joint-name -> (F, 3) positions in METRES in the CMU frame (y up), with
      'root' and '<bone>' = the END point of each bone (start of its children)."""
    def rows(a):
        return a if idx is None else a[idx]
    root = rows(motion['root'])
    F = root.shape[0]
    vals = {k: root[:, i] for i, k in enumerate(skel.root_order)}
    pos_root = np.stack([vals.get('TX', np.zeros(F)), vals.get('TY', np.zeros(F)), vals.get('TZ', np.zeros(F))], -1)
    pos_root = (pos_root + skel.root_position) * skel.scale
    rot = np.stack([vals.get('RX', np.zeros(F)), vals.get('RY', np.zeros(F)), vals.get('RZ', np.zeros(F))], -1)
    # root rotation order is given by the root 'axis' line, and the RX/RY/RZ values by 'order'
    M = euler(rot, skel.root_axis)
    R = {'root': skel.root_C @ M @ skel.root_C.T}
    P = {'root': pos_root}
    for name in skel.order:
        b = skel.bones[name]
        par = skel.parent[name]
        ang = np.zeros((F, 3))
        if b['dof'] and name in motion:
            v = rows(motion[name])
            for j, d in enumerate(b['dof']):
                if d in ('rx', 'ry', 'rz'):
                    ang[:, 'xyz'.index(d[1])] = v[:, j]
        Mb = euler(ang, 'XYZ')
        Rb = R[par] @ b['C'] @ Mb @ b['Cinv']
        R[name] = Rb
        P[name] = P[par] + (b['length'] * skel.scale) * (Rb @ b['direction'])
    return P


def to_world(P):
    """CMU (y up) positions -> Wind Mirror world (z up), proper rotation."""
    return {k: v @ CMU_TO_WORLD.T for k, v in P.items()}

"""Helpers for the agent's design task: propose body positions that a person could hold, as make_pose arguments.

Task used tonight: the lowest-drag position a person can hold facing the wind with both feet on the ground,
head up (tilted no more than 45 degrees forward) and balanced over the feet (ski-tuck problem).
  propose <n> <seed> <out.json>           random symmetric candidates that pass the constraints
  refine <cands.json> <idx,idx,..> <n> <seed> <out.json>   new candidates near chosen ones
"""
import sys, json
import numpy as np
import bodies as B


def com_and_support(pose):
    J = B.joints(pose); caps = B.capsules(J, pose)
    num = np.zeros(3); den = 0.0
    for a, b, r, _ in caps:
        L = np.linalg.norm(b - a); v = np.pi * r * r * L + 4 / 3 * np.pi * r ** 3
        num += v * (a + b) / 2; den += v
    com = num / den
    xs = [J['anL'][0], J['toeL'][0], J['anR'][0], J['toeR'][0]]
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in caps)
    feet_low = min(J['anL'][2], J['toeL'][2]) - B.RAD['foot'] - zmin      # how far the feet are above the lowest point
    return com, (min(xs) - 0.04, max(xs) + 0.04), feet_low, -zmin


def ok(spec):
    pose = B.make_pose(**spec)
    if spec['lean'] - spec['head_ext'] > 45:                 # head up enough to look ahead
        return False
    com, (x0, x1), feet_low, pelvis_h = com_and_support(pose)
    if not (x0 <= com[0] <= x1):                             # balanced over the feet (approximate centre of mass)
        return False
    if feet_low > 0.03:                                      # feet are what touches the ground
        return False
    J = B.joints(pose)
    for s in 'LR':                                           # hands and elbows stay off the ground and outside the legs' line
        if J['wr' + s][2] + pelvis_h < 0.08 or J['el' + s][2] + pelvis_h < 0.08:
            return False
    return True


def sample(rng, around=None, spread=1.0):
    U = rng.uniform
    if around is None:
        lean = U(0, 95); arm = (U(0, 180), U(-60, 120), U(0, 150), U(-60, 120)); leg = (U(0, 115), U(0, 20), U(0, 150))
        head_ext = U(max(0, lean - 45), min(lean, 75)) if lean > 5 else 0.0
    else:
        g = lambda v, s, lo, hi: float(np.clip(v + rng.normal(0, s * spread), lo, hi))
        a0, l0 = around['arms'][0], around['legs'][0]
        lean = g(around['lean'], 6, 0, 95); head_ext = g(around['head_ext'], 6, 0, 75)
        arm = (g(a0[0], 12, 0, 180), g(a0[1], 12, -60, 120), g(a0[2], 12, 0, 150), g(a0[3], 15, -60, 120))
        leg = (g(l0[0], 7, 0, 115), g(l0[1], 3, 0, 20), g(l0[2], 9, 0, 150))
    r = lambda t: [round(float(x), 1) for x in t]
    return dict(lean=round(float(lean), 1), head_ext=round(float(head_ext), 1), arms=[r(arm), r(arm)], legs=[r(leg), r(leg)])


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'propose':
        n, seed, out = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
        rng = np.random.default_rng(seed); C = []; tried = 0
        while len(C) < n:
            s = sample(rng); tried += 1
            if ok(s): C.append(s)
        json.dump(C, open(out, 'w')); print(json.dumps(dict(proposed=n, tried=tried, passed_constraints_pct=round(100 * n / tried, 1))))
    elif cmd == 'refine':
        src, idx, n, seed, out = json.load(open(sys.argv[2])), [int(x) for x in sys.argv[3].split(',')], int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
        rng = np.random.default_rng(seed); C = [src[i] for i in idx]; tried = 0
        while len(C) < n:
            s = sample(rng, around=src[idx[tried % len(idx)]]); tried += 1
            if ok(s): C.append(s)
        json.dump(C, open(out, 'w')); print(json.dumps(dict(proposed=n, tried=tried)))

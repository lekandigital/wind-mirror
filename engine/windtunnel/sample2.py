"""Build the queue of poses and body shapes for dataset v2. Deterministic: the same arguments give the same file.

Families (each queue item carries its family so any of them can be held out of training later):
  stand, tuck, wide   the pitch-night training families (roughly facing the wind)
  turn                any of those turned to any heading, 0-360 degrees (includes side-on and back to the wind)
  squat               knees bent deep with a fairly upright torso (sitting, squatting)
  stride              legs doing different things (lunge, step, one leg raised)
  bend                leaning sideways
  twist               hips turned against the shoulders
  inverted, prone, supine   handstand, lying head-first, lying on the back: never used for training, kept for testing the doubt signal

Usage: python sample2.py <out_queue.jsonl> <n> [seed]
"""
import sys, json
import numpy as np
import bodies as B

FAMILIES = dict(stand=0.16, tuck=0.13, wide=0.07, turn=0.24, squat=0.09, stride=0.10, bend=0.05, twist=0.06, inverted=0.03, prone=0.04, supine=0.03)
P_RANDOM_SHAPE = 0.55


def arm(rng):
    U = rng.uniform
    m = rng.choice(['down', 'any', 'fwd', 'back', 'up', 'out'], p=[0.25, 0.3, 0.13, 0.08, 0.12, 0.12])
    if m == 'down':
        return (U(0, 25), U(-20, 40), U(0, 40), U(0, 90))
    if m == 'fwd':
        return (U(60, 130), U(60, 110), U(0, 90), U(-30, 90))
    if m == 'back':
        return (U(10, 50), U(-60, -10), U(0, 30), U(0, 90))
    if m == 'up':
        return (U(130, 180), U(-20, 60), U(0, 50), U(0, 90))
    if m == 'out':
        return (U(60, 120), U(-25, 25), U(0, 30), U(0, 90))
    return (U(0, 180), U(-40, 120), U(0, 140), U(-60, 120))


def arms(rng):
    if rng.random() < 0.5:
        return (arm(rng), arm(rng))
    a = arm(rng)
    return (a, tuple(float(v + rng.normal(0, 6)) for v in a))


def small_yaw(rng):
    return float(np.clip(rng.normal(0, 12), -30, 30))


def rot_all(pose, R):
    return {k: R @ np.asarray(v, float) for k, v in pose.items()}


def sample(rng, family):
    U = rng.uniform
    kw = None
    if family in ('stand', 'tuck', 'wide'):
        pose, _ = B.sample_pose(rng, family)
    elif family == 'turn':
        base = rng.choice(['stand', 'tuck', 'wide', 'squat', 'stride'], p=[0.4, 0.2, 0.15, 0.1, 0.15])
        pose = sample(rng, str(base))[0]
        pose = rot_all(pose, B.rotz(np.deg2rad(U(-180, 180))))
    elif family == 'squat':
        hp = U(40, 110)
        legs = []
        for _ in range(2):
            a = float(np.clip(hp + U(-10, 10), 20, 120))
            legs.append((a, U(0, 30), float(np.clip(a * U(0.8, 1.6) + U(-10, 20), 0, 140))))
        lean = U(0, 45)
        kw = dict(yaw=small_yaw(rng), lean=lean, side_lean=float(rng.normal(0, 4)), head_ext=U(0, min(lean, 40)), arms=arms(rng), legs=tuple(legs))
    elif family == 'stride':
        front = (U(15, 100), U(0, 20), U(0, 110))
        back = (U(-45, 5), U(0, 20), U(0, 70))
        if rng.random() < 0.3:                                  # one leg raised to the side instead
            front = (U(-10, 40), U(30, 85), U(0, 60))
            back = (U(-8, 8), U(0, 8), U(0, 12))
        legs = (front, back) if rng.random() < 0.5 else (back, front)
        lean = U(0, 45)
        kw = dict(yaw=small_yaw(rng), lean=lean, side_lean=float(rng.normal(0, 6)), head_ext=U(0, min(lean, 40)), arms=arms(rng), legs=legs)
    elif family == 'bend':
        legs = tuple((U(-15, 15), U(0, 25), U(0, 20)) for _ in range(2))
        kw = dict(yaw=small_yaw(rng), lean=U(0, 25), side_lean=float(U(15, 50) * rng.choice([-1, 1])), head_ext=U(-10, 10), arms=arms(rng), legs=legs)
    elif family == 'twist':
        pose, _ = B.sample_pose(rng, str(rng.choice(['stand', 'wide'])))
        pose = B.twist(pose, float(U(20, 70) * rng.choice([-1, 1])))
    elif family == 'inverted':
        pose, _ = B.sample_ood(rng, 'inverted')
    elif family == 'prone':
        pose, _ = B.sample_ood(rng, 'prone')
    elif family == 'supine':
        legs = tuple((U(70, 100), U(0, 15), U(0, 30)) for _ in range(2))
        a = (U(0, 30), U(-10, 20), U(0, 30), 0.0) if rng.random() < 0.6 else (U(150, 180), U(-10, 30), U(0, 20), 0.0)
        kw = dict(yaw=float(rng.normal(0, 8)) + (180.0 if rng.random() < 0.5 else 0.0), lean=-U(80, 95), head_ext=U(-20, 10), arms=(a, a), legs=legs)
    else:
        raise ValueError(family)
    if kw is not None:
        pose = B.make_pose(**kw)
    if family not in ('twist', 'inverted', 'prone', 'supine') and 'lh' not in pose and rng.random() < 0.5:
        pose = B.twist(pose, float(np.clip(rng.normal(0, 10), -30, 30)))   # real people rarely keep hips and shoulders square
    return pose, family


def main():
    out, n = sys.argv[1], int(sys.argv[2])
    seed0 = int(sys.argv[3]) if len(sys.argv) > 3 else 20000
    fams, w = list(FAMILIES), np.array(list(FAMILIES.values())); w = w / w.sum()
    with open(out, 'w') as f:
        for i in range(n):
            rng = np.random.default_rng(seed0 + i)
            fam = str(rng.choice(fams, p=w))
            pose, fam = sample(rng, fam)
            body = B.sample_shape(rng) if rng.random() < P_RANDOM_SHAPE else None
            f.write(json.dumps(dict(qid=f's2_{seed0 + i}', source='synth2', family=fam, seed=seed0 + i, pose=B.pose_to_list(pose), body=body)) + '\n')
    print('wrote', n, 'to', out)


if __name__ == '__main__':
    main()

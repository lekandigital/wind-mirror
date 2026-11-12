"""Random search over a family of body positions, so an agent can screen tens of thousands of candidates in one call.

space: ranges (degrees) for named angles: lean, side_lean, head_ext, yaw, twist, and per-limb arm / leg angles:
  {"lean": [40, 95], "head_ext": [0, 60], "arms": {"abduction": [0, 180], "flexion": [-40, 120], "elbow": [0, 140], "swivel": [-60, 120], "symmetric": true},
   "legs": {"hip": [0, 110], "abduction": [0, 20], "knee": [0, 140], "symmetric": true}}
A single number fixes that angle. "around": {"angles": {...}, "sigma": 8} samples near a known position instead.
"""
import numpy as np

ARM = ['abduction', 'flexion', 'elbow', 'swivel']
LEG = ['hip', 'abduction', 'knee']
DEFAULT_ARM = [10.0, 0.0, 5.0, 0.0]
DEFAULT_LEG = [0.0, 4.0, 0.0]


def _draw(rng, v, default):
    if v is None:
        return float(default)
    if isinstance(v, (int, float)):
        return float(v)
    return float(rng.uniform(v[0], v[1]))


def sample(space, n, seed=0):
    rng = np.random.default_rng(seed)
    specs = []
    around = space.get('around')
    for _ in range(n):
        if around:
            a = around['angles']; sg = float(around.get('sigma', 8))
            j = lambda x: float(x + rng.normal(0, sg))
            ang = {k: j(a.get(k, 0.0)) for k in ('lean', 'side_lean', 'head_ext', 'yaw') if k in a or k == 'lean'}
            sym_a = around.get('symmetric_arms', True); sym_l = around.get('symmetric_legs', True)
            arms = [[j(x) for x in limb] for limb in a.get('arms', [DEFAULT_ARM, DEFAULT_ARM])]
            legs = [[j(x) for x in limb] for limb in a.get('legs', [DEFAULT_LEG, DEFAULT_LEG])]
            if sym_a: arms[1] = list(arms[0])
            if sym_l: legs[1] = list(legs[0])
            ang['arms'] = arms; ang['legs'] = legs
            if 'twist' in a: ang['twist'] = j(a['twist'])
        else:
            ang = {k: _draw(rng, space.get(k), 0.0) for k in ('lean', 'side_lean', 'head_ext', 'yaw')}
            if 'twist' in space: ang['twist'] = _draw(rng, space['twist'], 0.0)
            for key, names, dflt in (('arms', ARM, DEFAULT_ARM), ('legs', LEG, DEFAULT_LEG)):
                sp = space.get(key, {})
                one = lambda: [_draw(rng, sp.get(nm), d) for nm, d in zip(names, dflt)]
                left = one(); right = list(left) if sp.get('symmetric', True) else one()
                ang[key] = [left, right]
        ang['legs'] = [[l[0], max(l[1], 0.0), float(np.clip(l[2], 0, 150))] for l in ang['legs']]
        ang['arms'] = [[float(np.clip(a_[0], 0, 180)), a_[1], float(np.clip(a_[2], 0, 150)), a_[3]] for a_ in ang['arms']]
        specs.append(dict(angles=ang))
    return specs


def passes(res, c):
    return stance_ok(res['stance'], c)


def stance_ok(st, c):
    if c.get('feet_on_floor') and not st['feet_on_floor']:
        return False
    if 'max_com_offset_m' in c and max(abs(st['com_ahead_m']), abs(st['com_side_m'])) > c['max_com_offset_m']:
        return False
    if 'min_clearance_m' in c and st['rest_of_body_clearance_m'] < c['min_clearance_m']:
        return False
    if 'max_legs_through_torso_m' in c and st['legs_through_torso_m'] > c['max_legs_through_torso_m']:
        return False
    if 'min_head_height_m' in c and st['head_height_m'] < c['min_head_height_m']:
        return False
    if 'min_head_dir_up' in c and st['head_dir_up'] < c['min_head_dir_up']:
        return False
    if 'lowest_part_in' in c and st['lowest_part'] not in c['lowest_part_in']:
        return False
    return True


OBJ = dict(min_drag=lambda r: r['drag_area_m2'], max_drag=lambda r: -r['drag_area_m2'], max_lift=lambda r: -r['lift_area_m2'], min_lift=lambda r: r['lift_area_m2'],
           max_side=lambda r: -abs(r['side_area_m2']), max_lift_to_drag=lambda r: -r['lift_area_m2'] / max(r['drag_area_m2'], 1e-6))


def search(engine, space, n=2000, objective='min_drag', constraints=None, top_k=8, seed=0):
    import time
    from engine import featurise
    specs = sample(space, int(n), seed)
    t0 = time.perf_counter()
    X, st = featurise(specs)                                    # geometry for every candidate
    keep = [i for i in range(len(specs)) if stance_ok(st[i], constraints or {})]
    out = engine.results(X[keep], [st[i] for i in keep], time.perf_counter() - t0)   # the model only for those that meet the constraints
    ok = [dict(r, angles=specs[i]['angles']) for r, i in zip(out['results'], keep)]
    key = OBJ[objective]
    slim = lambda r: dict(angles={k: ([[round(x, 1) for x in l] for l in v] if isinstance(v, list) else round(v, 1)) for k, v in r['angles'].items()},
                          drag_area_m2=r['drag_area_m2'], lift_area_m2=r['lift_area_m2'], side_area_m2=r['side_area_m2'], push_kg_at_100kmh=r['push_kg_at_100kmh'],
                          error_bound_pct=r['error_bound_pct'], sure=r['sure'], stance=r['stance'])
    sure = sorted([r for r in ok if r['sure']], key=key)[:top_k]
    unsure = sorted([r for r in ok if not r['sure']], key=key)[:top_k]
    return dict(n_sampled=len(specs), n_meeting_constraints=len(ok), n_sure=sum(r['sure'] for r in ok), objective=objective,
                best_sure=[slim(r) for r in sure], best_unsure=[slim(r) for r in unsure], model_version=out['model_version'],
                seconds_geometry=out['seconds_geometry'], seconds_model=out['seconds_model'])

"""The engine behind both doors (the page and the agent tools): check, solve, learn.

  check(specs)  -> forces, error bound and verdict for each body, from model B (milliseconds)
  solve(spec)   -> the full flow solver on one body (seconds on a GPU); the run is kept
  learn(runs)   -> add solver runs to the model, re-calibrate the bound, bump the version

A body spec is {"angles": {...}} (named joint angles, see bodies.make_pose) or {"pose": [12 unit vectors]},
plus an optional "body": {shape multipliers}. State lives in a directory: store.npz (factory set + calibration) and
learned.jsonl (every solver run learned since).
"""
import json, os, time, threading
import numpy as np
import bodies as B, geom as G
from surrogate import Doubt, verr
from model_b import ModelB, SIG_NAMES

Q_KG = 0.5 * 1.225 * (100 / 3.6) ** 2 / 9.80665            # kg of push per m^2 of drag area in a 100 km/h wind


def spec_pose(spec):
    if 'pose' in spec:
        return B.pose_from_list(spec['pose'])
    kw = dict(spec.get('angles', {}))
    tw = kw.pop('twist', 0.0)
    for k in ('arms', 'legs'):
        if k in kw:
            kw[k] = tuple(tuple(a) for a in kw[k])
    pose = B.make_pose(**kw)
    return B.twist(pose, tw) if tw else pose


def seg_dist(p1, q1, p2, q2):
    """Shortest distance between segments p1-q1 and p2-q2."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = float(d1 @ d1), float(d2 @ d2), float(d2 @ r)
    if a < 1e-12 and e < 1e-12:
        return float(np.linalg.norm(r))
    if a < 1e-12:
        s, t = 0.0, np.clip(f / e, 0, 1)
    else:
        c = float(d1 @ r)
        if e < 1e-12:
            t, s = 0.0, np.clip(-c / a, 0, 1)
        else:
            b = float(d1 @ d2); den = a * e - b * b
            s = np.clip((b * f - c * e) / den, 0, 1) if den > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, np.clip(-c / a, 0, 1)
            elif t > 1:
                t, s = 1.0, np.clip((b - c) / a, 0, 1)
    return float(np.linalg.norm((p1 + d1 * s) - (p2 + d2 * t)))


def stance(pose, body=None):
    """Simple facts about how the body stands, for design constraints: are both feet on the floor, how far the centre of
    mass sits from the middle of the feet (metres, along the wind and across it), and how high the head is."""
    caps = G.body_capsules(pose, body)
    vol = np.array([np.pi * r * r * (np.linalg.norm(b - a) + 4.0 * r / 3.0) for a, b, r, _ in caps])
    com = sum(v * (a + b) / 2 for v, (a, b, r, _) in zip(vol, caps)) / vol.sum()
    J = B.joints(pose, body)
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in B.capsules(J, pose, body))
    feet = [(J['an' + s] + J['toe' + s]) / 2 - np.array([0, 0, zmin]) for s in 'LR']
    foot_low = [min(J['an' + s][2], J['toe' + s][2]) - zmin - B.dims(body)[1]['foot'] for s in 'LR']
    mid = (feet[0] + feet[1]) / 2
    lowest = min(caps, key=lambda c: min(c[0][2], c[1][2]) - c[2])[3]
    # clearance of everything that is not a foot or a lower leg, plus the knees (a shin's upper end)
    other = min([min(a[2], b[2]) - r for i, (a, b, r, p) in enumerate(caps) if i not in (11, 12, 17, 18)] + [caps[i][0][2] - caps[i][2] for i in (11, 17)])
    # how far the legs pass through the torso or head (a body cannot do that): the knee half of each thigh, and each shin,
    # against the chest capsules and the head; 0 when they only touch
    over = 0.0
    for li in (10, 16, 11, 17):
        a, b, r, _ = caps[li]
        a2 = (a + b) / 2 if li in (10, 16) else a
        for ti in (0, 2, 3, 4, 5):
            c, d, r2, _ = caps[ti]
            over = max(over, r + r2 - seg_dist(a2, b, c, d))
    return dict(feet_on_floor=bool(max(foot_low) < 0.04), rest_of_body_clearance_m=round(float(other), 3), legs_through_torso_m=round(float(max(over, 0.0)), 3), com_ahead_m=round(float(mid[0] - com[0]), 3), com_side_m=round(float(com[1] - mid[1]), 3),
                com_height_m=round(float(com[2]), 3), head_height_m=round(float(J['head'][2] - zmin), 3), lowest_part=B.PARTS[lowest],
                head_dir_up=round(float(B.unit(pose['h'])[2]), 3))


def _feat(spec):
    pose = spec_pose(spec)
    return G.features(pose, spec.get('body')), stance(pose, spec.get('body'))


def featurise(specs, procs=None):
    if len(specs) < 48:
        r = [_feat(s) for s in specs]
    else:
        from multiprocessing import Pool
        with Pool(procs or min(os.cpu_count() or 4, 24)) as pool:
            r = pool.map(_feat, specs, chunksize=16)
    return np.array([a for a, _ in r]), [b for _, b in r]


class Engine:
    def __init__(self, state_dir, store=None):
        self.dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        z = np.load(store or f'{state_dir}/store.npz', allow_pickle=False)
        self.kw = dict(ell=float(z['ell']), noise=float(z['noise']), k=int(z['k']))
        self.tol, self.alpha = float(z['tol']), float(z['alpha'])
        self.X0, self.y0, self.yp0 = z['X'], z['y'], z['yp']
        self.doubt = Doubt.__new__(Doubt)
        self.doubt.use = list(z['doubt_use']); self.doubt.w = z['doubt_w']; self.doubt.q = float(z['doubt_q']); self.doubt.alpha = self.alpha; self.doubt.floor = 0.01; self.doubt.s0 = float(z['doubt_s0']) if 'doubt_s0' in z.files else 0.0
        self.q_factory = self.doubt.q
        self.learned = []
        lp = f'{state_dir}/learned.jsonl'
        if os.path.exists(lp):
            self.learned = [json.loads(l) for l in open(lp)]
        self.lock = threading.Lock()
        self.version = 0
        self.solver = None
        self._rebuild()

    # ---- model
    def _rebuild(self):
        t0 = time.time()
        X, y, yp = self.X0, self.y0, self.yp0
        if self.learned:
            X = np.concatenate([X, np.array([r['features'] for r in self.learned])])
            y = np.concatenate([y, np.array([r['force'] for r in self.learned])])
            yp = np.concatenate([yp, np.array([r['parts'] for r in self.learned])])
        m = ModelB(X, y, yp, **self.kw)
        # re-calibrate: leave-one-run-out conformal factor over every run, never below the factory (leave-family-out) factor
        S, e = m.loo_signals()
        self.q_loo = self.doubt.conformal(S, e, self.alpha)
        self.doubt.q = max(self.q_factory, self.q_loo)
        self.model = m
        self.version += 1
        self.n_runs = len(X)
        self.rebuild_s = time.time() - t0

    def check_features(self, X):
        p, S = self.model.signals(np.atleast_2d(X))
        bound = self.doubt.bound(S)
        parts = self.model.parts.predict(np.atleast_2d(X))
        return p, bound, S, parts

    def check(self, specs):
        t0 = time.perf_counter()
        X, st = featurise(specs)
        return self.results(X, st, time.perf_counter() - t0)

    def results(self, X, st, seconds_geometry=0.0):
        """Model answers for bodies whose features (X) and stance facts (st) are already computed."""
        t1 = time.perf_counter()
        with self.lock:
            p, bound, S, parts = self.check_features(X) if len(X) else (np.zeros((0, 3)), np.zeros(0), np.zeros((0, len(SIG_NAMES))), np.zeros((0, len(B.PARTS), 3)))
        t2 = time.perf_counter()
        out = []
        for i in range(len(X)):
            out.append(dict(drag_area_m2=round(float(p[i, 0]), 4), lift_area_m2=round(float(p[i, 1]), 4), side_area_m2=round(float(p[i, 2]), 4),
                            push_kg_at_100kmh=round(float(p[i, 0] * Q_KG), 2), error_bound_pct=round(float(bound[i] * 100), 1), sure=bool(bound[i] <= self.tol),
                            frontal_area_m2=round(float(X[i, 0]), 4), signals={n: round(float(v), 4) for n, v in zip(SIG_NAMES, S[i])},
                            part_drag_m2={n: round(float(v), 4) for n, v in zip(B.PARTS, parts[i, :, 0])}, stance=st[i]))
        return dict(results=out, n=len(X), n_sure=int(sum(o['sure'] for o in out)), model_version=self.version, tolerance_pct=self.tol * 100,
                    seconds_geometry=round(seconds_geometry, 4), seconds_model=round(t2 - t1, 4))

    # ---- solver (one GPU worker; Taichi stays on the thread that first used it)
    def _solver(self):
        if self.solver is None:
            import gen2
            self.gen2 = gen2
            self.solver = gen2.Tunnel(gen2.NX, gen2.NY, gen2.NZ, U=gen2.U, nu=gen2.NU, nparts=len(B.PARTS))
        return self.solver

    def solve(self, spec, fields_path=None):
        """Runs the flow solver. Returns the run record (forces, timings) with the model's answer at the time, for comparison."""
        pose = spec_pose(spec); body = spec.get('body')
        X = G.features(pose, body)
        with self.lock:
            p, bound, S, _ = self.check_features(X)
        T = self._solver()
        rec, info, fld = self.gen2.solve_one(T, pose, body, fields=fields_path is not None)
        if rec is None:
            return dict(error='the body does not fit in the tunnel')
        if rec.get('diverged'):
            return dict(error='the solver diverged on this body (non-finite forces); nothing was learned')
        F = np.array(rec['F_parts']) * rec['corr']
        force = [float(F[:, 0].sum()), float(F[:, 2].sum()), float(F[:, 1].sum())]
        if fld is not None:
            np.save(fields_path, fld)
        run = dict(pose=B.pose_to_list(pose), body=body, features=[float(v) for v in X], force=force, parts=F[:, [0, 2, 1]].tolist(),
                   seconds=round(rec['seconds'], 2), area_m2=rec['area_m2'], F_halves=rec.get('F_halves'),
                   model_before=dict(force=[float(v) for v in p[0]], error_bound_pct=round(float(bound[0] * 100), 1), sure=bool(bound[0] <= self.tol),
                                     error_pct=round(float(verr(p, np.array([force]))[0] * 100), 1), version=self.version), t=time.time())
        return run

    def learn(self, runs):
        with self.lock:
            with open(f'{self.dir}/learned.jsonl', 'a') as f:
                for r in runs:
                    self.learned.append(r); f.write(json.dumps(r) + '\n')
            self._rebuild()
            X = np.array([r['features'] for r in runs]); y = np.array([r['force'] for r in runs])
            p, bound, S, _ = self.check_features(X)
        return dict(model_version=self.version, runs_in_model=int(self.n_runs), learned_total=len(self.learned), rebuild_seconds=round(self.rebuild_s, 2),
                    conformal_factor=round(self.doubt.q, 3), factory_factor=round(self.q_factory, 3), leave_one_out_factor=round(self.q_loo, 3),
                    on_these_runs_now=[dict(error_pct=round(float(e * 100), 1), error_bound_pct=round(float(b * 100), 1), sure=bool(b <= self.tol)) for e, b in zip(verr(p, y), bound)])

    def reset(self):
        with self.lock:
            self.learned = []
            lp = f'{self.dir}/learned.jsonl'
            if os.path.exists(lp):
                os.rename(lp, lp + f'.{int(time.time())}.bak')
            self._rebuild()
        return dict(model_version=self.version, runs_in_model=int(self.n_runs))

    def status(self):
        return dict(model_version=self.version, runs_in_model=int(self.n_runs), factory_runs=int(len(self.X0)), learned_runs=len(self.learned), tolerance_pct=self.tol * 100,
                    conformal_factor=round(self.doubt.q, 3), kriging=self.kw, signals=SIG_NAMES, kg_per_m2_at_100kmh=round(Q_KG, 3))

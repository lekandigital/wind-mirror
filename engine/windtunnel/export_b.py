"""Model B for the browser: one JSON object (small arrays as lists, the solver-run store as base64 float32).
Usage: python export_b.py <state_dir> <out.json> [parity_cases.json]"""
import sys, json, base64
import numpy as np
import geom as G


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a, dtype='<f4').tobytes()).decode()


def export(E):
    m, d = E.model, E.doubt
    r = lambda a: [float(f'{x:.9g}') for x in np.asarray(a, float).ravel()]
    return dict(kind='B', version=E.version, n_runs=int(E.n_runs), names=G.NAMES, tol=E.tol, alpha=E.alpha,
                full_mu=r(m.full.mu), full_sd=r(m.full.sd), full_W=r(m.full.W), full_Ainv=r(m.full.Ainv),
                glob_mu=r(m.glob.mu), glob_sd=r(m.glob.sd), glob_W=r(m.glob.W),
                parts_mu=r(m.parts.mu), parts_sd=r(m.parts.sd), parts_W=r(m.parts.W),
                ell=m.gp.ell, noise=m.gp.noise, k=m.gp.k, gp_scale=r(m.gp.scale), use_gp=bool(m.use_gp),
                N=int(len(m.Za)), Za=b64(m.Za), res=b64(m.res), loo=b64(m.loo_err),
                doubt_w=r(d.w), doubt_q=float(d.q), doubt_s0=float(getattr(d, 's0', 0.0)), doubt_use=[int(u) for u in d.use], q_factory=float(E.q_factory))


if __name__ == '__main__':
    from engine import Engine
    import sample2, bodies as B
    E = Engine(sys.argv[1])
    json.dump(export(E), open(sys.argv[2], 'w'), separators=(',', ':'))
    print('wrote', sys.argv[2], 'runs', E.n_runs)
    if len(sys.argv) > 3:
        rng = np.random.default_rng(11); cases = []
        fams = list(sample2.FAMILIES)
        for i in range(80):
            pose, fam = sample2.sample(rng, fams[i % len(fams)])
            body = B.sample_shape(rng) if i % 2 else None
            X = G.features(pose, body)
            p, bound, S, parts = E.check_features(X)
            cases.append(dict(family=fam, pose=B.pose_to_list(pose), has_lh='lh' in pose, body=body, features=X.tolist(), force=p[0].tolist(), bound=float(bound[0]), signals=S[0].tolist(), sure=bool(bound[0] <= E.tol)))
        json.dump(cases, open(sys.argv[3], 'w'))
        print('wrote', len(cases), 'parity cases')

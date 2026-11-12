"""The trust-layer experiment.

Train small models that predict a posed body's drag area from its pose, then test whether three cheap signals
(disagreement between two models, distance from the training data, a mirror-symmetry residual) tell us in
advance which answers are wrong -- on held-out poses, on pose families never trained on, and on a real
performer's tracked clip. Everything here runs on CPU.

Usage: python train.py <poses.jsonl> <out_dir> [clip_forces.jsonl] [clip_poses_30fps.json]
"""
import sys, json, os, time
import numpy as np
import torch

torch.set_num_threads(8)
SWAP = [0, 1, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10]          # joint order: neck head shL shR elL elR wrL wrR knL knR anL anR


def mirror(feat):
    f = np.asarray(feat, float).copy()
    J = f[..., :36].reshape(f.shape[:-1] + (12, 3))[..., SWAP, :].copy()
    J[..., 1] *= -1
    f[..., :36] = J.reshape(f.shape[:-1] + (36,))
    return f


def force_vec(r):
    """[drag, lift, side] force areas in m^2 (force divided by dynamic pressure), blockage-corrected."""
    F = np.array(r['F_parts'], float).sum(0) * r['corr']
    return [F[0], F[2], F[1]]


TOL = float(os.environ.get('SL_TOL', '0.10'))          # the gate's error tolerance: accepted answers should be within this fraction of the solver's
CAP = float(os.environ.get('SL_CAP', '1.0'))           # never answer a pose whose doubt is above this. 1.0 = the 90th percentile of each signal among familiar calibration poses.
EXTRA = os.environ.get('SL_EXTRA', '1') == '1'   # include the side and top shadow areas as inputs. Read once, at import, so every script (train, learn, eval, check) agrees.


def row_features(r):
    import bodies as B
    if EXTRA:
        return B.full_features(B.pose_from_list(r['pose']), r['area_m2'])
    return list(r['feat']) + [r['area_m2']]


def load(path):
    R = [json.loads(l) for l in open(path)]
    X = np.array([row_features(r) for r in R], float)
    y = np.array([force_vec(r) for r in R], float)          # (N, 3)
    return R, X, y


MIRROR_SIGN = np.array([1.0, 1.0, -1.0])                     # mirroring a pose left-right flips only the side force


def verr(p, y):
    """Error of a predicted force vector, as a fraction of the true force's size."""
    return np.linalg.norm(p - y, axis=-1) / np.linalg.norm(y, axis=-1)


class Net(torch.nn.Module):
    def __init__(self, d, w=128):
        super().__init__()
        self.f = torch.nn.Sequential(torch.nn.Linear(d, w), torch.nn.SiLU(), torch.nn.Linear(w, w), torch.nn.SiLU(), torch.nn.Linear(w, 3))

    def forward(self, x):
        return self.f(x)


def fit(X, y, seed, mu, sd, steps=2500, aug=True, boot=True):
    """Predict the three force coefficients (force area / frontal area); the caller multiplies the area back."""
    g = torch.Generator().manual_seed(seed)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(X), len(X)) if boot else np.arange(len(X))
    Xa, ya = X[idx], y[idx]
    if aug:
        Xm = Xa.copy(); Xm[:, :37] = mirror(Xa[:, :37])
        Xa, ya = np.concatenate([Xa, Xm]), np.concatenate([ya, ya * MIRROR_SIGN])
    cd = ya / Xa[:, -1:]
    xt = torch.tensor((Xa - mu) / sd, dtype=torch.float32)
    yt = torch.tensor(cd, dtype=torch.float32)
    net = Net(X.shape[1])
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    for s in range(steps):
        b = torch.randint(0, len(xt), (min(256, len(xt)),), generator=g)
        loss = torch.nn.functional.smooth_l1_loss(net(xt[b]), yt[b], beta=0.05)
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
    return net


def predict(nets, X, mu, sd):
    with torch.no_grad():
        xt = torch.tensor((X - mu) / sd, dtype=torch.float32)
        return np.stack([n(xt).numpy() for n in nets]) * X[:, -1][None, :, None]          # (M, N, 3) force areas


def knn_dist(Xq, Xtr, mu, sd, k=5):
    a = (Xq - mu) / sd; b = (Xtr - mu) / sd
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
    d.sort(axis=1)
    return d[:, :k].mean(1)


def signals(nets, X, Xtr_all, mu, sd):
    P = predict(nets, X, mu, sd)
    mean = P.mean(0)
    size = np.linalg.norm(mean, axis=-1)
    disagree = np.linalg.norm(P[0] - P[1], axis=-1) / size if len(nets) == 2 else np.linalg.norm(P.std(0), axis=-1) / size
    Xm = X.copy(); Xm[:, :37] = mirror(X[:, :37])
    sym = np.linalg.norm(predict(nets, Xm, mu, sd).mean(0) * MIRROR_SIGN - mean, axis=-1) / size
    Xtr2 = np.concatenate([Xtr_all, np.concatenate([mirror(Xtr_all[:, :37]), Xtr_all[:, 37:]], 1)])   # areas are mirror-invariant
    dist = knn_dist(X, Xtr2, mu, sd)
    return mean, dict(disagree=disagree, dist=dist, sym=sym)


def pick_tau(doubt_ca, err_ca, tol=0.05, keep=0.95, min_n=6):
    """Largest doubt threshold for which at least `keep` of the accepted calibration answers are within `tol` of the solver.
    Returns -1.0 (the gate stays shut) if no threshold with at least `min_n` accepted answers qualifies."""
    order = np.argsort(doubt_ca)
    for j in range(len(order), min_n - 1, -1):
        if np.mean(err_ca[order[:j]] <= tol) >= keep:
            return min(float(doubt_ca[order[j - 1]]), CAP)
    return -1.0


def auroc(score, bad):
    bad = np.asarray(bad, bool)
    if bad.sum() == 0 or (~bad).sum() == 0:
        return float('nan')
    r = np.argsort(np.argsort(score)) + 1
    return float((r[bad].sum() - bad.sum() * (bad.sum() + 1) / 2) / (bad.sum() * (~bad).sum()))


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    R, X, y = load(path)
    split = np.array([r['split'] for r in R]); fam = np.array([r['family'] for r in R])
    rng = np.random.default_rng(0)
    iin = np.where(split == 'in')[0]; rng.shuffle(iin)
    n_test = max(8, len(iin) // 5); n_cal = max(8, len(iin) // 5)
    te, ca, tr = iin[:n_test], iin[n_test:n_test + n_cal], iin[n_test + n_cal:]
    ood = np.where(split == 'ood')[0]
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
    S = dict(n_total=len(R), n_train=len(tr), n_cal=len(ca), n_test=len(te), n_ood=len(ood), n_features=int(X.shape[1]), extra_area_features=bool(EXTRA))
    noise = np.array([abs(r['CdA_halves'][0] - r['CdA_halves'][1]) / r['CdA'] for r in R])
    S['solver_half_to_half_diff_median_pct'] = float(np.median(noise) * 100)
    S['solver_seconds_median'] = float(np.median([r['seconds'] for r in R]))

    # baseline: frontal area times three constants (the rule of thumb a model has to beat)
    cd0 = np.median(y[tr] / X[tr, -1:], axis=0)
    base = cd0[None, :] * X[:, -1:]
    drag_err = lambda p, idx: np.abs(p[idx, 0] - y[idx, 0]) / y[idx, 0]
    S['baseline_area_times_const'] = dict(coeffs_drag_lift_side=cd0.tolist(),
                                          test_drag_err_pct=float(drag_err(base, te).mean() * 100), test_vector_err_pct=float(verr(base[te], y[te]).mean() * 100),
                                          ood_drag_err_pct=float(drag_err(base, ood).mean() * 100) if len(ood) else None,
                                          ood_vector_err_pct=float(verr(base[ood], y[ood]).mean() * 100) if len(ood) else None)

    # the pair of models (the product's "two models"), plus a 5-model ensemble for reference
    t0 = time.time()
    nets = [fit(X[tr], y[tr], s, mu, sd) for s in (1, 2, 3, 4, 5)]
    S['train_seconds_5_models'] = round(time.time() - t0, 1)
    pair = nets[:2]
    mean, sig = signals(pair, X, X[tr], mu, sd)
    err = verr(mean, y)                                    # the error used everywhere below: whole force vector
    derr = np.abs(mean[:, 0] - y[:, 0]) / y[:, 0]          # drag alone, for reference
    S['model_pair'] = dict(test_vector_err_pct=float(err[te].mean() * 100), test_vector_err_p90_pct=float(np.percentile(err[te], 90) * 100),
                           test_drag_err_pct=float(derr[te].mean() * 100), test_lift_abs_err_m2=float(np.abs(mean[te, 1] - y[te, 1]).mean()),
                           cal_vector_err_pct=float(err[ca].mean() * 100),
                           ood_vector_err_pct=float(err[ood].mean() * 100) if len(ood) else None,
                           ood_drag_err_pct=float(derr[ood].mean() * 100) if len(ood) else None,
                           ood_by_family={f: dict(n=int((fam[ood] == f).sum()), vector_err_pct=float(err[ood][fam[ood] == f].mean() * 100),
                                                  drag_err_pct=float(derr[ood][fam[ood] == f].mean() * 100)) for f in sorted(set(fam[ood]))})
    mean5, _ = signals(nets, X, X[tr], mu, sd)
    S['model_5'] = dict(test_vector_err_pct=float(verr(mean5, y)[te].mean() * 100))
    S['target_ranges_test'] = dict(drag_m2=[float(y[te, 0].min()), float(y[te, 0].max())], lift_m2=[float(y[te, 1].min()), float(y[te, 1].max())],
                                   side_m2=[float(y[te, 2].min()), float(y[te, 2].max())])

    # inference speed (one pose, both models + all three signals' model calls), CPU single thread
    torch.set_num_threads(1)
    x1 = torch.tensor(((X[:1] - mu) / sd), dtype=torch.float32)
    with torch.no_grad():
        for _ in range(200): pair[0](x1)
        t0 = time.perf_counter()
        for _ in range(2000): pair[0](x1); pair[1](x1)
        S['inference_ms_per_check_cpu_1thread'] = (time.perf_counter() - t0) / 2000 * 1000
        xb = torch.tensor(np.repeat((X[:1] - mu) / sd, 1000, 0), dtype=torch.float32)
        t0 = time.perf_counter()
        for _ in range(50): pair[0](xb); pair[1](xb)
        S['inference_ms_per_1000_checks_cpu_1thread'] = (time.perf_counter() - t0) / 50 * 1000
    torch.set_num_threads(8)

    # one trust score: each signal scaled by its 90th percentile on the calibration set, then the max
    scale = {k: np.percentile(v[ca], 90) + 1e-9 for k, v in sig.items()}
    doubt = np.max(np.stack([sig[k] / scale[k] for k in sig]), 0)
    ev = np.concatenate([te, ood])
    S['signal_quality_on_test_plus_ood'] = {}
    for k, v in list(sig.items()) + [('combined', doubt)]:
        S['signal_quality_on_test_plus_ood'][k] = dict(spearman_with_error=spearman(v[ev], err[ev]),
                                                       auroc_err_gt_5pct=auroc(v[ev], err[ev] > 0.05), auroc_err_gt_10pct=auroc(v[ev], err[ev] > 0.10))
    # threshold chosen on the calibration set only (rule in pick_tau): 95% of accepted calibration answers within 5% of the solver
    tau = pick_tau(doubt[ca], err[ca], TOL)
    S['tau'] = tau
    S['gate_tolerance'] = TOL
    S['gate_by_tolerance'] = {}
    for tol in (0.05, 0.10):
        t_ = pick_tau(doubt[ca], err[ca], tol)
        a_te, a_ood = doubt[te] <= t_, doubt[ood] <= t_
        S['gate_by_tolerance'][f'{int(tol * 100)}pct'] = dict(
            tau=t_, test_answered_instantly_pct=float(a_te.mean() * 100),
            test_err_of_answered_mean_pct=float(err[te][a_te].mean() * 100) if a_te.any() else None,
            test_err_of_answered_max_pct=float(err[te][a_te].max() * 100) if a_te.any() else None,
            test_answered_within_tol_pct=float(np.mean(err[te][a_te] <= tol) * 100) if a_te.any() else None,
            never_seen_answered_instantly_pct=float(a_ood.mean() * 100) if len(ood) else None,
            never_seen_let_through=int(a_ood.sum()) if len(ood) else None,
            never_seen_let_through_worst_err_pct=float(err[ood][a_ood].max() * 100) if len(ood) and a_ood.any() else None)
    def gate(idx):
        a = doubt[idx] <= tau
        return dict(n=int(len(idx)), answered_instantly_pct=float(a.mean() * 100),
                    err_of_answered_mean_pct=float(err[idx][a].mean() * 100) if a.any() else None,
                    err_of_answered_p95_pct=float(np.percentile(err[idx][a], 95) * 100) if a.any() else None,
                    answered_within_5pct_pct=float(np.mean(err[idx][a] <= 0.05) * 100) if a.any() else None,
                    answered_within_tol_pct=float(np.mean(err[idx][a] <= TOL) * 100) if a.any() else None,
                    err_of_answered_max_pct=float(err[idx][a].max() * 100) if a.any() else None,
                    err_of_escalated_mean_pct=float(err[idx][~a].mean() * 100) if (~a).any() else None,
                    err_if_no_gate_mean_pct=float(err[idx].mean() * 100), err_if_no_gate_max_pct=float(err[idx].max() * 100),
                    bad_answers_gt10pct_total=int((err[idx] > 0.10).sum()), bad_answers_gt10pct_let_through=int(((err[idx] > 0.10) & a).sum()))
    S['gate'] = dict(test=gate(te), ood=gate(ood) if len(ood) else None, **{f'ood_{f}': gate(ood[fam[ood] == f]) for f in sorted(set(fam[ood]))})

    # learning curve (pair, mirror augmentation on)
    S['learning_curve'] = []
    for n in [m for m in (25, 50, 100, 150, 200, 300, 400, 600, 800) if m < len(tr)] + [len(tr)]:
        if n <= len(tr):
            mu_n, sd_n = X[tr[:n]].mean(0), X[tr[:n]].std(0) + 1e-6
            p = predict([fit(X[tr[:n]], y[tr[:n]], s, mu_n, sd_n) for s in (1, 2)], X[te], mu_n, sd_n).mean(0)
            S['learning_curve'].append(dict(n=n, test_vector_err_pct=float(verr(p, y[te]).mean() * 100),
                                            test_drag_err_pct=float((np.abs(p[:, 0] - y[te, 0]) / y[te, 0]).mean() * 100)))

    # the loop: send the escalated out-of-distribution poses of one family to the solver, add half to training, retrain, re-test on the rest
    S['flywheel'] = {}
    for f in sorted(set(fam[ood])):
        idx = ood[fam[ood] == f]
        if len(idx) < 12:
            continue
        add, hold = idx[:len(idx) // 2], idx[len(idx) // 2:]
        tr2 = np.concatenate([tr, add])
        mu2, sd2 = X[tr2].mean(0), X[tr2].std(0) + 1e-6
        nets2 = [fit(X[tr2], y[tr2], s, mu2, sd2) for s in (1, 2)]
        m2, sig2 = signals(nets2, X, X[tr2], mu2, sd2)
        e2 = verr(m2, y)
        sc2 = {k: np.percentile(v[ca], 90) + 1e-9 for k, v in sig2.items()}
        d2 = np.max(np.stack([sig2[k] / sc2[k] for k in sig2]), 0)
        S['flywheel'][f] = dict(solver_runs_added=int(len(add)), held_out=int(len(hold)),
                                before=dict(mape_pct=float(err[hold].mean() * 100), answered_instantly_pct=float((doubt[hold] <= tau).mean() * 100)),
                                after=dict(mape_pct=float(e2[hold].mean() * 100), answered_instantly_pct=float((d2[hold] <= tau).mean() * 100),
                                           err_of_answered_mean_pct=float(e2[hold][d2[hold] <= tau].mean() * 100) if (d2[hold] <= tau).any() else None))

    np.savez(f'{out}/eval.npz', y=y, pred=mean, err=err, drag_err=derr, base=base, doubt=doubt, te=te, ca=ca, tr=tr, ood=ood, fam=fam, area=X[:, -1],
             **{'sig_' + k: v for k, v in sig.items()})
    torch.save(dict(nets=[n.state_dict() for n in pair], mu=mu, sd=sd, scale=scale, tau=tau, Xtr=X[tr], cd0=cd0, extra=bool(EXTRA)), f'{out}/pair.pt')

    # the performer's real clip
    if len(sys.argv) > 3 and os.path.exists(sys.argv[3]):
        C = [json.loads(l) for l in open(sys.argv[3])]
        Xc = np.array([row_features(c) for c in C], float); yc = np.array([force_vec(c) for c in C])
        mc, sc = signals(pair, Xc, X[tr], mu, sd)
        dc = np.max(np.stack([sc[k] / scale[k] for k in sc]), 0)
        ec = verr(mc, yc)
        bc = cd0[None, :] * Xc[:, -1:]
        a = dc <= tau
        S['performer_clip'] = dict(n_solver_frames=len(C), vector_err_pct=float(ec.mean() * 100), max_vector_err_pct=float(ec.max() * 100),
                                   drag_err_pct=float((np.abs(mc[:, 0] - yc[:, 0]) / yc[:, 0]).mean() * 100),
                                   baseline_vector_err_pct=float(verr(bc, yc).mean() * 100),
                                   baseline_drag_err_pct=float((np.abs(bc[:, 0] - yc[:, 0]) / yc[:, 0]).mean() * 100),
                                   answered_instantly_pct=float(a.mean() * 100), err_of_answered_mean_pct=float(ec[a].mean() * 100) if a.any() else None,
                                   err_of_answered_max_pct=float(ec[a].max() * 100) if a.any() else None,
                                   err_of_escalated_mean_pct=float(ec[~a].mean() * 100) if (~a).any() else None,
                                   spearman_doubt_vs_error=spearman(dc, ec), drag_min_m2=float(yc[:, 0].min()), drag_max_m2=float(yc[:, 0].max()),
                                   lift_min_m2=float(yc[:, 1].min()), lift_max_m2=float(yc[:, 1].max()))
        np.savez(f'{out}/clip_eval.npz', t=np.array([c['t'] for c in C]), frame=np.array([c['frame'] for c in C]), y=yc, pred=mc, doubt=dc, err=ec,
                 area=Xc[:, -1], parts=np.array([np.array(c['F_parts'])[:, 0] * c['corr'] for c in C]))
    json.dump(S, open(f'{out}/summary.json', 'w'), indent=1)
    print(json.dumps(S, indent=1))


if __name__ == '__main__':
    main()

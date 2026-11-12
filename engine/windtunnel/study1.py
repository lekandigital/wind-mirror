"""Study 1 (pitch-night data only): do wind's-eye geometric inputs beat joint-coordinate inputs, in and out of distribution?

Same training split as the pitch (150-180 random 'familiar' poses). Tested on held-out familiar poses, on the four pose
families never trained on, and on the performer's tracked clips (never trained on here).
Usage: python study1.py
"""
import json, sys, time
import numpy as np
import torch
import data as D, geom as G

torch.set_num_threads(8)


def verr(p, y):
    return np.linalg.norm(p - y, axis=-1) / np.linalg.norm(y, axis=-1)


class Net(torch.nn.Module):
    def __init__(self, d, w=96, out=3):
        super().__init__()
        self.f = torch.nn.Sequential(torch.nn.Linear(d, w), torch.nn.SiLU(), torch.nn.Linear(w, w), torch.nn.SiLU(), torch.nn.Linear(w, out))

    def forward(self, x):
        return self.f(x)


def fit_mlp(X, Y, seed, steps=2500, wd=1e-3, w=96, boot=True):
    """X standardised inputs, Y targets (already scaled). Returns a net."""
    g = torch.Generator().manual_seed(seed); torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(X), len(X)) if boot else np.arange(len(X))
    xt = torch.tensor(X[idx], dtype=torch.float32); yt = torch.tensor(Y[idx], dtype=torch.float32)
    net = Net(X.shape[1], w, Y.shape[1])
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    for s in range(steps):
        b = torch.randint(0, len(xt), (min(256, len(xt)),), generator=g)
        loss = torch.nn.functional.smooth_l1_loss(net(xt[b]), yt[b], beta=0.05)
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
    return net


def ens_predict(nets, X):
    with torch.no_grad():
        xt = torch.tensor(X, dtype=torch.float32)
        return np.stack([n(xt).numpy() for n in nets])


MS = np.array([1.0, 1.0, -1.0])       # mirroring flips the side force only


def ridge_fit(X, Y, lam):
    A = X.T @ X + lam * np.eye(X.shape[1])
    return np.linalg.solve(A, X.T @ Y)


def ridge_cv(X, Y, lams=(1e-3, 1e-2, 3e-2, 0.1, 0.3, 1, 3, 10, 30)):
    """Leave-one-out choice of the ridge strength (closed form)."""
    best = None
    for lam in lams:
        A = X.T @ X + lam * np.eye(X.shape[1])
        Hm = X @ np.linalg.solve(A, X.T)
        res = (Y - Hm @ Y) / (1 - np.diag(Hm))[:, None]
        s = float((res ** 2).mean())
        if best is None or s < best[0]:
            best = (s, lam)
    return best[1]


def main():
    P = D.load('../../out/pitch/poses_v1.jsonl', '../../out/pitch/feat_cache.npz')
    clips = {c: D.load(f'../../out/pitch/clip_{c}.jsonl', '../../out/pitch/feat_cache.npz', source='clip_' + c) for c in ('fly', 'puppet', 'row')}
    turn_frames = {450, 465, 510, 525, 540}                     # the side-on frames of the Puppet clip (pitch loop report)
    rng = np.random.default_rng(0)
    iin = np.where(P['split'] == 'in')[0]; rng.shuffle(iin)
    n = len(iin) // 5
    te, ca, tr = iin[:n], iin[n:2 * n], iin[2 * n:]
    ood = np.where(P['split'] == 'ood')[0]
    y = P['y']
    sets = dict(test=(P, te), **{'ood_' + f: (P, ood[P['fam'][ood] == f]) for f in sorted(set(P['fam'][ood]))},
                fly=(clips['fly'], np.arange(clips['fly']['n'])))
    pu, ro = clips['puppet'], clips['row']
    isturn = np.array([r['frame'] in turn_frames for r in pu['R']])
    sets['puppet_ordinary'] = (pu, np.where(~isturn)[0]); sets['puppet_turn'] = (pu, np.where(isturn)[0]); sets['row'] = (ro, np.arange(ro['n']))
    print('train', len(tr), 'cal', len(ca), 'test', len(te), 'ood', len(ood), {k: len(v[1]) for k, v in sets.items()})
    results = {}

    def report(name, predict):
        row = {}
        for k, (Dset, idx) in sets.items():
            p = predict(Dset, idx)
            e = verr(p, Dset['y'][idx])
            row[k] = round(float(e.mean() * 100), 1)
            row[k + '_drag'] = round(float((np.abs(p[:, 0] - Dset['y'][idx, 0]) / Dset['y'][idx, 0]).mean() * 100), 1)
        results[name] = row
        keys = list(sets)
        print(f'{name:28s} ' + ' '.join(f'{k}={row[k]:5.1f}' for k in keys), flush=True)

    # 0. rule of thumb: area times three constants
    cd0 = np.median(y[tr] / P['X'][tr, :1], axis=0)
    report('area x const', lambda Dset, idx: cd0[None] * Dset['X'][idx, :1])

    # 1. the pitch model: joint coordinates -> coefficients, mirror-augmented MLPs
    import train as T
    J = P['J']; mu, sd = J[tr].mean(0), J[tr].std(0) + 1e-6
    nets = [T.fit(J[tr], y[tr], s, mu, sd) for s in (1, 2, 3, 4, 5)]
    report('pitch: joints MLP x5', lambda Dset, idx: T.predict(nets, Dset['J'][idx], mu, sd).mean(0))

    # 2. geometric features, linear (ridge), force areas directly; mirror-augmented
    def geo_xy(Dset, idx, cols=None):
        X = Dset['X'][idx]; Y = Dset['y'][idx]
        Xa = np.concatenate([X, G.mirror(X)]); Ya = np.concatenate([Y, Y * MS])
        return (Xa if cols is None else Xa[:, cols]), Ya
    for label, cols in (('geo global', list(range(G.NG))), ('geo all', list(range(len(G.NAMES))))):
        Xa, Ya = geo_xy(P, tr, cols)
        m_, s_ = Xa.mean(0), Xa.std(0) + 1e-9
        Z = np.concatenate([(Xa - m_) / s_, np.ones((len(Xa), 1))], 1)
        lam = ridge_cv(Z, Ya)
        W = ridge_fit(Z, Ya, lam)
        pr = lambda Dset, idx, cols=cols, m_=m_, s_=s_, W=W: np.concatenate([(Dset['X'][idx][:, cols] - m_) / s_, np.ones((len(idx), 1))], 1) @ W
        report(f'ridge, {label} (lam {lam})', pr)

        # 3. MLP ensemble on the same inputs, predicting force coefficients (force / frontal area)
        Ca = Ya / Xa[:, :1]
        Zs = (Xa - m_) / s_
        for w_, wd in ((96, 1e-3), (96, 3e-2)):
            nets_g = [fit_mlp(Zs, Ca, s, w=w_, wd=wd) for s in (1, 2, 3, 4, 5)]
            def pm(Dset, idx, cols=cols, m_=m_, s_=s_, nets_g=nets_g):
                X = Dset['X'][idx][:, cols]
                return ens_predict(nets_g, (X - m_) / s_).mean(0) * X[:, :1]
            report(f'MLP x5, {label}, wd {wd}', pm)

        # 4. ridge prior + MLP on the residual coefficient
        res = (Ya - Z @ W) / Xa[:, :1]
        nets_r = [fit_mlp(Zs, res, s, wd=3e-2) for s in (1, 2, 3, 4, 5)]
        def pmr(Dset, idx, cols=cols, m_=m_, s_=s_, W=W, nets_r=nets_r):
            X = Dset['X'][idx][:, cols]; Zq = (X - m_) / s_
            return np.concatenate([Zq, np.ones((len(X), 1))], 1) @ W + ens_predict(nets_r, Zq).mean(0) * X[:, :1]
        report(f'ridge + MLP residual, {label}', pmr)
    json.dump(results, open('../../out/study1.json', 'w'), indent=1)


if __name__ == '__main__':
    main()

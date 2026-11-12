"""The surrogate and its doubt score. NumPy only, so the same arithmetic can be ported to the browser.

Model      force areas (drag, lift, side) = linear trend in the wind's-eye features (ridge, mirror-augmented)
           + optional Gaussian-process correction on the trend's residuals (added in fit(..., gp=True)).
Signals    lev   leverage: how far the features sit from the training cloud, in the model's own metric
           knn   mean distance to the 5 nearest training bodies in standardised feature space
           dis   disagreement between two models that see different inputs (global features only vs all features)
           par   physics check: per-part forces predicted separately must add up to the whole-body force
Doubt      sigma(x) = exp(b0 + b . log(signals)) is fitted to predict the size of the relative force error;
           the bound shown to the user is q * sigma(x), with q the conformal quantile that makes
           P(error <= q * sigma) >= 1 - alpha on held-out data. "Sure" means bound <= tolerance.
"""
import numpy as np
import geom as G

MS = np.array([1.0, 1.0, -1.0])            # mirroring a body left-right flips only the side force
SIG_NAMES = ['lev', 'knn', 'dis', 'par']
GLOBAL = list(range(G.NG))


def verr(p, y):
    return np.linalg.norm(p - y, axis=-1) / np.linalg.norm(y, axis=-1)


def _ridge_cv(Z, Y, lams=(1e-3, 1e-2, 3e-2, 0.1, 0.3, 1, 3, 10, 30)):
    best = None
    ZtZ = Z.T @ Z
    for lam in lams:
        A = ZtZ + lam * np.eye(Z.shape[1])
        S = np.linalg.solve(A, Z.T)
        hd = np.einsum('ij,ji->i', Z, S)
        res = (Y - Z @ (S @ Y)) / (1 - hd)[:, None]
        s = float((res ** 2).mean())
        if best is None or s < best[0]:
            best = (s, lam)
    return best[1]


class Linear:
    """Ridge regression on standardised features with a bias column, trained on the data and its mirror image."""

    def __init__(self, X, Y, cols=None, sign=None, lam=None):
        self.cols = list(range(X.shape[1])) if cols is None else list(cols)
        Xa = np.concatenate([X, G.mirror(X)])[:, self.cols]
        Ya = np.concatenate([Y, Y * (MS if sign is None else sign)])
        self.mu, self.sd = Xa.mean(0), Xa.std(0) + 1e-9
        Z = self._z(Xa, raw=False)
        self.lam = _ridge_cv(Z, Ya) if lam is None else lam
        self.Ainv = np.linalg.inv(Z.T @ Z + self.lam * np.eye(Z.shape[1]))
        self.W = self.Ainv @ Z.T @ Ya
        self.Ztrain = Z[:len(X)]

    def _z(self, X, raw=True):
        X = X[:, self.cols] if raw else X
        return np.concatenate([(X - self.mu) / self.sd, np.ones((len(X), 1))], 1)

    def predict(self, X):
        return self._z(X) @ self.W

    def leverage(self, X):
        Z = self._z(X)
        return np.einsum('ij,jk,ik->i', Z, self.Ainv, Z)


def part_sign():
    """Sign pattern for mirroring the 10 x 3 per-part force table (parts are swapped separately)."""
    return np.tile(MS, len(G.PART_SWAP))


def mirror_parts(Yp):
    """Yp: (N, 10, 3) per-part [drag, lift, side] -> the mirrored body's table."""
    return Yp[:, G.PART_SWAP, :] * MS


class PartsLinear:
    """Per-part forces (10 x 3) from all features; used for the 'parts must add up to the whole' check and for display."""

    def __init__(self, X, Yp, lam=None):
        Xa = np.concatenate([X, G.mirror(X)])
        Ya = np.concatenate([Yp, mirror_parts(Yp)]).reshape(2 * len(X), -1)
        self.mu, self.sd = Xa.mean(0), Xa.std(0) + 1e-9
        Z = np.concatenate([(Xa - self.mu) / self.sd, np.ones((len(Xa), 1))], 1)
        self.lam = _ridge_cv(Z, Ya) if lam is None else lam
        self.W = np.linalg.solve(Z.T @ Z + self.lam * np.eye(Z.shape[1]), Z.T @ Ya)

    def predict(self, X):
        Z = np.concatenate([(X - self.mu) / self.sd, np.ones((len(X), 1))], 1)
        return (Z @ self.W).reshape(len(X), -1, 3)


class Surrogate:
    def __init__(self, X, Y, Yp=None, k=5, gp=False):
        self.full = Linear(X, Y)
        self.glob = Linear(X, Y, cols=GLOBAL)
        self.parts = PartsLinear(X, Yp) if Yp is not None else None
        Xa = np.concatenate([X, G.mirror(X)])
        self.Zref = (Xa - self.full.mu) / self.full.sd
        self.k = k
        self.gp = None
        if gp:
            from gp import ResidualGP
            self.gp = ResidualGP(self.Zref, np.concatenate([Y, Y * MS]) - self.full.predict(Xa), np.concatenate([X[:, 0], X[:, 0]]))

    def predict(self, X):
        p = self.full.predict(X)
        if self.gp is not None:
            p = p + self.gp.mean((X - self.full.mu) / self.full.sd, X[:, 0])
        return p

    def signals(self, X, exclude_self=False):
        """exclude_self: X are the training rows themselves (in order), so skip each row's zero distance to itself."""
        p = self.predict(X)
        size = np.linalg.norm(p, axis=-1) + 1e-9
        lev = self.full.leverage(X)
        Zq = (X - self.full.mu) / self.full.sd
        d2 = (Zq ** 2).sum(1)[:, None] - 2 * Zq @ self.Zref.T + (self.Zref ** 2).sum(1)[None]
        d = np.sqrt(np.maximum(d2, 0)); d.sort(axis=1)
        knn = d[:, 1:self.k + 1].mean(1) if exclude_self else d[:, :self.k].mean(1)
        knn = knn / np.sqrt(X.shape[1])
        dis = np.linalg.norm(p - self.glob.predict(X), axis=-1) / size
        par = np.linalg.norm(self.parts.predict(X).sum(1) - p, axis=-1) / size if self.parts is not None else np.zeros(len(X))
        return p, np.stack([lev, knn, dis, par], 1)


class Doubt:
    """sigma(x) from the signals, and the conformal factor q."""

    def __init__(self, S, err, use=(0, 1, 2, 3), alpha=0.10, floor=0.01, fit_floor=False):
        self.use = list(use); self.alpha = alpha; self.floor = floor; self.s0 = 0.0
        L = self._l(S)
        A = np.concatenate([L, np.ones((len(L), 1))], 1)
        t = np.log(np.maximum(err, floor))
        w, *_ = np.linalg.lstsq(A, t, rcond=None)
        w[:-1] = np.maximum(w[:-1], 0.0)                     # a larger signal may never lower the doubt
        w[-1] = float(np.mean(t - L @ w[:-1]))
        self.w = w
        self.q = 1.0
        if fit_floor:
            # A floor under sigma: however familiar the body, the answer is never better than the solver's own noise plus
            # the model's bias. Chosen by the pinball loss of the resulting (1 - alpha) bound, a proper score for a quantile.
            best = None
            for s0 in (0.0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05):
                self.s0 = s0
                b = self.conformal(S, err, alpha) * self.sigma(S)
                loss = float(np.mean(np.where(err > b, (1 - alpha) * (err - b), alpha * (b - err))))
                if best is None or loss < best[0]:
                    best = (loss, s0)
            self.s0 = best[1]
        self.q = self.conformal(S, err, alpha)

    def _l(self, S):
        return np.log(np.maximum(S[:, self.use], 1e-6))

    def sigma(self, S):
        base = np.exp(self._l(S) @ self.w[:-1] + self.w[-1])
        return np.sqrt(base ** 2 + getattr(self, 's0', 0.0) ** 2)

    def conformal(self, S, err, alpha):
        r = np.sort(err / self.sigma(S))
        n = len(r)
        j = min(int(np.ceil((n + 1) * (1 - alpha))) - 1, n - 1)
        return float(r[j])

    def bound(self, S):
        return self.q * self.sigma(S)


def auroc(score, bad):
    bad = np.asarray(bad, bool)
    if bad.sum() == 0 or (~bad).sum() == 0:
        return float('nan')
    r = np.argsort(np.argsort(score)) + 1
    return float((r[bad].sum() - bad.sum() * (bad.sum() + 1) / 2) / (bad.sum() * (~bad).sum()))

"""Model B: linear trend on the wind's-eye features + local kriging on its residuals, with six doubt signals.

  lev   leverage of the query in the linear trend
  knn   mean distance to the 5 nearest training bodies
  dis   disagreement between the global-features trend and the full trend
  par   per-part forces must add up to the whole-body force
  gsd   kriging standard deviation (1 = no nearby solver run informs this answer)
  loc   how wrong the model was, leave-one-out, on the solver runs nearest to the query (relative error)
"""
import numpy as np
import geom as G
from surrogate import Linear, PartsLinear, MS, GLOBAL, verr
from krige import LocalGP

SIG_NAMES = ['lev', 'knn', 'dis', 'par', 'gsd', 'loc']


class ModelB:
    def __init__(self, X, Y, Yp=None, ell=5.0, noise=0.1, k=40, lam=None, use_gp=True):
        n = len(X)
        self.full = Linear(X, Y, lam=lam)
        self.glob = Linear(X, Y, cols=GLOBAL)
        self.parts = PartsLinear(X, Yp) if Yp is not None else None
        Xa = np.concatenate([X, G.mirror(X)]); Ya = np.concatenate([Y, Y * MS])
        self.Za = (Xa - self.full.mu) / self.full.sd
        self.group = np.concatenate([np.arange(n), np.arange(n)])
        self.Ya = Ya
        self.res = Ya - self.full.predict(Xa)
        self.use_gp = use_gp
        self.gp = LocalGP(self.Za, self.res, self.group, ell, noise, k)
        # leave-one-run-out error of the whole model at every training point (for the 'loc' signal)
        m, _, _ = self.gp.predict(self.Za, self.group)
        p_loo = self.full.predict(Xa) + (m if use_gp else 0.0)
        self.loo_err = verr(p_loo, Ya)

    def predict(self, X):
        return self.signals(X)[0]

    def signals(self, X, kloc=8):
        X = np.atleast_2d(X)
        Zq = (X - self.full.mu) / self.full.sd
        m, gsd, _ = self.gp.predict(Zq)
        p = self.full.predict(X) + (m if self.use_gp else 0.0)
        size = np.linalg.norm(p, axis=-1) + 1e-9
        lev = self.full.leverage(X)
        d2 = np.maximum((Zq ** 2).sum(1)[:, None] - 2 * Zq @ self.Za.T + self.gp.zz[None], 0)
        idx = np.argpartition(d2, kloc - 1, axis=1)[:, :kloc]
        dn = np.sqrt(np.take_along_axis(d2, idx, 1))
        knn = np.sort(dn, 1)[:, :5].mean(1) / np.sqrt(X.shape[1])
        w = np.exp(-dn ** 2 / (2 * self.gp.ell ** 2)) + 1e-6
        loc = (w * self.loo_err[idx]).sum(1) / w.sum(1)
        dis = np.linalg.norm(self.full.predict(X) - self.glob.predict(X), axis=-1) / size
        par = np.linalg.norm(self.parts.predict(X).sum(1) - self.full.predict(X), axis=-1) / size if self.parts is not None else np.zeros(len(X))
        return p, np.stack([lev, knn, dis, par, gsd, loc], 1)

    def loo_signals(self, kloc=8):
        """Signals and errors at every training run, each computed as if that run (and its mirror image) had been left out.
        Used to re-calibrate the conformal factor after the model learns new runs. Returns (S (N, 6), err (N,)) for the N original runs."""
        n = len(self.Za) // 2
        Z = self.Za[:n]
        m, gsd, _ = self.gp.predict(Z, self.group[:n])
        A = self.full.Ainv
        Zb = np.concatenate([Z, np.ones((n, 1))], 1)
        h = np.einsum('ij,jk,ik->i', Zb, A, Zb)
        lev = h / np.maximum(1.0 - 2.0 * h, 0.05)               # leverage with the run and its mirror removed (approximate)
        d2 = np.maximum((Z ** 2).sum(1)[:, None] - 2 * Z @ self.Za.T + self.gp.zz[None], 0)
        d2 = np.where(self.group[None, :] == np.arange(n)[:, None], np.inf, d2)
        idx = np.argpartition(d2, kloc - 1, axis=1)[:, :kloc]
        dn = np.sqrt(np.take_along_axis(d2, idx, 1))
        knn = np.sort(dn, 1)[:, :5].mean(1) / np.sqrt(Z.shape[1])
        w = np.exp(-dn ** 2 / (2 * self.gp.ell ** 2)) + 1e-6
        loc = (w * self.loo_err[idx]).sum(1) / w.sum(1)
        X = Z * self.full.sd + self.full.mu
        pt = self.full.predict(X)
        p = pt + (m if self.use_gp else 0.0)
        size = np.linalg.norm(p, axis=-1) + 1e-9
        dis = np.linalg.norm(pt - self.glob.predict(X), axis=-1) / size
        par = np.linalg.norm(self.parts.predict(X).sum(1) - pt, axis=-1) / size if self.parts is not None else np.zeros(n)
        return np.stack([lev, knn, dis, par, gsd, loc], 1), self.loo_err[:n]

"""Load a saved surrogate (model_*.npz) and answer checks. NumPy only; this is the arithmetic the browser port mirrors."""
import numpy as np
import geom as G


class Model:
    def __init__(self, path):
        z = np.load(path, allow_pickle=False)
        self.z = {k: z[k] for k in z.files}
        assert list(self.z['names']) == G.NAMES, 'feature list of the saved model does not match geom.NAMES'
        self.tol = float(self.z['tol']); self.q = float(self.z['doubt_q']); self.w = self.z['doubt_w']; self.use = list(self.z['doubt_use'])
        self.k = int(self.z['k'])
        self.Zref = self.z['Zref'].astype(float)
        self._zz = (self.Zref ** 2).sum(1)

    def _lin(self, X, pre, cols=None):
        Xc = X if cols is None else X[:, cols]
        Z = np.concatenate([(Xc - self.z[pre + '_mu']) / self.z[pre + '_sd'], np.ones((len(X), 1))], 1)
        return Z, Z @ self.z[pre + '_W']

    def check(self, X):
        """X: (N, 67) wind's-eye features. Returns forces (N, 3: drag, lift, side, m^2), per-part forces (N, 10, 3),
        the four signals, the error bound (fraction of the force) and the verdict."""
        X = np.atleast_2d(np.asarray(X, float))
        Z, p = self._lin(X, 'full')
        _, pg = self._lin(X, 'glob', list(range(G.NG)))
        _, pp = self._lin(X, 'parts'); pp = pp.reshape(len(X), -1, 3)
        size = np.linalg.norm(p, axis=-1) + 1e-9
        lev = np.einsum('ij,jk,ik->i', Z, self.z['full_Ainv'], Z)
        Zq = Z[:, :-1]
        d2 = (Zq ** 2).sum(1)[:, None] - 2 * Zq @ self.Zref.T + self._zz[None]
        d = np.sqrt(np.maximum(d2, 0)); d.partition(self.k - 1, axis=1)
        knn = d[:, :self.k].mean(1) / np.sqrt(X.shape[1])
        dis = np.linalg.norm(p - pg, axis=-1) / size
        par = np.linalg.norm(pp.sum(1) - p, axis=-1) / size
        S = np.stack([lev, knn, dis, par], 1)
        sigma = np.exp(np.log(np.maximum(S[:, self.use], 1e-6)) @ self.w[:-1] + self.w[-1])
        bound = self.q * sigma
        return dict(force=p, parts=pp, signals=S, bound=bound, sure=bound <= self.tol)

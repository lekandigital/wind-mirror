"""Local kriging on the residuals of the linear trend: a Gaussian-process correction computed from the k nearest solver
runs only. NumPy; the browser port mirrors it. Adding a solver run is appending one point (and its mirror image)."""
import numpy as np


class LocalGP:
    def __init__(self, Z, R, group, ell=5.0, noise=0.1, k=40):
        """Z: (N, d) inputs; R: (N, m) residuals; group: (N,) ids (a run and its mirror image share one)."""
        self.Z = np.asarray(Z, float); self.R = np.asarray(R, float); self.group = np.asarray(group)
        self.ell, self.noise, self.k = float(ell), float(noise), int(k)
        self.scale = self.R.std(0) + 1e-9                      # prior standard deviation per output
        self.zz = (self.Z ** 2).sum(1)

    def _neigh(self, Zq, gq=None):
        d2 = (Zq ** 2).sum(1)[:, None] - 2 * Zq @ self.Z.T + self.zz[None]
        d2 = np.maximum(d2, 0)
        if gq is not None:
            d2 = np.where(self.group[None, :] == np.asarray(gq)[:, None], np.inf, d2)   # leave the query's own run (and mirror) out
        k = min(self.k, self.Z.shape[0] - 2)
        idx = np.argpartition(d2, k - 1, axis=1)[:, :k]
        return idx, np.take_along_axis(d2, idx, 1)

    def predict(self, Zq, gq=None, chunk=512):
        """Returns mean (Nq, m), sd (Nq,) as a fraction of the prior sd (1 = knows nothing here), nearest distance (Nq,)."""
        Zq = np.atleast_2d(np.asarray(Zq, float))
        mean = np.zeros((len(Zq), self.R.shape[1])); sd = np.zeros(len(Zq)); dmin = np.zeros(len(Zq))
        for s in range(0, len(Zq), chunk):
            zq = Zq[s:s + chunk]
            idx, d2 = self._neigh(zq, None if gq is None else gq[s:s + chunk])
            Zn = self.Z[idx]                                   # (n, k, d)
            dn = ((Zn[:, :, None, :] - Zn[:, None, :, :]) ** 2).sum(-1)
            K = np.exp(-dn / (2 * self.ell ** 2)) + self.noise * np.eye(idx.shape[1])[None]
            ks = np.exp(-d2 / (2 * self.ell ** 2))             # (n, k)
            sol = np.linalg.solve(K, np.concatenate([ks[..., None], self.R[idx] / self.scale], -1))
            w = sol[..., 0]
            mean[s:s + chunk] = np.einsum('nk,nkm->nm', ks, sol[..., 1:]) * self.scale
            sd[s:s + chunk] = np.sqrt(np.maximum(1.0 - (ks * w).sum(1), 0.0))
            dmin[s:s + chunk] = np.sqrt(d2.min(1))
        return mean, sd, dmin

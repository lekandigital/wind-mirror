"""The check: pose -> (drag area, doubt score, verdict). This is the function an agent would call.

Loads the two small models and the calibration written by train.py. `check_batch` answers many poses at once.
"""
import json, time
import numpy as np
import torch
import bodies as B
from train import Net, mirror, knn_dist, MIRROR_SIGN, EXTRA


class Check:
    def __init__(self, path):
        ck = torch.load(path, weights_only=False)
        self.mu, self.sd, self.scale, self.tau, self.Xtr = ck['mu'], ck['sd'], ck['scale'], ck['tau'], ck['Xtr']
        self.n_features = len(self.mu)
        want = 40 if EXTRA else 38
        if self.n_features != want:
            raise SystemExit(f'{path} was trained on {self.n_features} inputs but SL_EXTRA selects {want}. Set SL_EXTRA={"1" if self.n_features == 40 else "0"}.')
        self.nets = []
        for sdict in ck['nets']:
            n = Net(len(self.mu)); n.load_state_dict(sdict); n.eval(); self.nets.append(n)
        self.Xtr2 = np.concatenate([self.Xtr, np.concatenate([mirror(self.Xtr[:, :37]), self.Xtr[:, 37:]], 1)])

    def _pred(self, X):
        with torch.no_grad():
            xt = torch.tensor((X - self.mu) / self.sd, dtype=torch.float32)
            return np.stack([n(xt).numpy() for n in self.nets]) * X[:, -1][None, :, None]

    def check_features(self, X, with_distance=True):
        """X: (N, 40) from bodies.full_features (frontal area last). Returns dict of arrays."""
        P = self._pred(X)
        mean = P.mean(0)                                         # (N, 3): drag, lift, side force areas
        size = np.linalg.norm(mean, axis=-1)
        disagree = np.linalg.norm(P[0] - P[1], axis=-1) / size
        Xm = X.copy(); Xm[:, :37] = mirror(X[:, :37])
        sym = np.linalg.norm(self._pred(Xm).mean(0) * MIRROR_SIGN - mean, axis=-1) / size
        sig = dict(disagree=disagree / self.scale['disagree'], sym=sym / self.scale['sym'])
        if with_distance:
            dist = np.concatenate([knn_dist(X[i:i + 2000], self.Xtr2, self.mu, self.sd) for i in range(0, len(X), 2000)])
            sig['dist'] = dist / self.scale['dist']
        doubt = np.max(np.stack(list(sig.values())), 0)
        return dict(CdA=mean[:, 0], lift=mean[:, 1], side=mean[:, 2], doubt=doubt, sure=doubt <= self.tau, signals=sig)


def pose_features(pose, area_front):
    """The model's inputs for one pose, matching the SL_EXTRA setting the models were trained with."""
    return B.full_features(pose, area_front) if EXTRA else list(B.features(pose)) + [float(area_front)]


def pose_area(pose, H=64, shape=(224, 128, 128)):
    """Frontal area needs only geometry (no flow solve): rasterise the capsules as the wind sees them."""
    mask, info = B.voxelize(pose, shape, H)
    return info['area_m2']


def fast_area(pose, res=0.0137):
    """Cheaper frontal area: draw capsules into a 2D y-z image."""
    J = B.joints(pose); caps = B.capsules(J, pose)
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in caps)
    ny, nz = int(2.4 / res), int(2.6 / res)
    Y, Z = np.meshgrid((np.arange(ny) + 0.5) * res - 1.2, (np.arange(nz) + 0.5) * res, indexing='ij')
    img = np.zeros((ny, nz), bool)
    for a, b, r, _ in caps:
        A = np.array([a[1], a[2] - zmin]); Bp = np.array([b[1], b[2] - zmin]); d = Bp - A; dd = d @ d
        t = np.clip(((Y - A[0]) * d[0] + (Z - A[1]) * d[1]) / dd, 0, 1) if dd > 1e-12 else 0.0
        img |= (Y - A[0] - t * d[0]) ** 2 + (Z - A[1] - t * d[1]) ** 2 < r * r
    return img.sum() * res * res


if __name__ == '__main__':
    import sys
    ck = Check(sys.argv[1])
    for name, kw in B.NAMED.items():
        pose = B.make_pose(**kw)
        X = np.array([pose_features(pose, pose_area(pose))])
        r = ck.check_features(X)
        print(f'{name:16s} CdA={r["CdA"][0]:.3f}  doubt={r["doubt"][0]:6.2f}  {"SURE" if r["sure"][0] else "ASK SOLVER"}   ' +
              ' '.join(f'{k}={v[0]:.2f}' for k, v in r['signals'].items()))

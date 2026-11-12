"""The 'every solver run becomes training data' step: refit the two models with extra solver runs added.
Usage: learn.py <dataset.jsonl> <extra.jsonl[,more.jsonl]> <out_pair.pt>   (same split and calibration rule as train.py)"""
import sys, json, time
import numpy as np, torch
from train import load, fit, signals, verr, pick_tau, EXTRA, TOL

t0 = time.time()
R, X, y = load(sys.argv[1])
split = np.array([r['split'] for r in R])
rng = np.random.default_rng(0)
iin = np.where(split == 'in')[0]; rng.shuffle(iin)
n = max(8, len(iin) // 5)
te, ca, tr = iin[:n], iin[n:2 * n], iin[2 * n:]
Xe, ye = [], []
for p in sys.argv[2].split(','):
    _, a, b = load(p); Xe.append(a); ye.append(b)
Xe, ye = np.concatenate(Xe), np.concatenate(ye)
Xt, yt = np.concatenate([X[tr], Xe]), np.concatenate([y[tr], ye])
mu, sd = Xt.mean(0), Xt.std(0) + 1e-6
nets = [fit(Xt, yt, s, mu, sd) for s in (1, 2)]
mean, sig = signals(nets, X, Xt, mu, sd)
err = verr(mean, y)
scale = {k: np.percentile(v[ca], 90) + 1e-9 for k, v in sig.items()}
doubt = np.max(np.stack([sig[k] / scale[k] for k in sig]), 0)
tau = pick_tau(doubt[ca], err[ca], TOL)
cd0 = np.median(yt / Xt[:, -1:], axis=0)
torch.save(dict(nets=[n_.state_dict() for n_ in nets], mu=mu, sd=sd, scale=scale, tau=tau, Xtr=Xt, cd0=cd0, extra=bool(EXTRA)), sys.argv[3])
a = doubt[te] <= tau
print(json.dumps(dict(n_features=int(X.shape[1]), tau=round(tau, 3), extra_runs=len(Xe), train_rows=len(Xt), seconds=round(time.time() - t0, 1), test_vector_err_pct=round(float(err[te].mean() * 100), 2),
                      test_answered_instantly_pct=round(float(a.mean() * 100), 1), test_err_of_answered_pct=round(float(err[te][a].mean() * 100), 2) if a.any() else None)))

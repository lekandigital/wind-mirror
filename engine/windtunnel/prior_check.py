"""How much of the force do three geometric numbers explain? A first look at the wind's-eye features on the pitch-night runs."""
import time, numpy as np
import data as D, geom as G

if __name__ == '__main__':
    t0 = time.time()
    P = D.load('../../out/pitch/poses_v1.jsonl', '../../out/pitch/feat_cache.npz')
    print('pitch rows', P['n'], 'features', P['X'].shape, P['J'].shape, round(time.time() - t0, 1), 's')
    for c in ('fly', 'puppet', 'row'):
        C = D.load(f'../../out/pitch/clip_{c}.jsonl', '../../out/pitch/feat_cache.npz', source='clip_' + c); print(c, C['n'])
    m = P['split'] == 'in'
    X, y = P['X'], P['y']
    ix = lambda n: G.NAMES.index(n)
    for tname, t, cols in (('drag', 0, ['A', 'Nx']), ('lift', 1, ['Nz', 'Bz', 'A']), ('side', 2, ['Ny', 'By'])):
        c = [ix(n) for n in cols]
        w, *_ = np.linalg.lstsq(X[m][:, c], y[m, t], rcond=None)
        for lab, mask in (('in', m), ('ood', ~m)):
            pred = X[mask][:, c] @ w; e = np.abs(pred - y[mask, t])
            print(f'{tname:5s} ~ {cols} w={np.round(w, 3)} {lab}: mean abs err {e.mean():.4f} m2 (target sd {y[mask, t].std():.3f})  as share of |F| {np.mean(e / np.linalg.norm(y[mask], axis=1)) * 100:.1f}%')

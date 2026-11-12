// Model B in the tab: linear trend on the wind's-eye features + a local Gaussian-process correction from the 40 nearest
// solver runs, six doubt signals, and the conformal error bound. A port of engine/windtunnel/model_b.py + krige.py;
// tests/parity_b.mjs checks it against the Python.
import { NG, NFEAT } from './geom.js';

function f32(b64) { const bin = atob(b64); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new Float32Array(u.buffer); }

export class ModelB {
  constructor(j) { this.set(j); }
  static async load(url) { return new ModelB(await (await fetch(url, { cache: 'no-store' })).json()); }

  set(j) {
    this.j = j; this.tol = j.tol; this.q = j.doubt_q; this.w = j.doubt_w; this.use = j.doubt_use; this.version = j.version; this.nRuns = j.n_runs;
    this.N = j.N; this.Za = f32(j.Za); this.res = f32(j.res); this.loo = f32(j.loo);
    this.zz = new Float64Array(this.N);
    for (let i = 0; i < this.N; i++) { let s = 0; const o = i * NFEAT; for (let d = 0; d < NFEAT; d++) { const v = this.Za[o + d]; s += v * v; } this.zz[i] = s; }
    this.d2 = new Float64Array(this.N);
    this.k = Math.min(j.k, this.N - 2);
    this.idx = new Int32Array(this.k);
    this.K = new Float64Array(this.k * this.k); this.rhs = new Float64Array(this.k * 4);
  }

  check(X) {
    const j = this.j, n = NFEAT, N = this.N, k = this.k;
    const Z = new Float64Array(n + 1);
    for (let d = 0; d < n; d++) Z[d] = (X[d] - j.full_mu[d]) / j.full_sd[d];
    Z[n] = 1;
    const lin = (Zv, W, nout) => { const o = new Float64Array(nout); for (let i = 0; i < Zv.length; i++) { const zi = Zv[i]; if (zi === 0) continue; for (let c = 0; c < nout; c++) o[c] += zi * W[i * nout + c]; } return o; };
    const pt = lin(Z, j.full_W, 3);
    const Zg = new Float64Array(NG + 1);
    for (let d = 0; d < NG; d++) Zg[d] = (X[d] - j.glob_mu[d]) / j.glob_sd[d];
    Zg[NG] = 1;
    const pg = lin(Zg, j.glob_W, 3);
    const Zp = new Float64Array(n + 1);
    for (let d = 0; d < n; d++) Zp[d] = (X[d] - j.parts_mu[d]) / j.parts_sd[d];
    Zp[n] = 1;
    const parts = lin(Zp, j.parts_W, 30);
    // distances to every solver run in the store
    let qq = 0; for (let d = 0; d < n; d++) qq += Z[d] * Z[d];
    const Za = this.Za, d2 = this.d2;
    for (let i = 0; i < N; i++) { let s = 0; const o = i * n; for (let d = 0; d < n; d++) s += Z[d] * Za[o + d]; const v = qq - 2 * s + this.zz[i]; d2[i] = v > 0 ? v : 0; }
    // the k nearest (insertion into a small sorted list)
    const idx = this.idx; let cnt = 0;
    for (let i = 0; i < N; i++) {
      const v = d2[i];
      if (cnt < k) { let m = cnt++; while (m > 0 && d2[idx[m - 1]] > v) { idx[m] = idx[m - 1]; m--; } idx[m] = i; }
      else if (v < d2[idx[k - 1]]) { let m = k - 1; while (m > 0 && d2[idx[m - 1]] > v) { idx[m] = idx[m - 1]; m--; } idx[m] = i; }
    }
    // local kriging: solve (K + noise I) [w | alpha] = [ks | R / scale]
    const ell2 = 2 * j.ell * j.ell, K = this.K, rhs = this.rhs;
    for (let a = 0; a < k; a++) {
      const oa = idx[a] * n;
      for (let b = 0; b <= a; b++) {
        const ob = idx[b] * n; let s = 0;
        for (let d = 0; d < n; d++) { const t = Za[oa + d] - Za[ob + d]; s += t * t; }
        const v = Math.exp(-s / ell2) + (a === b ? j.noise : 0);
        K[a * k + b] = v; K[b * k + a] = v;
      }
      rhs[a * 4] = Math.exp(-d2[idx[a]] / ell2);
      for (let c = 0; c < 3; c++) rhs[a * 4 + 1 + c] = this.res[idx[a] * 3 + c] / j.gp_scale[c];
    }
    const ks = new Float64Array(k); for (let a = 0; a < k; a++) ks[a] = rhs[a * 4];
    for (let a = 0; a < k; a++) {                                 // Cholesky, in place (lower triangle)
      for (let b = 0; b <= a; b++) {
        let s = K[a * k + b];
        for (let c = 0; c < b; c++) s -= K[a * k + c] * K[b * k + c];
        K[a * k + b] = a === b ? Math.sqrt(Math.max(s, 1e-12)) : s / K[b * k + b];
      }
    }
    for (let c = 0; c < 4; c++) {                                 // forward and back substitution for each right-hand side
      for (let a = 0; a < k; a++) { let s = rhs[a * 4 + c]; for (let b = 0; b < a; b++) s -= K[a * k + b] * rhs[b * 4 + c]; rhs[a * 4 + c] = s / K[a * k + a]; }
      for (let a = k - 1; a >= 0; a--) { let s = rhs[a * 4 + c]; for (let b = a + 1; b < k; b++) s -= K[b * k + a] * rhs[b * 4 + c]; rhs[a * 4 + c] = s / K[a * k + a]; }
    }
    let kw = 0; const gm = [0, 0, 0];
    for (let a = 0; a < k; a++) { kw += ks[a] * rhs[a * 4]; for (let c = 0; c < 3; c++) gm[c] += ks[a] * rhs[a * 4 + 1 + c]; }
    const gsd = Math.sqrt(Math.max(1 - kw, 0));
    const p = j.use_gp ? [pt[0] + gm[0] * j.gp_scale[0], pt[1] + gm[1] * j.gp_scale[1], pt[2] + gm[2] * j.gp_scale[2]] : [pt[0], pt[1], pt[2]];
    const size = Math.hypot(p[0], p[1], p[2]) + 1e-9;
    // signals
    let lev = 0;
    for (let a = 0; a <= n; a++) { let s = 0; const row = a * (n + 1); for (let b = 0; b <= n; b++) s += j.full_Ainv[row + b] * Z[b]; lev += Z[a] * s; }
    let knn = 0; for (let m = 0; m < 5; m++) knn += Math.sqrt(d2[idx[m]]);
    knn = knn / 5 / Math.sqrt(n);
    let lw = 0, ls = 0;
    for (let m = 0; m < 8; m++) { const wgt = Math.exp(-d2[idx[m]] / ell2) + 1e-6; lw += wgt; ls += wgt * this.loo[idx[m]]; }
    const loc = ls / lw;
    const dis = Math.hypot(pt[0] - pg[0], pt[1] - pg[1], pt[2] - pg[2]) / size;
    let s0 = 0, s1 = 0, s2 = 0;
    for (let q = 0; q < 10; q++) { s0 += parts[q * 3]; s1 += parts[q * 3 + 1]; s2 += parts[q * 3 + 2]; }
    const par = Math.hypot(s0 - pt[0], s1 - pt[1], s2 - pt[2]) / size;
    const S = [lev, knn, dis, par, gsd, loc];
    let lg = this.w[this.w.length - 1];
    for (let u = 0; u < this.use.length; u++) lg += this.w[u] * Math.log(Math.max(S[this.use[u]], 1e-6));
    const bound = this.q * Math.hypot(Math.exp(lg), this.j.doubt_s0 || 0);
    return { force: p, parts, signals: S, bound, sure: bound <= this.tol };
  }
}

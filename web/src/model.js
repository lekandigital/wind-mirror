// The surrogate in the tab: a port of engine/windtunnel/model_io.py. Linear trend on the wind's-eye features, four doubt
// signals, and the conformal error bound. Weights come from models/*.json (written by engine/windtunnel/export_model.py).
import { NG, NFEAT } from './geom.js';

export const Q_KG_PER_M2 = 0.5 * 1.225 * (100 / 3.6) ** 2 / 9.80665;   // kg of push per m^2 of drag area in a 100 km/h wind

export class Model {
  constructor(j) {
    this.j = j; this.tol = j.tol; this.q = j.doubt_q; this.w = j.doubt_w; this.use = j.doubt_use; this.k = j.k;
    this.nref = j.Zref.length / NFEAT;
    this.Zref = Float64Array.from(j.Zref);
    this.zz = new Float64Array(this.nref);
    for (let i = 0; i < this.nref; i++) { let s = 0; for (let d = 0; d < NFEAT; d++) { const v = this.Zref[i * NFEAT + d]; s += v * v; } this.zz[i] = s; }
    this.memory = [];                                        // solver runs learned in this session: {z, r}
  }

  static async load(url) { return new Model(await (await fetch(url)).json()); }

  check(X) {
    const j = this.j, n = NFEAT;
    const Z = new Float64Array(n + 1);
    for (let d = 0; d < n; d++) Z[d] = (X[d] - j.full_mu[d]) / j.full_sd[d];
    Z[n] = 1;
    const lin = (Zv, W, nout) => { const o = new Float64Array(nout); for (let i = 0; i < Zv.length; i++) { const zi = Zv[i]; if (zi === 0) continue; for (let k = 0; k < nout; k++) o[k] += zi * W[i * nout + k]; } return o; };
    const p = lin(Z, j.full_W, 3);
    const Zg = new Float64Array(NG + 1);
    for (let d = 0; d < NG; d++) Zg[d] = (X[d] - j.glob_mu[d]) / j.glob_sd[d];
    Zg[NG] = 1;
    const pg = lin(Zg, j.glob_W, 3);
    const Zp = new Float64Array(n + 1);
    for (let d = 0; d < n; d++) Zp[d] = (X[d] - j.parts_mu[d]) / j.parts_sd[d];
    Zp[n] = 1;
    const parts = lin(Zp, j.parts_W, 30);
    const size = Math.hypot(p[0], p[1], p[2]) + 1e-9;
    let lev = 0;
    for (let a = 0; a <= n; a++) { let s = 0; const row = a * (n + 1); for (let b = 0; b <= n; b++) s += j.full_Ainv[row + b] * Z[b]; lev += Z[a] * s; }
    let qq = 0; for (let d = 0; d < n; d++) qq += Z[d] * Z[d];
    const best = new Float64Array(this.k).fill(Infinity);
    for (let i = 0; i < this.nref; i++) {
      let s = 0; const o = i * n;
      for (let d = 0; d < n; d++) s += Z[d] * this.Zref[o + d];
      const d2 = Math.max(qq - 2 * s + this.zz[i], 0);
      if (d2 < best[this.k - 1]) { let m = this.k - 1; while (m > 0 && best[m - 1] > d2) { best[m] = best[m - 1]; m--; } best[m] = d2; }
    }
    let knn = 0; for (let m = 0; m < this.k; m++) knn += Math.sqrt(best[m]);
    knn = knn / this.k / Math.sqrt(n);
    const dis = Math.hypot(p[0] - pg[0], p[1] - pg[1], p[2] - pg[2]) / size;
    let s0 = 0, s1 = 0, s2 = 0;
    for (let q = 0; q < 10; q++) { s0 += parts[q * 3]; s1 += parts[q * 3 + 1]; s2 += parts[q * 3 + 2]; }
    const par = Math.hypot(s0 - p[0], s1 - p[1], s2 - p[2]) / size;
    const S = [lev, knn, dis, par];
    let ls = this.w[this.w.length - 1];
    for (let u = 0; u < this.use.length; u++) ls += this.w[u] * Math.log(Math.max(S[this.use[u]], 1e-6));
    const bound = this.q * Math.exp(ls);
    return { force: p, parts, signals: S, bound, sure: bound <= this.tol, z: Z };
  }
}

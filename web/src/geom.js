// Wind's-eye-view features: a port of engine/windtunnel/geom.py. Same grid, same order of operations, so the numbers match
// the Python that produced the training data (tests/parity.mjs checks this).
import { bodyCapsules, PARTS } from './body.js';

export const PX = 0.02, YMIN = -1.5, YMAX = 1.5, ZMAX = 2.7;
export const NYP = Math.round((YMAX - YMIN) / PX), NZP = Math.round(ZMAX / PX);
export const NPART = PARTS.length;
export const GLOBAL_NAMES = ['A', 'Nx', 'Ny', 'Nz', 'By', 'Bz', 'thick', 'len_x', 'width', 'height', 'perim', 'zc', 'depth_sd', 'tilt_y', 'tilt_z', 'A_side', 'A_top'];
export const NG = GLOBAL_NAMES.length;
export const NAMES = GLOBAL_NAMES.concat(PARTS.flatMap((p) => ['A', 'Nx', 'Ny', 'Nz', 'Ab'].map((k) => `${p}:${k}`)));
export const NFEAT = NAMES.length;

function window_(axis) {
  if (axis === 0) return [1, 2, YMIN, NYP, 0.0, NZP];
  if (axis === 1) return [0, 2, -2.0, Math.round(4.0 / PX), 0.0, NZP];
  return [0, 1, -2.0, Math.round(4.0 / PX), YMIN, NYP];
}

// Ray-cast capsules along `axis`. Returns front/back depth (Infinity / -Infinity on a miss), normals and parts.
export function cast(caps, axis, wantNormals) {
  const [k0, k1, u0, nu, v0, nv] = window_(axis);
  const n = nu * nv;
  const front = new Float64Array(n).fill(Infinity), back = new Float64Array(n).fill(-Infinity);
  const pf = new Int16Array(n).fill(-1), pb = new Int16Array(n).fill(-1);
  const nf = wantNormals ? new Float64Array(n * 3) : null, nb = wantNormals ? new Float64Array(n * 3) : null;
  const O = [0, 0, 0];
  for (const { a, b, r, part } of caps) {
    const loU = Math.max(Math.floor((Math.min(a[k0], b[k0]) - r - u0) / PX), 0), hiU = Math.min(Math.ceil((Math.max(a[k0], b[k0]) + r - u0) / PX) + 1, nu);
    const loV = Math.max(Math.floor((Math.min(a[k1], b[k1]) - r - v0) / PX), 0), hiV = Math.min(Math.ceil((Math.max(a[k1], b[k1]) + r - v0) / PX) + 1, nv);
    if (hiU <= loU || hiV <= loV) continue;
    const ba = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    const baba = ba[0] * ba[0] + ba[1] * ba[1] + ba[2] * ba[2], bard = ba[axis];
    const Aq = baba - bard * bard;
    for (let iu = loU; iu < hiU; iu++) {
      for (let iv = loV; iv < hiV; iv++) {
        O[axis] = 0; O[k0] = u0 + (iu + 0.5) * PX; O[k1] = v0 + (iv + 0.5) * PX;
        let tIn = Infinity, tOut = -Infinity;
        for (let e = 0; e < 2; e++) {                               // the two end spheres
          const c = e === 0 ? a : b;
          const ox = O[0] - c[0], oy = O[1] - c[1], oz = O[2] - c[2];
          const Bq = e === 0 ? (axis === 0 ? ox : axis === 1 ? oy : oz) : (axis === 0 ? ox : axis === 1 ? oy : oz);
          const Cq = ox * ox + oy * oy + oz * oz - r * r;
          const h = Bq * Bq - Cq;
          if (h > 0) { const sq = Math.sqrt(h); if (-Bq - sq < tIn) tIn = -Bq - sq; if (-Bq + sq > tOut) tOut = -Bq + sq; }
        }
        if (baba > 1e-12) {                                         // the cylinder between them, clipped to the segment
          const ox = O[0] - a[0], oy = O[1] - a[1], oz = O[2] - a[2];
          const baoa = ox * ba[0] + oy * ba[1] + oz * ba[2];
          const rdoa = axis === 0 ? ox : axis === 1 ? oy : oz;
          const oaoa = ox * ox + oy * oy + oz * oz;
          const Cq = baba * oaoa - baoa * baoa - r * r * baba;
          let ok, c1, c2;
          if (Aq > 1e-9 * baba) {
            const Bq = baba * rdoa - baoa * bard;
            const h = Bq * Bq - Aq * Cq;
            ok = h > 0;
            const sq = Math.sqrt(ok ? h : 0);
            c1 = (-Bq - sq) / Aq; c2 = (-Bq + sq) / Aq;
          } else { ok = Cq < 0; c1 = -Infinity; c2 = Infinity; }
          let lo, hi;
          if (Math.abs(bard) > 1e-12) {
            const s1 = (0.0 - baoa) / bard, s2 = (baba - baoa) / bard;
            lo = Math.min(s1, s2); hi = Math.max(s1, s2);
          } else {
            const inside = baoa >= 0 && baoa <= baba;
            lo = inside ? -Infinity : Infinity; hi = inside ? Infinity : -Infinity;
          }
          const e1 = Math.max(c1, lo), e2 = Math.min(c2, hi);
          if (ok && e2 > e1) { if (e1 < tIn) tIn = e1; if (e2 > tOut) tOut = e2; }
        }
        if (!(tOut > tIn)) continue;
        const idx = iu * nv + iv;
        for (let side = 0; side < 2; side++) {
          const t = side === 0 ? tIn : tOut;
          const depth = side === 0 ? front : back;
          const upd = side === 0 ? t < depth[idx] : t > depth[idx];
          if (!upd) continue;
          depth[idx] = t;
          (side === 0 ? pf : pb)[idx] = part;
          if (wantNormals) {
            const P0 = O[0] + (axis === 0 ? t : 0), P1 = O[1] + (axis === 1 ? t : 0), P2 = O[2] + (axis === 2 ? t : 0);
            let s = 0;
            if (baba > 1e-12) s = Math.min(Math.max(((P0 - a[0]) * ba[0] + (P1 - a[1]) * ba[1] + (P2 - a[2]) * ba[2]) / baba, 0), 1);
            const nn = side === 0 ? nf : nb;
            nn[idx * 3] = (P0 - (a[0] + s * ba[0])) / r; nn[idx * 3 + 1] = (P1 - (a[1] + s * ba[1])) / r; nn[idx * 3 + 2] = (P2 - (a[2] + s * ba[2])) / r;
          }
        }
      }
    }
  }
  return { front, back, nf, nb, pf, pb, nu, nv };
}

export function featuresFromCapsules(caps) {
  const { front, back, nf, nb, pf, pb, nu, nv } = cast(caps, 0, true);
  const dA = PX * PX;
  const f = new Float64Array(NFEAT);
  let nhit = 0;
  for (let i = 0; i < nu * nv; i++) if (front[i] !== Infinity) nhit++;
  if (nhit === 0) return f;
  const A = nhit * dA;
  let Nx = 0, Ny = 0, Nz = 0, By = 0, Bz = 0, thick = 0, bmax = -Infinity, fmin = Infinity;
  let iuMin = nu, iuMax = -1, ivMin = nv, ivMax = -1, sy = 0, sz = 0, sd = 0;
  const P = new Float64Array(NPART * 5);
  for (let iu = 0; iu < nu; iu++) {
    for (let iv = 0; iv < nv; iv++) {
      const i = iu * nv + iv;
      if (front[i] === Infinity) continue;
      const w = nf[i * 3];
      Nx += w * nf[i * 3]; Ny += w * nf[i * 3 + 1]; Nz += w * nf[i * 3 + 2];
      By += nb[i * 3 + 1]; Bz += nb[i * 3 + 2];
      thick += back[i] - front[i];
      if (back[i] > bmax) bmax = back[i];
      if (front[i] < fmin) fmin = front[i];
      if (iu < iuMin) iuMin = iu; if (iu > iuMax) iuMax = iu; if (iv < ivMin) ivMin = iv; if (iv > ivMax) ivMax = iv;
      sy += YMIN + (iu + 0.5) * PX; sz += (iv + 0.5) * PX; sd += front[i];
      const p = pf[i];
      P[p * 5] += dA; P[p * 5 + 1] += w * nf[i * 3] * dA; P[p * 5 + 2] += w * nf[i * 3 + 1] * dA; P[p * 5 + 3] += w * nf[i * 3 + 2] * dA;
      P[pb[i] * 5 + 4] += dA;
    }
  }
  const yc = sy / nhit, zc = sz / nhit, dm = sd / nhit;
  let var_ = 0, ty = 0, tz = 0, perim = 0;
  const hit = (iu, iv) => iu >= 0 && iu < nu && iv >= 0 && iv < nv && front[iu * nv + iv] !== Infinity;
  for (let iu = 0; iu < nu; iu++) {
    for (let iv = 0; iv < nv; iv++) {
      const i = iu * nv + iv;
      if (front[i] === Infinity) continue;
      const d = front[i] - dm;
      var_ += d * d; ty += d * (YMIN + (iu + 0.5) * PX - yc); tz += d * ((iv + 0.5) * PX - zc);
      if (!hit(iu - 1, iv)) perim++; if (!hit(iu + 1, iv)) perim++; if (!hit(iu, iv - 1)) perim++; if (!hit(iu, iv + 1)) perim++;
    }
  }
  const count = (axis) => { const c = cast(caps, axis, false); let k = 0; for (let i = 0; i < c.front.length; i++) if (c.front[i] !== Infinity) k++; return k * dA; };
  const g = [A, Nx * dA, Ny * dA, Nz * dA, By * dA, Bz * dA, thick * dA / A, bmax - fmin, (iuMax - iuMin + 1) * PX, (ivMax - ivMin + 1) * PX, perim * PX, zc,
    Math.sqrt(var_ / nhit), ty / nhit, tz / nhit, count(1), count(2)];
  for (let i = 0; i < NG; i++) f[i] = g[i];
  for (let i = 0; i < NPART * 5; i++) f[NG + i] = P[i];
  return f;
}

export function features(pose, shape) { return featuresFromCapsules(bodyCapsules(pose, shape)); }

// The capsule twin: pose (unit bone directions) + shape (proportions) -> joints -> capsules.
// A line-for-line port of engine/windtunnel/bodies.py (joints, capsules, dims). World frame: wind blows toward +x,
// y is lateral, z is up; a person facing the wind faces -x with their left at -y.

export const LEN = { torso: 0.50, neck: 0.10, head: 0.12, sh: 0.19, hip: 0.085, uarm: 0.29, farm: 0.26, hand: 0.07, thigh: 0.44, shin: 0.42, foot: 0.20 };
export const RAD = { head: 0.105, neck: 0.055, torso_c: 0.125, torso_s: 0.105, girdle: 0.06, pelvis: 0.10, uarm: 0.047, farm: 0.040, hand: 0.040, thigh: 0.078, shin: 0.052, foot: 0.042 };
export const PARTS = ['head', 'torso', 'L_upper_arm', 'L_forearm', 'R_upper_arm', 'R_forearm', 'L_thigh', 'L_shin', 'R_thigh', 'R_shin'];
export const BONES = ['t', 'l', 'h', 'uaL', 'faL', 'uaR', 'faR', 'thL', 'shL', 'thR', 'shR', 'lh'];
export const SHAPE_KEYS = ['g_torso', 'g_limb', 'leg', 'arm', 'sh', 'hip', 'torso'];

export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const norm = (a) => Math.sqrt(dot(a, a));
export function unit(v) { const n = norm(v); return n > 1e-9 ? [v[0] / n, v[1] / n, v[2] / n] : [v[0], v[1], v[2]]; }

export function dims(shape) {
  if (!shape) return [LEN, RAD];
  const g = (k) => (shape[k] === undefined ? 1.0 : shape[k]);
  const L = { ...LEN }, R = { ...RAD };
  L.thigh *= g('leg'); L.shin *= g('leg');
  L.uarm *= g('arm'); L.farm *= g('arm');
  L.sh *= g('sh'); L.hip *= g('hip'); L.torso *= g('torso');
  for (const k of ['torso_c', 'torso_s', 'girdle', 'pelvis']) R[k] *= g('g_torso');
  for (const k of ['uarm', 'farm', 'hand', 'thigh', 'shin', 'foot']) R[k] *= g('g_limb');
  return [L, R];
}

export function hipLine(pose) {
  const t = unit(pose.t);
  const lh = unit(pose.lh ? pose.lh : pose.l);
  return unit(sub(lh, mul(t, dot(lh, t))));
}

export function joints(pose, shape) {
  const [L] = dims(shape);
  const t = unit(pose.t), h = unit(pose.h);
  let l = unit(pose.l); l = unit(sub(l, mul(t, dot(l, t))));
  const lh = hipLine(pose);
  const J = {};
  J.pelvis = [0, 0, 0];
  J.neck = mul(t, L.torso);
  J.head = add(J.neck, mul(h, L.neck + L.head));
  for (const [s, sg] of [['L', 1.0], ['R', -1.0]]) {
    J['sh' + s] = add(J.neck, mul(l, sg * L.sh));
    J['el' + s] = add(J['sh' + s], mul(unit(pose['ua' + s]), L.uarm));
    J['wr' + s] = add(J['el' + s], mul(unit(pose['fa' + s]), L.farm));
    J['hand' + s] = add(J['wr' + s], mul(unit(pose['fa' + s]), L.hand));
    J['hip' + s] = mul(lh, sg * L.hip);
    J['kn' + s] = add(J['hip' + s], mul(unit(pose['th' + s]), L.thigh));
    J['an' + s] = add(J['kn' + s], mul(unit(pose['sh' + s]), L.shin));
    const fwd = cross(lh, t);
    const sh = unit(pose['sh' + s]);
    let fd = sub(fwd, mul(sh, dot(fwd, sh)));
    fd = norm(fd) > 1e-3 ? unit(fd) : unit(cross(sh, lh));
    J['toe' + s] = add(J['an' + s], mul(fd, L.foot));
  }
  return J;
}

// Returns [{a, b, r, part}], pelvis at the origin.
export function capsules(J, pose, shape) {
  const [, R] = dims(shape);
  const t = unit(pose.t);
  let l = unit(pose.l); l = unit(sub(l, mul(t, dot(l, t))));
  const lh = hipLine(pose);
  const gs = (k) => (shape && shape[k] !== undefined ? shape[k] : 1.0);
  const wt = 0.11 * gs('sh') * Math.pow(gs('g_torso'), 0.5), wb = 0.075 * gs('hip');
  const C = [];
  const push = (a, b, r, part) => C.push({ a, b, r, part });
  push(J.head, J.head, R.head, 0);
  push(J.neck, J.head, R.neck, 0);
  push(add(J.pelvis, mul(t, 0.07)), sub(J.neck, mul(t, 0.09)), R.torso_c, 1);
  for (const sg of [1.0, -1.0]) {
    push(add(sub(J.neck, mul(t, 0.07)), mul(l, sg * wt)), add(add(J.pelvis, mul(t, 0.03)), mul(lh, sg * wb)), R.torso_s, 1);
  }
  push(J.shL, J.shR, R.girdle, 1);
  push(J.hipL, J.hipR, R.pelvis, 1);
  for (const [s, pu, pf, pt, ps] of [['L', 2, 3, 6, 7], ['R', 4, 5, 8, 9]]) {
    push(J['sh' + s], J['el' + s], R.uarm, pu);
    push(J['el' + s], J['wr' + s], R.farm, pf);
    push(J['wr' + s], J['hand' + s], R.hand, pf);
    push(J['hip' + s], J['kn' + s], R.thigh, pt);
    push(J['kn' + s], J['an' + s], R.shin, ps);
    push(J['an' + s], J['toe' + s], R.foot, ps);
  }
  return C;
}

// Capsules with the floor at z = 0 (the body's lowest point rests on it) and the pelvis at x = y = 0.
export function bodyCapsules(pose, shape) {
  const J = joints(pose, shape);
  const caps = capsules(J, pose, shape);
  let zmin = Infinity;
  for (const c of caps) zmin = Math.min(zmin, Math.min(c.a[2], c.b[2]) - c.r);
  return caps.map((c) => ({ a: [c.a[0], c.a[1], c.a[2] - zmin], b: [c.b[0], c.b[1], c.b[2] - zmin], r: c.r, part: c.part }));
}

export function poseFromList(lst) {
  const p = {};
  for (let i = 0; i < lst.length && i < BONES.length; i++) p[BONES[i]] = lst[i];
  return p;
}

// A neutral standing pose facing the wind (bodies.make_pose() defaults).
export function standingPose() {
  const d = Math.PI / 180;
  const fwd = [-1, 0, 0], left = [0, -1, 0], up = [0, 0, 1];
  const t = up, l = left, fwdT = cross(l, t);
  const pose = { t, l, h: up };
  for (const [s, sg] of [['L', 1], ['R', -1]]) {
    const side = mul(l, sg);
    const ab = 10 * d, el = 5 * d;
    const ua = unit(add(mul(t, -Math.cos(ab)), mul(side, Math.sin(ab))));
    let e = sub(fwdT, mul(ua, dot(fwdT, ua))); e = unit(e);
    pose['ua' + s] = ua;
    pose['fa' + s] = unit(add(mul(ua, Math.cos(el)), mul(e, Math.sin(el))));
    const sd = mul(left, sg), a4 = 4 * d;
    const th = unit(add(mul(up, -Math.cos(a4)), mul(sd, Math.sin(a4))));
    pose['th' + s] = th; pose['sh' + s] = th;
  }
  return pose;
}

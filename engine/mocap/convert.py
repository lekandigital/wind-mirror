"""CMU ASF/AMC -> Wind Mirror poses (12 unit vectors), heading-canonicalised, 2 poses per second.

Usage:
  python convert.py <subjects dir> <cmu_index.json> <out cmu_all.jsonl> [--workers 24] [--only 02_01,49_06]

Pose vectors, in this order: t, l, h, uaL, faL, uaR, faR, thL, shL, thR, shR, lh   (bodies.BONES + 'lh')
  t   mid-hips -> mid-shoulders            l  right shoulder -> left shoulder, orthogonalised against t
  h   mid-shoulders -> head centre         lh right hip -> left hip, orthogonalised against t
  ua  shoulder -> elbow    fa elbow -> wrist    th hip -> knee    sh knee -> ankle
CMU joints used: hip = end of <s>hipjoint, knee = end of <s>femur, ankle = end of <s>tibia, shoulder = end of
<s>clavicle, elbow = end of <s>humerus, wrist = end of <s>radius, head centre = midpoint of the head bone
(end of upperneck .. end of head).

Sampling: t = 0.25 s, 0.75 s, ... up to (duration - 0.25 s), nearest frame; frame numbers are the AMC's (1-based).
Heading: psi = atan2(hip_y, hip_x) + 90 deg for the raw (un-orthogonalised) right->left hip vector, so that
  pose_as_captured = Rz(heading_deg) @ pose_stored. Stored poses have the hip line's horizontal projection along -y
  (left at -y, forward -x). Pitch/roll are untouched (rotation about world z only). If the unit hip vector's horizontal
  length is < HEADING_MIN_HORIZ the heading of the last earlier frame (full frame rate) with a valid hip line is used
  (or, if none, the first later one; or 0 if the trial has none) and heading_fallback is true.
Record fields: id, subject, trial, frame, t (s since the first frame), desc (trial description, 'unknown' if not in
  the CMU index), cat (subject description, or the AMC header source path for subjects missing from the index),
  coarse (primary keyword category, categories.py), pose (12 x [x,y,z]), heading_deg, heading_fallback,
  torso_up (= t_z), pelvis_h (mid-hip height above the lowest non-finger joint / skeleton height proxy, see
  asfamc.Skeleton.rest_height_m), fps, fps_assumed (true when the index has no frame rate: 120 assumed),
  hip_horiz (horizontal length of the unit hip vector; < 0.3 means fallback).
"""
import sys, os, re, json, math, argparse, glob
import numpy as np
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asfamc
import categories

BONES12 = ['t', 'l', 'h', 'uaL', 'faL', 'uaR', 'faR', 'thL', 'shL', 'thR', 'shR', 'lh']
SAMPLE_HZ = 2.0
EDGE_S = 0.25
HEADING_MIN_HORIZ = 0.3     # |horizontal part| of the unit hip line below this -> heading undefined (on the side)
DEFAULT_FPS = 120
# joints considered for "lowest joint" (bone end points; fingers and thumbs excluded as noisy / not captured)
LOW_SET = ['root', 'lhipjoint', 'rhipjoint', 'lfemur', 'rfemur', 'ltibia', 'rtibia', 'lfoot', 'rfoot', 'ltoes', 'rtoes',
           'lowerback', 'upperback', 'thorax', 'lowerneck', 'upperneck', 'head', 'lclavicle', 'rclavicle',
           'lhumerus', 'rhumerus', 'lradius', 'rradius', 'lwrist', 'rwrist', 'lhand', 'rhand']


def unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def orth(v, t):
    return unit(v - np.sum(v * t, -1, keepdims=True) * t)


def vectors(W):
    """W: dict joint -> (F, 3) world positions. Returns (F, 12, 3) raw (not heading-canonicalised) unit vectors."""
    hipL, hipR = W['lhipjoint'], W['rhipjoint']
    shL, shR = W['lclavicle'], W['rclavicle']
    pel, neck = 0.5 * (hipL + hipR), 0.5 * (shL + shR)
    head = 0.5 * (W['upperneck'] + W['head'])
    t = unit(neck - pel)
    V = [t, orth(shL - shR, t), unit(head - neck),
         unit(W['lhumerus'] - shL), unit(W['lradius'] - W['lhumerus']),
         unit(W['rhumerus'] - shR), unit(W['rradius'] - W['rhumerus']),
         unit(W['lfemur'] - hipL), unit(W['ltibia'] - W['lfemur']),
         unit(W['rfemur'] - hipR), unit(W['rtibia'] - W['rfemur']),
         orth(hipL - hipR, t)]
    return np.stack(V, 1)


def headings(W):
    """Per frame: heading angle (deg) of the raw hip line and a validity mask.
    heading = angle psi such that pose_world = Rz(psi) @ pose_canonical, where canonical has the hip line
    (right hip -> left hip) horizontal projection along -y (left at -y, forward -x)."""
    v = unit(W['lhipjoint'] - W['rhipjoint'])
    hn = np.hypot(v[:, 0], v[:, 1])
    psi = np.degrees(np.arctan2(v[:, 1], v[:, 0])) + 90.0
    psi = (psi + 180.0) % 360.0 - 180.0
    return psi, hn >= HEADING_MIN_HORIZ, hn


def rotz_deg(a):
    a = np.radians(a)
    c, s = np.cos(a), np.sin(a)
    R = np.zeros(np.shape(a) + (3, 3))
    R[..., 0, 0], R[..., 0, 1], R[..., 1, 0], R[..., 1, 1], R[..., 2, 2] = c, -s, s, c, 1.0
    return R


def sample_rows(n_frames, fps):
    dur = (n_frames - 1) / fps
    times = np.arange(EDGE_S, dur - EDGE_S + 1e-9, 1.0 / SAMPLE_HZ)
    rows = np.round(times * fps).astype(int)
    return rows[(rows >= 0) & (rows < n_frames)]


def process_trial(args):
    asf, amc, subj, trial, fps, fps_assumed, desc, cat = args
    try:
        sk = asfamc.Skeleton(asf)
        frames, mot = asfamc.read_amc(amc, sk)
        n = len(frames)
        if n == 0:
            return dict(err=f'{amc}: no frames', recs=[])
        W = asfamc.to_world(asfamc.fk(sk, mot))          # all frames, so the heading fallback can use any earlier frame
        psi, ok, hn = headings(W)
        rows = sample_rows(n, fps)
        if len(rows) == 0:
            return dict(err=None, recs=[], n_frames=n)
        V = vectors({k: v[rows] for k, v in W.items()})
        H = sk.rest_height_m()
        coarse = categories.primary_category(desc, cat)
        valid_idx = np.where(ok)[0]
        recs = []
        for k, r in enumerate(rows):
            fb = not ok[r]
            if fb:
                prev = valid_idx[valid_idx < r]
                if len(prev):
                    hd = psi[prev[-1]]
                else:
                    nxt = valid_idx[valid_idx > r]
                    hd = psi[nxt[0]] if len(nxt) else 0.0
            else:
                hd = psi[r]
            Rm = rotz_deg(-hd)
            pose = V[k] @ Rm.T
            pel = 0.5 * (W['lhipjoint'][r] + W['rhipjoint'][r])
            low = min(W[j][r, 2] for j in LOW_SET)
            recs.append(dict(
                id=f's{subj}_t{trial}_f{int(frames[r])}', subject=subj, trial=trial, frame=int(frames[r]),
                t=round(float((frames[r] - frames[0]) / fps), 4), desc=desc, cat=cat, coarse=coarse,
                pose=[[round(float(x), 8) for x in vec] for vec in pose],
                heading_deg=round(float(hd), 3), heading_fallback=bool(fb),
                torso_up=round(float(pose[0, 2]), 8), pelvis_h=round(float((pel[2] - low) / H), 5),
                fps=int(fps), fps_assumed=bool(fps_assumed), hip_horiz=round(float(hn[r]), 4)))
        return dict(err=None, recs=recs, n_frames=n, height_m=H)
    except Exception as e:  # report, never silently drop
        return dict(err=f'{amc}: {type(e).__name__}: {e}', recs=[])


def build_jobs(subjects_dir, index, only=None):
    S = index['subjects']
    jobs = []
    for amc in sorted(glob.glob(os.path.join(subjects_dir, '*', '*.amc'))):
        b = os.path.basename(amc)[:-4]
        m = re.fullmatch(r'(\d+)_(\d+)', b)
        if not m:
            continue
        subj, trial = int(m.group(1)), int(m.group(2))
        if only and f'{subj:02d}_{trial:02d}' not in only and b not in only:
            continue
        sd = os.path.dirname(amc)
        asfs = glob.glob(os.path.join(sd, '*.asf'))
        if len(asfs) != 1:
            raise RuntimeError(f'{sd}: expected one asf, found {asfs}')
        s = S.get(str(subj))
        tinfo = s['trials'].get(str(trial)) if s else None
        if tinfo:
            desc, fps, fps_assumed = tinfo['desc'] or 'unknown', tinfo['fps'] or DEFAULT_FPS, tinfo['fps'] is None
        else:
            desc, fps, fps_assumed = 'unknown', DEFAULT_FPS, True
        if s and s['desc']:
            cat = s['desc']
        else:
            hdr = ''
            with open(amc, encoding='latin-1') as fh:
                first = fh.readline().strip()
            if first.startswith('#!OML:ASF'):
                hdr = first[len('#!OML:ASF'):].strip()
            cat = f'unlisted in CMU index; AMC header source path: {hdr}' if hdr else 'unlisted in CMU index'
        jobs.append((asfs[0], amc, subj, trial, fps, fps_assumed, desc, cat))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('subjects_dir')
    ap.add_argument('index')
    ap.add_argument('out')
    ap.add_argument('--workers', type=int, default=24)
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    index = json.load(open(a.index))
    only = set(x for x in a.only.split(',') if x)
    jobs = build_jobs(a.subjects_dir, index, only or None)
    print(f'{len(jobs)} trials to convert', flush=True)
    n_poses, errs, n_trials, heights = 0, [], 0, []
    tmp = a.out + '.partial'
    with open(tmp, 'w') as out, Pool(a.workers) as pool:
        for i, res in enumerate(pool.imap(process_trial, jobs, chunksize=2)):
            if res['err']:
                errs.append(res['err'])
            if res['recs']:
                n_trials += 1
                heights.append(res['height_m'])
            for r in res['recs']:
                out.write(json.dumps(r, separators=(',', ':')) + '\n')
            n_poses += len(res['recs'])
            if (i + 1) % 200 == 0:
                print(f'  {i + 1}/{len(jobs)} trials, {n_poses} poses, {len(errs)} errors', flush=True)
    os.replace(tmp, a.out)
    print(f'done: {n_trials} trials with poses, {n_poses} poses, {len(errs)} errors')
    if heights:
        print(f'skeleton height proxy (m): median {np.median(heights):.3f}, min {min(heights):.3f}, max {max(heights):.3f}')
    for e in errs:
        print('ERROR', e)


if __name__ == '__main__':
    main()

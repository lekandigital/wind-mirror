"""QA for the CMU pose set: contact sheets (drawn with bodies.joints), numeric checks, left/right checks, torso_up checks.

Usage: python qa.py <out dir (cmu_all.jsonl etc.)> <CMU subjects dir> <extra subjects dir (subject 144 for the arm check)>
Writes <out dir>/qa/*.png and <out dir>/qa/qa_report.json, prints a summary.
"""
import sys, os, re, json, glob
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'windtunnel'))
import bodies
import asfamc
import convert

LEFT, RIGHT, MID = '#1f5fd1', '#d62728', '#222222'
SEGS = [('pelvis', 'neck', MID), ('neck', 'head', MID), ('neck', 'shL', LEFT), ('neck', 'shR', RIGHT),
        ('pelvis', 'hipL', LEFT), ('pelvis', 'hipR', RIGHT)]
for s, c in (('L', LEFT), ('R', RIGHT)):
    SEGS += [('sh' + s, 'el' + s, c), ('el' + s, 'wr' + s, c), ('wr' + s, 'hand' + s, c),
             ('hip' + s, 'kn' + s, c), ('kn' + s, 'an' + s, c), ('an' + s, 'toe' + s, c)]


def load(path):
    return [json.loads(l) for l in open(path)]


def draw_pose(ax, pose_list, side_off=1.25):
    """Front view (from upwind, looking down +x): screen right = world -y = the person's LEFT.
    Side view (from the person's left, looking along +y), shifted right by side_off: screen right = world +x (downwind),
    so a person facing the wind faces screen-left."""
    P = bodies.pose_from_list(pose_list)
    J = bodies.joints(P)
    t = bodies.unit(P['t'])
    fwd = np.cross(bodies.hip_line(P), t)
    zmin = min(v[2] for v in J.values())
    for view in (0, 1):
        def uv(p):
            return (-p[1], p[2]) if view == 0 else (p[0] + side_off, p[2])
        for a, b, c in SEGS:
            (u0, v0), (u1, v1) = uv(J[a]), uv(J[b])
            ax.plot([u0, u1], [v0, v1], color=c, lw=1.4, solid_capstyle='round')
        hu, hv = uv(J['head'])
        ax.add_patch(plt.Circle((hu, hv), 0.1, fill=False, color=MID, lw=1.0))
        nu, nv = uv(J['head'] + 0.13 * fwd)
        ax.plot([hu, nu], [hv, nv], color='#2a9d2a', lw=1.2)          # green tick = facing direction
    ax.plot([-0.6, side_off + 0.6], [zmin, zmin], color='#999999', lw=0.6, ls='--')
    ax.set_xlim(-1.05, side_off + 1.05)
    ax.set_ylim(-1.3, 1.3)
    ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([])


def sheet(recs, title, path, cols=8, rows=6):
    fig, axs = plt.subplots(rows, cols, figsize=(cols * 2.5, rows * 1.95 + 0.6))
    for k, ax in enumerate(axs.flat):
        if k >= len(recs):
            ax.axis('off'); continue
        r = recs[k]
        draw_pose(ax, r['pose'])
        ax.set_title(f"{r['desc'][:34]}\n{r['id']} tu={r['torso_up']:.2f}{' FB' if r['heading_fallback'] else ''}", fontsize=5.5, pad=1.5)
    fig.suptitle(title + '\nEach cell: FRONT view from upwind (person faces you; their LEFT = blue appears on the RIGHT)  |  '
                 'SIDE view from the person\'s left (wind blows left->right; facing the wind = facing left). '
                 'Green tick = facing direction cross(lh, t). Grey dash = lowest joint. FB = heading fallback.', fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(path, dpi=90)
    plt.close(fig)


def trial_full(subdir, subj, trial):
    """All frames of a trial: canonical (F,12,3) poses with the same heading rules as convert.py."""
    asf = glob.glob(os.path.join(subdir, '*.asf'))[0]
    sk = asfamc.Skeleton(asf)
    frames, mot = asfamc.read_amc(os.path.join(subdir, f'{subj:02d}_{trial:02d}.amc'), sk)
    W = asfamc.to_world(asfamc.fk(sk, mot))
    V = convert.vectors(W)
    psi, ok, hn = convert.headings(W)
    F = len(frames)
    last = np.maximum.accumulate(np.where(ok, np.arange(F), -1))
    nxt = np.where(ok)[0]
    use = np.where(last >= 0, last, nxt[0] if len(nxt) else 0)
    hd = psi[use] if len(nxt) else np.zeros(F)
    Rm = convert.rotz_deg(-hd)                               # (F,3,3)
    Vc = np.einsum('fij,fkj->fki', Rm, V)
    hip_raw_c = np.einsum('fij,fj->fi', Rm, W['lhipjoint'] - W['rhipjoint'])
    return dict(frames=frames, W=W, V=V, Vc=Vc, heading=hd, fallback=~ok, hip_raw_c=hip_raw_c, sk=sk)


def mannequin_joints(Vc):
    return [bodies.joints(bodies.pose_from_list(v.tolist())) for v in Vc]


def main():
    out, subjects, extra = sys.argv[1], sys.argv[2], sys.argv[3]
    qa = os.path.join(out, 'qa'); os.makedirs(qa, exist_ok=True)
    idx = json.load(open(os.path.join(out, 'cmu_index.json')))['subjects']
    fps_of = lambda s, t: (idx.get(str(s), {}).get('trials', {}).get(str(t), {}) or {}).get('fps') or 120
    allr = load(os.path.join(out, 'cmu_all.jsonl'))
    div = load(os.path.join(out, 'cmu_diverse_4000.jsonl'))
    rnd = load(os.path.join(out, 'cmu_random_4000.jsonl'))
    rep = {}
    rng = np.random.default_rng(1)

    # ---- 1. numeric integrity -------------------------------------------------------------------------------------
    def integrity(recs):
        P = np.array([r['pose'] for r in recs], float)          # (N,12,3)
        n = np.linalg.norm(P, axis=-1)
        t, l, lh = P[:, 0], P[:, 1], P[:, 11]
        return dict(n=len(recs), shape=list(P.shape), nan=int(np.isnan(P).sum()), inf=int(np.isinf(P).sum()),
                    max_unit_err=float(np.abs(n - 1).max()), max_abs_l_dot_t=float(np.abs((l * t).sum(1)).max()),
                    max_abs_lh_dot_t=float(np.abs((lh * t).sum(1)).max()),
                    max_torso_up_mismatch=float(np.abs(P[:, 0, 2] - np.array([r['torso_up'] for r in recs])).max()),
                    other_nonfinite_fields=int(sum(1 for r in recs for k in ('heading_deg', 'pelvis_h', 't', 'torso_up') if not np.isfinite(r[k]))))
    rep['integrity'] = {k: integrity(v) for k, v in (('all', allr), ('diverse', div), ('random', rnd))}
    ids = [r['id'] for r in allr]
    rep['integrity']['unique_ids'] = len(set(ids)) == len(ids)
    rep['integrity']['subsets_disjoint'] = not (set(r['idx'] for r in div) & set(r['idx'] for r in rnd))
    rep['integrity']['subset_lines_match_all'] = all(allr[r['idx']]['id'] == r['id'] and allr[r['idx']]['pose'] == r['pose'] for r in div + rnd)
    rep['integrity']['subset_sizes'] = [len(div), len(set(r['idx'] for r in div)), len(rnd), len(set(r['idx'] for r in rnd))]
    nfb = [r for r in allr if not r['heading_fallback']]
    # for non-fallback poses, the shoulder line is roughly lateral: canonical l should point to -y on average
    L = np.array([r['pose'][1] for r in nfb]); LH = np.array([r['pose'][11] for r in nfb])
    rep['integrity']['nonfallback_mean_l'] = L.mean(0).round(4).tolist()
    rep['integrity']['nonfallback_mean_lh'] = LH.mean(0).round(4).tolist()
    rep['integrity']['nonfallback_frac_lh_y_negative'] = float((LH[:, 1] < 0).mean())
    # facing direction (belly) = cross(lh, t): upright poses should face -x; inverted poses face +x under the hip-line rule
    P = np.array([r['pose'] for r in allr], float)
    fw = np.cross(P[:, 11], P[:, 0])
    tu_all = P[:, 0, 2]
    for name, m in (('upright_tu_gt_0p7', tu_all > 0.7), ('inverted_tu_lt_m0p5', tu_all < -0.5)):
        rep['integrity'][f'mean_facing_{name}'] = dict(n=int(m.sum()), mean_cross_lh_t=fw[m].mean(0).round(3).tolist(),
                                                       frac_facing_minus_x=float((fw[m][:, 0] < 0).mean()))

    # ---- 2. re-derivation check on random trials: stored poses == recomputed; raw hip line canonical along -y --------
    trial_keys = sorted(set((r['subject'], r['trial']) for r in allr))
    pick = [trial_keys[i] for i in rng.choice(len(trial_keys), 25, replace=False)]
    by_trial = {}
    for i, r in enumerate(allr):
        by_trial.setdefault((r['subject'], r['trial']), []).append(r)
    maxdiff, hip_ang_err = 0.0, 0.0
    for s, t in pick:
        T = trial_full(os.path.join(subjects, f'{s:02d}'), s, t)
        fr = list(T['frames'])
        for r in by_trial[(s, t)]:
            f = fr.index(r['frame'])
            maxdiff = max(maxdiff, float(np.abs(T['Vc'][f] - np.array(r['pose'])).max()))
            if not r['heading_fallback']:
                hv = T['hip_raw_c'][f]
                hip_ang_err = max(hip_ang_err, abs(np.degrees(np.arctan2(hv[1], hv[0])) + 90.0))
    rep['rederive'] = dict(trials=[f'{s:02d}_{t:02d}' for s, t in pick], max_abs_diff_stored_vs_recomputed=maxdiff,
                           max_raw_hip_angle_err_deg_nonfallback=hip_ang_err)

    # ---- 3. contact sheets ------------------------------------------------------------------------------------------
    rs = [rnd[i] for i in sorted(rng.choice(len(rnd), 48, replace=False))]
    sheet(rs, 'cmu_random_4000: 48 random poses', os.path.join(qa, 'sheet_random.png'))
    sheet(div[:48], 'cmu_diverse_4000: first 48 (farthest-point order, #0 = start pose nearest bodies standing)', os.path.join(qa, 'sheet_diverse_first48.png'))
    rep['sheets'] = {}
    for kw in ('walk', 'cartwheel', 'sit', 'jump'):
        cand = [r for r in allr if re.search(kw, r['desc'], re.I)]
        ch = sorted(rng.choice(len(cand), min(48, len(cand)), replace=False))
        sheet([cand[i] for i in ch], f'cmu_all poses from trials whose description contains "{kw}" ({len(cand)} poses; 48 random shown, sorted by id)',
              os.path.join(qa, f'sheet_{kw}.png'))
        rep['sheets'][kw] = dict(n_candidates=len(cand), n_trials=len(set((r['subject'], r['trial']) for r in cand)),
                                 torso_up_min=min(r['torso_up'] for r in cand), frac_torso_up_gt_0p9=float(np.mean([r['torso_up'] > 0.9 for r in cand])))

    # ---- 4. left/right checks ---------------------------------------------------------------------------------------
    lr = {}
    # 4a. "Hop on left foot" (132_23..28): the right foot is held up, so the right ankle should be higher than the left.
    hop = []
    hop_sheet = []
    for t in range(23, 29):
        T = trial_full(os.path.join(subjects, '132'), 132, t)
        Jm = mannequin_joints(T['Vc'])
        aL = np.array([j['anL'][2] for j in Jm]); aR = np.array([j['anR'][2] for j in Jm])
        # mocap ankle heights too (end of tibia), independent of the mannequin
        mL, mR = T['W']['ltibia'][:, 2], T['W']['rtibia'][:, 2]
        hop.append(dict(trial=f'132_{t}', frames=len(aL), frac_right_ankle_higher_mannequin=float((aR > aL).mean()),
                        mean_right_minus_left_ankle_m_mannequin=float((aR - aL).mean()),
                        frac_right_ankle_higher_mocap=float((mR > mL).mean()), mean_right_minus_left_ankle_m_mocap=float((mR - mL).mean())))
        for f in np.linspace(30, len(aL) - 31, 8).astype(int):
            hop_sheet.append(dict(pose=T['Vc'][f].tolist(), desc='Hop on left foot', id=f's132_t{t}_f{T["frames"][f]}',
                                  torso_up=float(T['Vc'][f][0][2]), heading_fallback=bool(T['fallback'][f])))
    lr['hop_on_left_foot'] = hop
    sheet(hop_sheet, 'Left/right check: 132_23..28 "Hop on left foot" (8 frames per trial). Expect the RED (right) foot off the ground, BLUE (left) foot planted.',
          os.path.join(qa, 'lr_hop_on_left_foot.png'))
    # 4b. Arms: subject 144 (fetched only for this check; not in the 2007 zip): Left_Blocks (144_07), Right_Blocks (144_26),
    #     Left_Punch_Sequence001 (144_13). Measure each wrist's motion (mocap, relative to the pelvis, canonical frame).
    arms = []
    fig, axs = plt.subplots(1, 3, figsize=(15, 3.6))
    for ax, (t, name) in zip(axs, ((7, 'Left_Blocks'), (26, 'Right_Blocks'), (13, 'Left_Punch_Sequence001'))):
        T = trial_full(os.path.join(extra, '144'), 144, t)
        Jm = mannequin_joints(T['Vc'])
        wL = np.array([j['wrL'] for j in Jm]); wR = np.array([j['wrR'] for j in Jm])
        fwdL, fwdR = -wL[:, 0], -wR[:, 0]                                     # forward = -x in the canonical frame
        pathL = float(np.linalg.norm(np.diff(wL, axis=0), axis=1).sum()); pathR = float(np.linalg.norm(np.diff(wR, axis=0), axis=1).sum())
        stdL = float(wL.std(0).sum()); stdR = float(wR.std(0).sum())
        arms.append(dict(trial=f'144_{t:02d}', desc=name, wrist_path_m_L=round(pathL, 2), wrist_path_m_R=round(pathR, 2),
                         wrist_pos_std_sum_L=round(stdL, 3), wrist_pos_std_sum_R=round(stdR, 3),
                         wrist_max_forward_m_L=round(float(fwdL.max()), 3), wrist_max_forward_m_R=round(float(fwdR.max()), 3),
                         wrist_max_height_m_L=round(float(wL[:, 2].max()), 3), wrist_max_height_m_R=round(float(wR[:, 2].max()), 3)))
        tt = (T['frames'] - T['frames'][0]) / 120.0
        ax.plot(tt, wL[:, 2], color=LEFT, label='left wrist z (wrL)'); ax.plot(tt, wR[:, 2], color=RIGHT, label='right wrist z (wrR)')
        ax.plot(tt, fwdL, color=LEFT, ls=':', label='left wrist forward (-x)'); ax.plot(tt, fwdR, color=RIGHT, ls=':', label='right wrist forward (-x)')
        ax.set_title(f'144_{t:02d} "{name}"', fontsize=9); ax.set_xlabel('s (120 fps assumed: 144 is listed at 120)'); ax.set_ylabel('m, mannequin, pelvis origin')
    axs[0].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(qa, 'lr_arms_144.png'), dpi=90); plt.close(fig)
    lr['arms_subject144'] = arms

    # ---- 5. chirality from walking direction (label-independent): forward = cross(lh, t) vs root velocity ------------
    walk_trials = sorted(set((r['subject'], r['trial'], r['desc']) for r in allr if re.search(r'\bwalk', r['desc'], re.I)))
    res = []
    for s, t, d in walk_trials:
        T = trial_full(os.path.join(subjects, f'{s:02d}'), s, t)
        fps = fps_of(s, t)
        rp = T['W']['root'][:, :2]
        k = max(1, int(round(fps / 10)))                                          # velocity over 0.1 s
        vel = (rp[k:] - rp[:-k]) * fps / k
        lhw = convert.orth(T['W']['lhipjoint'] - T['W']['rhipjoint'], T['V'][:, 0])
        fw = np.cross(lhw, T['V'][:, 0])[:-k, :2]
        sp = np.linalg.norm(vel, axis=1)
        m = sp > 0.4
        if m.sum() < 10:
            continue
        c = (vel[m] * fw[m]).sum(1) / (sp[m] * np.maximum(np.linalg.norm(fw[m], axis=1), 1e-9))
        res.append(dict(trial=f'{s:02d}_{t:02d}', desc=d, mean_cos=float(c.mean()), backwards=bool(re.search(r'backward|back\b', d, re.I))))
    fwd_ok = [r for r in res if not r['backwards']]
    bwd = [r for r in res if r['backwards']]
    lr['walk_direction'] = dict(
        n_trials=len(res), n_forward_desc=len(fwd_ok), n_backward_desc=len(bwd),
        forward_desc_frac_mean_cos_gt_0p5=float(np.mean([r['mean_cos'] > 0.5 for r in fwd_ok])),
        forward_desc_median_mean_cos=float(np.median([r['mean_cos'] for r in fwd_ok])),
        backward_desc=[(r['trial'], r['desc'], round(r['mean_cos'], 3)) for r in bwd],
        forward_desc_worst=[(r['trial'], r['desc'], round(r['mean_cos'], 3)) for r in sorted(fwd_ok, key=lambda r: r['mean_cos'])[:12]])
    rep['left_right'] = lr

    # ---- 6. torso_up: a walking trial and cartwheel trials at full frame rate ---------------------------------------
    tu = {}
    fig, axs = plt.subplots(1, 2, figsize=(15, 3.8))
    T = trial_full(os.path.join(subjects, '02'), 2, 1)
    tt = (T['frames'] - 1) / 120.0
    axs[0].plot(tt, T['Vc'][:, 0, 2], color=MID)
    samp = by_trial[(2, 1)]
    axs[0].plot([r['t'] for r in samp], [r['torso_up'] for r in samp], 'o', color='#e08a00', label='sampled poses (2/s)')
    axs[0].set_ylim(-1.05, 1.05); axs[0].axhline(0, color='#aaa', lw=0.5); axs[0].set_title('02_01 "walk": torso_up = t_z'); axs[0].legend(fontsize=7)
    tu['walk_02_01'] = dict(min_full=float(T['Vc'][:, 0, 2].min()), max_full=float(T['Vc'][:, 0, 2].max()),
                            sampled=[round(r['torso_up'], 3) for r in samp])
    walk_prim = np.array([r['torso_up'] for r in allr if r['desc'].strip().lower() in ('walk', 'walking')])
    tu['all_trials_desc_exactly_walk'] = dict(n=len(walk_prim), min=float(walk_prim.min()), frac_gt_0p9=float((walk_prim > 0.9).mean()))
    cw = sorted(set((r['subject'], r['trial'], r['desc']) for r in allr if re.search('cartwheel', r['desc'], re.I)))
    tu['cartwheel_trials'] = []
    for s, t, d in cw:
        T = trial_full(os.path.join(subjects, f'{s:02d}'), s, t)
        fps = fps_of(s, t)
        tt = (T['frames'] - T['frames'][0]) / fps
        z = T['Vc'][:, 0, 2]
        samp = by_trial[(s, t)]
        axs[1].plot(tt, z, lw=1, label=f'{s:02d}_{t:02d} {d[:28]}')
        tu['cartwheel_trials'].append(dict(trial=f'{s:02d}_{t:02d}', desc=d, min_full=round(float(z.min()), 3),
                                           frac_frames_lt0=round(float((z < 0).mean()), 3), frac_frames_fallback=round(float(T['fallback'].mean()), 3),
                                           sampled_min=round(min(r['torso_up'] for r in samp), 3), n_sampled=len(samp),
                                           n_sampled_lt0=sum(r['torso_up'] < 0 for r in samp)))
    axs[1].set_ylim(-1.05, 1.05); axs[1].axhline(0, color='#aaa', lw=0.5); axs[1].legend(fontsize=6, ncol=2)
    axs[1].set_title('cartwheel trials: torso_up at full frame rate'); axs[1].set_xlabel('s')
    fig.tight_layout(); fig.savefig(os.path.join(qa, 'torso_up_walk_cartwheel.png'), dpi=90); plt.close(fig)
    rep['torso_up'] = tu

    json.dump(rep, open(os.path.join(qa, 'qa_report.json'), 'w'), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main()

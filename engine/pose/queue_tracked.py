"""Turn pose logs from the demo page (web/tests/trackdump.mjs) into solver queues.

 uniform  about 60 evenly spaced poses per clip
 dense    8 poses a second over chosen time windows (single moves), for the 'learn a move from a few solver runs' experiment
Clips are split into DEV (may be used for training and tuning) and SEALED (only for the fresh test of model B).
Usage: python queue_tracked.py <tracked_dir> <out_dir>
"""
import sys, json, os

DEV = ['fly', 'puppet', 'fx_crouch_stand', 'fx_lean_lr', 'fx_arms_tpose']
SEALED = ['row', 'fx_fullbody', 'fx_lean_fb', 'fx_seated', 'fx_rowing_slow', 'fx_arms', 'fx_torso']
DENSE = {'fly': [(19.0, 24.5)], 'puppet': [(14.0, 18.8)], 'fx_crouch_stand': [(8.0, 16.0)], 'fx_lean_fb': [(10.0, 17.0)], 'fx_seated': [(20.0, 26.0)]}
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)


def item(clip, i, r, kind):
    return dict(qid=f'trk_{clip}_{i:05d}', source='tracked', family='trk:' + clip, kind=kind, clip=clip, t=round(r['t'], 3), legW=round(r.get('legW', 1.0), 3),
                vis=r.get('vis'), pose=r['pose'], body=None)


for name, clips in (('dev', DEV), ('sealed', SEALED)):
    uni, dense = [], []
    for c in clips:
        p = f'{src}/{c}.json'
        if not os.path.exists(p):
            print('missing', p); continue
        L = json.load(open(p))
        L = [r for r in L if r['t'] > 0.4]
        step = max(len(L) // 60, 1)
        picked = set(range(step // 2, len(L), step))
        uni += [item(c, i, L[i], 'uniform') for i in sorted(picked)]
        for a, b in DENSE.get(c, []):
            last = -1.0
            for i, r in enumerate(L):
                if a <= r['t'] <= b and r['t'] - last >= 0.125 and i not in picked:
                    dense.append(item(c, i, r, 'dense')); last = r['t']
    for kind, items in (('uniform', uni), ('dense', dense)):
        with open(f'{out}/queue_trk_{name}_{kind}.jsonl', 'w') as f:
            for it in items:
                f.write(json.dumps(it) + '\n')
        print(name, kind, len(items))

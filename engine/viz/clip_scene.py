"""Build Blender scene files for the clip key frames that have saved 3D fields."""
import sys, json, glob, os
import numpy as np
sys.path.insert(0, '../windtunnel')
import bodies as B
from streamlines import build

clip = sys.argv[1]                      # e.g. ../out/clip_fly
field = sys.argv[2] if len(sys.argv) > 2 else 'vavg'
recs = {json.loads(l)['k']: json.loads(l) for l in open(f'{clip}/forces.jsonl')}
for p in sorted(glob.glob(f'{clip}/field_*.npz')):
    k = int(os.path.basename(p)[6:9])
    if k not in recs:
        continue
    r = recs[k]
    pose = B.pose_from_list(r['pose'])
    parts = {n: float(np.array(r['F_parts'])[i, 0] * r['corr']) for i, n in enumerate(B.PARTS)}
    sc = build(p, pose, f'{clip}/scene_{k:03d}_{field}.json', field=field, extra=dict(part_drag=parts, CdA=r['CdA'], frame=r['frame'], t=r['t'], area=r['area_m2']))
    print(k, r['frame'], round(r['CdA'], 3), len(sc['lines']))

"""Build a scene of many mannequins (the 'thousand at once' picture) from thousand.py output.
Usage: grid_scene.py <thousand.json> <out_scene.json> [n_cols n_rows]"""
import sys, json
import numpy as np
sys.path.insert(0, '../windtunnel')
import bodies as B

d = json.load(open(sys.argv[1]))
nc = int(sys.argv[3]) if len(sys.argv) > 3 else 16
nr = int(sys.argv[4]) if len(sys.argv) > 4 else 9
items = []
for i in range(nc * nr):
    pose = B.pose_from_list(d['poses'][i])
    J = B.joints(pose); caps = B.capsules(J, pose)
    zmin = min(min(a[2], b[2]) - r for a, b, r, _ in caps)
    off = np.array([(i // nc) * 2.3, (i % nc - (nc - 1) / 2) * 1.45, -zmin])
    items.append(dict(sure=bool(d['sure'][i]), CdA=d['CdA'][i], caps=[dict(a=(a + off).tolist(), b=(b + off).tolist(), r=float(r)) for a, b, r, _ in caps],
                      base=[float(off[0]), float(off[1])]))
json.dump(dict(items=items, nc=nc, nr=nr), open(sys.argv[2], 'w'))
print(len(items), 'bodies;', sum(it['sure'] for it in items), 'sure')

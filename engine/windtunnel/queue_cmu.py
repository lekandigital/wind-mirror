"""Turn CMU motion-capture poses (out/mocap/*.jsonl, made by engine/mocap/) into solver queues.
Each pose gets a heading (60%: roughly facing the wind; 40%: any heading) and, half the time, a random body shape.
Usage: python queue_cmu.py <cmu_subset.jsonl> <out_queue.jsonl> <source_label> <n> [seed]"""
import sys, json
import numpy as np
import bodies as B

src, out, label, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
seed = int(sys.argv[5]) if len(sys.argv) > 5 else 31000
rows = [json.loads(l) for l in open(src)][:n]
with open(out, 'w') as f:
    for i, r in enumerate(rows):
        rng = np.random.default_rng(seed + i)
        yaw = float(np.clip(rng.normal(0, 20), -50, 50)) if rng.random() < 0.6 else float(rng.uniform(-180, 180))
        R = B.rotz(np.deg2rad(yaw))
        pose = [[float(x) for x in R @ np.asarray(v, float)] for v in r['pose']]
        body = B.sample_shape(rng) if rng.random() < 0.5 else None
        up = float(r['torso_up'])
        posture = 'upright' if up >= 0.5 else ('low' if up >= 0.0 else 'inverted')
        f.write(json.dumps(dict(qid=f'{label}_{r["id"]}', source=label, family='cmu:' + str(r.get('coarse', 'other')), posture=posture, torso_up=up, yaw_deg=yaw,
                                desc=r.get('desc', ''), pose=pose, body=body)) + '\n')
print('wrote', len(rows), 'to', out)

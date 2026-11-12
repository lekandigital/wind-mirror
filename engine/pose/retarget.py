"""MediaPipe world landmarks -> the tunnel's 11 bone directions. She faces the camera; the wind comes from the camera."""
import sys, json
import numpy as np
sys.path.insert(0, 'windtunnel')
import bodies as B

M = np.array([[0, 0, 1.0], [-1.0, 0, 0], [0, -1.0, 0]])     # mediapipe (x right, y down, z away) -> world (x downwind, y, z up)

def smooth(a, k=7):
    ker = np.hanning(k + 2)[1:-1]; ker /= ker.sum()
    pad = k // 2
    ap = np.concatenate([np.repeat(a[:1], pad, 0), a, np.repeat(a[-1:], pad, 0)], 0)
    return np.stack([np.convolve(ap[:, j], ker, mode='valid') for j in range(a.shape[1])], 1)

def retarget(world):
    """world: (T, 33, 3) -> list of pose dicts."""
    T = world.shape[0]
    w = smooth(world.reshape(T, -1)).reshape(T, 33, 3) @ M.T
    poses = []
    for f in range(T):
        p = w[f]
        pel, neck = (p[23] + p[24]) / 2, (p[11] + p[12]) / 2
        t = B.unit(neck - pel)
        l = B.unit(p[11] - p[12]); l = B.unit(l - np.dot(l, t) * t)
        h = B.unit((p[7] + p[8]) / 2 - neck)
        poses.append(dict(t=t, l=l, h=h, uaL=B.unit(p[13] - p[11]), faL=B.unit(p[15] - p[13]), uaR=B.unit(p[14] - p[12]), faR=B.unit(p[16] - p[14]),
                          thL=B.unit(p[25] - p[23]), shL=B.unit(p[27] - p[25]), thR=B.unit(p[26] - p[24]), shR=B.unit(p[28] - p[26])))
    return poses

if __name__ == '__main__':
    d = np.load(sys.argv[1])
    poses = retarget(d['world'])
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    out = [dict(frame=i, t=i / float(d['fps']), pose=B.pose_to_list(poses[i]), feat=[float(x) for x in B.features(poses[i])]) for i in range(0, len(poses), step)]
    json.dump(out, open(sys.argv[2], 'w'))
    print(len(out), 'poses written')

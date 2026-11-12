"""Run MediaPipe Pose (the same model family BodyArcade uses) on a recorded clip; save 3D world landmarks per frame."""
import sys, json
import numpy as np, cv2
import mediapipe as mp
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision

video, out = sys.argv[1], sys.argv[2]
model = '/Users/lekan/Dev/posepuppet/public/models/pose_landmarker_full.task'
opts = vision.PoseLandmarkerOptions(base_options=mpp.BaseOptions(model_asset_path=model), running_mode=vision.RunningMode.VIDEO, num_poses=1)
cap = cv2.VideoCapture(video)
fps = cap.get(cv2.CAP_PROP_FPS)
W, Hh = int(cap.get(3)), int(cap.get(4))
world, image, vis = [], [], []
with vision.PoseLandmarker.create_from_options(opts) as lm:
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        r = lm.detect_for_video(img, int(i * 1000 / fps))
        if r.pose_world_landmarks:
            wl = r.pose_world_landmarks[0]; il = r.pose_landmarks[0]
            world.append([[p.x, p.y, p.z] for p in wl]); image.append([[p.x, p.y] for p in il]); vis.append([p.visibility for p in wl])
        else:
            world.append([[np.nan] * 3] * 33); image.append([[np.nan] * 2] * 33); vis.append([0.0] * 33)
        i += 1
np.savez_compressed(out, world=np.array(world, np.float32), image=np.array(image, np.float32), vis=np.array(vis, np.float32), fps=fps, size=[W, Hh])
print('frames', len(world), 'fps', fps, 'size', W, Hh, 'missing', int(np.isnan(np.array(world)[:, 0, 0]).sum()))

# Side outline of the Tatra 87 for scripts/3d/lod_check.py --ref, from the oblique photo (GRAFIK#72, free):
#   python docs/spikes/2026-10-31-tatra-silueta.py library/3d/tatra87-hunyuan3d/predloha-left.png out.png
# Straightens the side plane by a homography from the wheels (axles and ends at the positions in lod_tatra87.py DIM,
# rear wheel scale from a 1-D fit along the length), then sets the height to 1.50 / 4.74: the photo overstates it.
# The outline is approximate (roof line on the centre plane, not the wheel plane): for comparing models, not for metres.
import sys

import cv2
import numpy as np

img = cv2.imread(sys.argv[1], cv2.IMREAD_UNCHANGED)
mask = (cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY) < 245).astype(np.uint8)
n, lab, st, _ = cv2.connectedComponentsWithStats(mask)
mask = (lab == 1 + np.argmax(st[1:, 4])).astype(np.uint8)
ys, xs = np.where(mask)
X = np.array([0, 0.8, 3.65, 4.74])                  # nose, axles, tail in metres
U = np.array([xs.min(), 250, 912, xs.max()], float)  # the same in photo pixels (hub and ground contact read by eye)
a, b, g = np.linalg.lstsq(np.c_[X, np.ones(4), -X * U], U, rcond=None)[0]
front = (516 - 418) / 0.36                           # px per metre: front wheel, hub to ground, radius 0.36 m
rear = front * (g * 0.8 + 1) / (g * 3.65 + 1)
K = 250                                              # px per metre of the result
src = np.float32([[250, 516], [252, 418], [912, 418], [916, 418 - 0.36 * rear]])
dst = np.float32([[0.8 * K + 40, 600], [0.8 * K + 40, 600 - 0.36 * K], [3.65 * K + 40, 600], [3.65 * K + 40, 600 - 0.36 * K]])
H = cv2.getPerspectiveTransform(src, dst)
warped = (cv2.warpPerspective(mask * 255, H, (1300, 700)) > 127).astype(np.uint8)
n, lab, st, _ = cv2.connectedComponentsWithStats(warped)
warped = (lab == 1 + np.argmax(st[1:, 4])).astype(np.uint8)
ys, xs = np.where(warped)
out = np.dstack([cv2.warpPerspective(img[:, :, :3], H, (1300, 700)), warped * 255])
crop = out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
cv2.imwrite(sys.argv[2], cv2.resize(crop, (crop.shape[1], round(crop.shape[1] * 1.5 / 4.74)), interpolation=cv2.INTER_AREA))

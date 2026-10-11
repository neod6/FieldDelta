import time
import cv2
import numpy as np
from PIL import Image, ImageOps


def load_image(path, max_size=1600):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    image.thumbnail((max_size, max_size))
    return image


def warp_points(points, matrix):
    return cv2.perspectiveTransform(np.asarray(points, np.float32).reshape(-1, 1, 2),
                                    np.asarray(matrix, np.float64)).reshape(-1, 2)


def register(before, after):
    """Map AFTER normalized coordinates to BEFORE normalized coordinates."""
    started = time.perf_counter()
    old, new = np.asarray(before), np.asarray(after)
    h1, w1 = old.shape[:2]
    h2, w2 = new.shape[:2]
    sift = cv2.SIFT_create(nfeatures=5000)
    k1, d1 = sift.detectAndCompute(cv2.cvtColor(old, cv2.COLOR_RGB2GRAY), None)
    k2, d2 = sift.detectAndCompute(cv2.cvtColor(new, cv2.COLOR_RGB2GRAY), None)
    base = dict(status='REGISTRATION_UNCERTAIN', action='RESCAN_RECOMMENDED',
                method='SIFT_RATIO_RANSAC_HOMOGRAPHY', matches=0, inliers=0,
                inlier_ratio=0., median_reprojection_px=None, p90_reprojection_px=None,
                matrix=None, confidence='low', reliable=False)
    if d1 is None or d2 is None:
        return {**base, 'reason': 'Insufficient features', 'latency_seconds': time.perf_counter()-started}
    matches = cv2.BFMatcher().knnMatch(d2, d1, k=2)
    good = [pair[0] for pair in matches if len(pair)==2 and pair[0].distance < .72*pair[1].distance]
    base['matches'] = len(good)
    if len(good) < 12:
        return {**base, 'reason': 'Too few feature matches', 'latency_seconds': time.perf_counter()-started}
    src = np.float32([k2[m.queryIdx].pt for m in good])
    dst = np.float32([k1[m.trainIdx].pt for m in good])
    cv2.setRNGSeed(42)
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4., maxIters=4000, confidence=.995)
    if matrix is None:
        return {**base, 'reason': 'RANSAC failed', 'latency_seconds': time.perf_counter()-started}
    keep = mask.ravel().astype(bool)
    errors = np.linalg.norm(warp_points(src, matrix)-dst, axis=1)[keep]
    cells = {(min(int(x/w1*3),2), min(int(y/h1*3),2)) for x,y in dst[keep]}
    normalized = np.diag([1/w1, 1/h1, 1]) @ matrix @ np.diag([w2, h2, 1])
    normalized /= normalized[2,2]
    corners = warp_points([[0,0],[1,0],[1,1],[0,1]], normalized)
    area = abs(cv2.contourArea(corners.astype(np.float32)))
    inliers = int(keep.sum())
    ratio = inliers / len(good)
    median, p90 = float(np.median(errors)), float(np.percentile(errors,90))
    reliable = bool(inliers >= 30 and ratio >= .40 and median < 2.5 and p90 < 4.
                    and len(cells) >= 4 and .3 < area < 3
                    and np.isfinite(corners).all() and cv2.isContourConvex(corners.astype(np.float32)))
    return dict(status='REGISTERED' if reliable else 'REGISTRATION_UNCERTAIN',
                action=None if reliable else 'RESCAN_RECOMMENDED',
                method=base['method'], matches=len(good), inliers=inliers, inlier_ratio=ratio,
                median_reprojection_px=median, p90_reprojection_px=p90,
                occupied_grid_cells=len(cells), mapped_frame_area=area,
                matrix=normalized.tolist(), confidence='geometric_only' if reliable else 'low',
                reliable=reliable, latency_seconds=time.perf_counter()-started,
                limitation='One homography assumes approximately planar/static scene. Low RANSAC error is not physical ground-truth accuracy.')


def map_object(obj, registration):
    result = dict(obj)
    if registration['matrix'] is None:
        result['registered_center'] = obj['center']
        result['registered_bbox'] = obj['normalized_bbox']
        return result
    x1,y1,x2,y2 = obj['normalized_bbox']
    corners = warp_points([[x1,y1],[x2,y1],[x2,y2],[x1,y2]], registration['matrix'])
    center = warp_points([obj['center']], registration['matrix'])[0]
    result.update(registered_center=center.tolist(),
                  registered_bbox=[float(corners[:,0].min()),float(corners[:,1].min()),
                                   float(corners[:,0].max()),float(corners[:,1].max())])
    return result


def inside_roi(center, polygon):
    return cv2.pointPolygonTest(np.asarray(polygon,np.float32), tuple(map(float,center)), False) >= 0


def expected_in_view(obj, registration):
    if not registration['reliable']:
        return False
    x1,y1,x2,y2 = obj['normalized_bbox']
    points = warp_points([[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                         np.linalg.inv(registration['matrix']))
    return bool(((points >= .015) & (points <= .985)).all())

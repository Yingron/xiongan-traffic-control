import argparse
import json
import os
from typing import List, Dict, Tuple

import cv2
import numpy as np

# Note: Requires opencv-contrib-python so that cv2.ximgproc.thinning is available.


# ---------- IO helpers ----------
def read_image(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    return img


def save_image(path: str, img: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imencode('.png', img)[1].tofile(path)


def save_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)


# ---------- Preprocess ----------
def hsv_mask(img: np.ndarray, lower: List[int], upper: List[int]) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_arr = np.array(lower, dtype=np.uint8)
    upper_arr = np.array(upper, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_arr, upper_arr)
    return mask


def morph_cleanup(mask: np.ndarray, ksize: int = 7) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ksize, ksize))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
    return cleaned


def skeletonize(mask: np.ndarray) -> np.ndarray:
    # Ensure binary
    _, bw = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    skel = cv2.ximgproc.thinning(bw)
    return skel


# ---------- Skeleton to polylines (key points only) ----------
def douglas_peucker(points: List[Tuple[int, int]], eps: float) -> List[Tuple[int, int]]:
    if len(points) < 3:
        return points
    p0 = np.array(points[0], dtype=float)
    pN = np.array(points[-1], dtype=float)
    line = pN - p0
    line_len = np.hypot(line[0], line[1])
    if line_len == 0:
        dists = [np.hypot(*(np.array(p) - p0)) for p in points]
        idx = int(np.argmax(dists))
        if dists[idx] <= eps:
            return [points[0], points[-1]]
        left = douglas_peucker(points[: idx + 1], eps)
        right = douglas_peucker(points[idx:], eps)
        return left[:-1] + right
    dists = []
    for p in points:
        v = np.array(p, dtype=float) - p0
        area = abs(line[0] * v[1] - line[1] * v[0])
        dist = area / line_len
        dists.append(dist)
    idx = int(np.argmax(dists))
    if dists[idx] > eps:
        left = douglas_peucker(points[: idx + 1], eps)
        right = douglas_peucker(points[idx:], eps)
        return left[:-1] + right
    else:
        return [points[0], points[-1]]


def skeleton_to_graph(skel: np.ndarray):
    coords = np.argwhere(skel > 0)
    adj = { (int(y), int(x)): [] for y, x in coords }
    neighs = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    coord_set = set(adj.keys())
    for y, x in coords:
        for dy, dx in neighs:
            ny, nx = int(y + dy), int(x + dx)
            if (ny, nx) in coord_set:
                adj[(int(y), int(x))].append((ny, nx))
    return adj


def find_nodes(adj):
    endpoints = []
    junctions = []
    for p, nbrs in adj.items():
        d = len(nbrs)
        if d == 1:
            endpoints.append(p)
        elif d >= 3:
            junctions.append(p)
    return endpoints, junctions


def walk_path(adj, start, visited_global):
    path = [start]
    cur = start
    prev = None
    while True:
        nbrs = adj[cur]
        nexts = [n for n in nbrs if n != prev]
        if not nexts:
            break
        nxt = None
        for n in nexts:
            if n not in visited_global:
                nxt = n
                break
        if nxt is None:
            nxt = nexts[0]
        path.append(nxt)
        prev = cur
        cur = nxt
        if len(adj[cur]) != 2:
            break
    return path


def skeleton_to_polylines(skel: np.ndarray, simplify_eps: float = 2.0) -> List[List[Tuple[int, int]]]:
    adj = skeleton_to_graph(skel)
    endpoints, junctions = find_nodes(adj)
    visited = set()
    polylines: List[List[Tuple[int, int]]] = []

    # start from endpoints
    for ep in endpoints:
        if ep in visited:
            continue
        path = walk_path(adj, ep, visited)
        for p in path:
            visited.add(p)
        pts = [(int(x), int(y)) for (y, x) in path]
        if len(pts) >= 2:
            polylines.append(douglas_peucker(pts, simplify_eps))

    # then junction branches
    for j in junctions:
        for nbr in adj[j]:
            if j in visited and nbr in visited:
                continue
            path = walk_path(adj, nbr, visited)
            full = [j] + path
            for p in full:
                visited.add(p)
            pts = [(int(x), int(y)) for (y, x) in full]
            if len(pts) >= 2:
                polylines.append(douglas_peucker(pts, simplify_eps))

    return polylines


def pixel_to_unity(points: List[Tuple[int, int]], width: int, height: int, scale: float) -> List[Dict[str, float]]:
    # Map image coords to Unity XZ plane: center at (0,0), y = 0
    unity_pts = []
    for x, y in points:
        xn = x / width
        yn = (height - y) / height  # flip Y so image top -> positive Z
        ux = (xn - 0.5) * scale
        uz = (yn - 0.5) * scale
        unity_pts.append({"x": ux, "y": 0.0, "z": uz})
    return unity_pts


def main():
    parser = argparse.ArgumentParser(description="Extract road skeleton and lines using OpenCV.")
    parser.add_argument("input", help="Input image path")
    parser.add_argument("--mask_out", default="output/mask.png", help="Output mask path")
    parser.add_argument("--skeleton_out", default="output/skeleton.png", help="Output skeleton path")
    parser.add_argument("--polylines_out", default="output/polylines_pixels.json", help="Polyline keypoints in pixel coords")
    parser.add_argument("--polylines_unity_out", default="output/polylines_unity.json", help="Polyline keypoints mapped to Unity coords")

    parser.add_argument("--lower_hsv", nargs=3, type=int, default=[0, 0, 180],
                        help="Lower HSV threshold (H S V)")
    parser.add_argument("--upper_hsv", nargs=3, type=int, default=[180, 60, 255],
                        help="Upper HSV threshold (H S V)")
    parser.add_argument("--morph_ksize", type=int, default=7, help="Kernel size for morphology")
    parser.add_argument("--simplify_eps", type=float, default=2.0, help="Douglas-Peucker epsilon (pixels)")
    parser.add_argument("--unity_scale", type=float, default=1.0, help="Scale factor for Unity coordinates (applied after centering & normalization)")

    args = parser.parse_args()

    img = read_image(args.input)
    mask = hsv_mask(img, args.lower_hsv, args.upper_hsv)
    mask = morph_cleanup(mask, ksize=args.morph_ksize)
    skel = skeletonize(mask)
    polylines_px = skeleton_to_polylines(skel, simplify_eps=args.simplify_eps)

    h, w = skel.shape
    polylines_unity = []
    for pl in polylines_px:
        polylines_unity.append(pixel_to_unity(pl, w, h, args.unity_scale))

    save_image(args.mask_out, mask)
    save_image(args.skeleton_out, skel)
    save_json(args.polylines_out, polylines_px)
    save_json(args.polylines_unity_out, polylines_unity)

    print(f"Saved mask to {args.mask_out}")
    print(f"Saved skeleton to {args.skeleton_out}")
    print(f"Saved {len(polylines_px)} polylines to {args.polylines_out}")
    print(f"Saved Unity-ready polylines to {args.polylines_unity_out}")


if __name__ == "__main__":
    main()

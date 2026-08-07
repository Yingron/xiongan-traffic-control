import argparse
import json
import os
from typing import Dict, List, Tuple

import cv2
import numpy as np


def read_image(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    return img


def save_image(path: str, img: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imencode(".png", img)[1].tofile(path)


def save_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def hsv_mask(img: np.ndarray, lower: List[int], upper: List[int]) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_arr = np.array(lower, dtype=np.uint8)
    upper_arr = np.array(upper, dtype=np.uint8)
    return cv2.inRange(hsv, lower_arr, upper_arr)


def morph_cleanup(mask: np.ndarray, ksize: int = 7) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ksize, ksize))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
    return cleaned


def skeletonize(mask: np.ndarray) -> np.ndarray:
    _, bw = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return cv2.ximgproc.thinning(bw)


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
        dists.append(area / line_len)
    idx = int(np.argmax(dists))
    if dists[idx] > eps:
        left = douglas_peucker(points[: idx + 1], eps)
        right = douglas_peucker(points[idx:], eps)
        return left[:-1] + right
    return [points[0], points[-1]]


def resample_polyline(points: List[Tuple[int, int]], step: float) -> List[Tuple[int, int]]:
    if len(points) < 2 or step <= 0:
        return points
    pts = np.array(points, dtype=float)
    deltas = np.diff(pts, axis=0)
    seg_lens = np.hypot(deltas[:, 0], deltas[:, 1])
    total_len = float(np.sum(seg_lens))
    if total_len <= 0:
        return [points[0]]

    targets = [0.0]
    dist = step
    while dist < total_len:
        targets.append(dist)
        dist += step
    targets.append(total_len)

    resampled = []
    seg_index = 0
    seg_start = pts[0]
    seg_accum = 0.0
    for t in targets:
        while seg_index < len(seg_lens) and seg_accum + seg_lens[seg_index] < t:
            seg_accum += seg_lens[seg_index]
            seg_index += 1
            if seg_index < len(pts) - 1:
                seg_start = pts[seg_index]
        if seg_index >= len(seg_lens):
            resampled.append(pts[-1])
            break
        seg_len = seg_lens[seg_index]
        if seg_len <= 0:
            p = seg_start
        else:
            ratio = (t - seg_accum) / seg_len
            p = seg_start + ratio * (pts[seg_index + 1] - seg_start)
        resampled.append(p)

    out: List[Tuple[int, int]] = []
    for p in resampled:
        pi = (int(round(p[0])), int(round(p[1])))
        if not out or pi != out[-1]:
            out.append(pi)
    return out


def resample_polyline_to_n(points: List[Tuple[int, int]], n: int) -> List[Tuple[int, int]]:
    if len(points) < 2 or n <= 0:
        return points
    if n == 1:
        return [points[0]]
    pts = np.array(points, dtype=float)
    deltas = np.diff(pts, axis=0)
    seg_lens = np.hypot(deltas[:, 0], deltas[:, 1])
    total_len = float(np.sum(seg_lens))
    if total_len <= 0:
        return [points[0], points[-1]]

    targets = np.linspace(0.0, total_len, n)
    resampled = []
    seg_index = 0
    seg_start = pts[0]
    seg_accum = 0.0
    for t in targets:
        while seg_index < len(seg_lens) and seg_accum + seg_lens[seg_index] < t:
            seg_accum += seg_lens[seg_index]
            seg_index += 1
            if seg_index < len(pts) - 1:
                seg_start = pts[seg_index]
        if seg_index >= len(seg_lens):
            resampled.append(pts[-1])
            continue
        seg_len = seg_lens[seg_index]
        if seg_len <= 0:
            p = seg_start
        else:
            ratio = (t - seg_accum) / seg_len
            p = seg_start + ratio * (pts[seg_index + 1] - seg_start)
        resampled.append(p)

    out: List[Tuple[int, int]] = []
    for p in resampled:
        pi = (int(round(p[0])), int(round(p[1])))
        if not out or pi != out[-1]:
            out.append(pi)
    return out


def polyline_length(points: List[Tuple[int, int]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        total += float(np.hypot(dx, dy))
    return total


def skeleton_to_graph(skel: np.ndarray) -> Dict[Tuple[int, int], List[Tuple[int, int]]]:
    coords = np.argwhere(skel > 0)
    adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = {(int(y), int(x)): [] for y, x in coords}
    neighs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    coord_set = set(adj.keys())
    for y, x in coords:
        for dy, dx in neighs:
            ny, nx = int(y + dy), int(x + dx)
            if (ny, nx) in coord_set:
                adj[(int(y), int(x))].append((ny, nx))
    return adj


def prune_short_branches(adj: Dict[Tuple[int, int], List[Tuple[int, int]]], min_len: float) -> None:
    if min_len <= 0:
        return
    changed = True
    while changed:
        changed = False
        endpoints = [p for p, nbrs in adj.items() if len(nbrs) == 1]
        for ep in endpoints:
            if ep not in adj:
                continue
            path = [ep]
            cur = ep
            prev = None
            length = 0.0
            while True:
                nbrs = adj.get(cur, [])
                if len(nbrs) == 0:
                    break
                if len(nbrs) != 1 and cur != ep:
                    break
                nxt = nbrs[0]
                if nxt == prev:
                    break
                length += float(np.hypot(nxt[0] - cur[0], nxt[1] - cur[1]))
                path.append(nxt)
                prev = cur
                cur = nxt
                if len(adj.get(cur, [])) != 2:
                    break
                if length >= min_len:
                    break
            if length < min_len:
                for node in path:
                    for n in adj.get(node, []):
                        if n in adj:
                            adj[n] = [x for x in adj[n] if x != node]
                    if node in adj:
                        del adj[node]
                changed = True
                break


def trace_polylines(adj: Dict[Tuple[int, int], List[Tuple[int, int]]]) -> List[List[Tuple[int, int]]]:
    def edge_key(a, b):
        return (a, b) if a < b else (b, a)

    nodes = [p for p, nbrs in adj.items() if len(nbrs) != 2]
    visited_edges = set()
    paths: List[List[Tuple[int, int]]] = []

    for node in nodes:
        for nbr in adj.get(node, []):
            ek = edge_key(node, nbr)
            if ek in visited_edges:
                continue
            path = [node, nbr]
            visited_edges.add(ek)
            prev = node
            cur = nbr
            while len(adj.get(cur, [])) == 2:
                n0, n1 = adj[cur]
                nxt = n0 if n0 != prev else n1
                ek = edge_key(cur, nxt)
                if ek in visited_edges:
                    break
                visited_edges.add(ek)
                path.append(nxt)
                prev = cur
                cur = nxt
            paths.append(path)

    if not nodes and adj:
        start = next(iter(adj))
        nbr = adj[start][0]
        path = [start, nbr]
        visited_edges.add(edge_key(start, nbr))
        prev = start
        cur = nbr
        while True:
            nbrs = adj[cur]
            nxt = nbrs[0] if nbrs[0] != prev else nbrs[1]
            ek = edge_key(cur, nxt)
            if ek in visited_edges:
                break
            visited_edges.add(ek)
            path.append(nxt)
            prev = cur
            cur = nxt
        paths.append(path)

    return paths


def simplify_to_target_points(
    points: List[Tuple[int, int]],
    target_min: int,
    target_max: int,
    eps_start: float,
) -> List[Tuple[int, int]]:
    if len(points) < 2:
        return points
    target_min = max(2, int(target_min))
    target_max = max(target_min, int(target_max))

    simplified = douglas_peucker(points, eps_start)
    if target_min <= len(simplified) <= target_max:
        return simplified

    if len(simplified) > target_max:
        eps_low = 0.0
        eps_high = max(1.0, eps_start)
        max_len = polyline_length(points)
        while len(douglas_peucker(points, eps_high)) > target_max and eps_high < max_len:
            eps_low = eps_high
            eps_high *= 2.0
        for _ in range(12):
            mid = (eps_low + eps_high) / 2.0
            if len(douglas_peucker(points, mid)) > target_max:
                eps_low = mid
            else:
                eps_high = mid
        simplified = douglas_peucker(points, eps_high)

    if len(simplified) < target_min:
        return resample_polyline_to_n(points, target_min)
    if len(simplified) > target_max:
        return resample_polyline_to_n(points, target_max)
    return simplified


def skeleton_to_polylines(
    skel: np.ndarray,
    simplify_eps: float,
    resample_step: float,
    target_points_min: int,
    target_points_max: int,
    min_branch_len: float,
) -> List[List[Tuple[int, int]]]:
    adj = skeleton_to_graph(skel)
    prune_short_branches(adj, min_branch_len)
    paths = trace_polylines(adj)

    polylines: List[List[Tuple[int, int]]] = []
    for path in paths:
        pts = [(int(x), int(y)) for (y, x) in path]
        pts = resample_polyline(pts, resample_step)
        if len(pts) < 2:
            continue
        pts = simplify_to_target_points(pts, target_points_min, target_points_max, simplify_eps)
        if len(pts) >= 2:
            polylines.append(pts)
    return polylines


def pixel_to_unity(points: List[Tuple[int, int]], width: int, height: int, scale: float) -> List[Dict[str, float]]:
    unity_pts = []
    for x, y in points:
        xn = x / width
        yn = (height - y) / height
        ux = (xn - 0.5) * scale
        uz = (yn - 0.5) * scale
        unity_pts.append({"x": ux, "y": 0.0, "z": uz})
    return unity_pts


def extract(image_path: str, output_dir: str, params: Dict) -> Dict[str, str]:
    img = read_image(image_path)
    mask = hsv_mask(img, params["lower_hsv"], params["upper_hsv"])
    mask = morph_cleanup(mask, ksize=params["morph_ksize"])
    skel = skeletonize(mask)
    polylines_px = skeleton_to_polylines(
        skel,
        simplify_eps=params["simplify_eps"],
        resample_step=params["resample_step"],
        target_points_min=params["target_points_min"],
        target_points_max=params["target_points_max"],
        min_branch_len=params["min_branch_len"],
    )

    h, w = skel.shape
    polylines_unity = [pixel_to_unity(pl, w, h, params["unity_scale"]) for pl in polylines_px]
    roads_keypoints = [{"controlPoints": pl} for pl in polylines_unity]

    mask_path = os.path.join(output_dir, "mask.png")
    skel_path = os.path.join(output_dir, "skeleton.png")
    poly_px_path = os.path.join(output_dir, "polylines_pixels.json")
    poly_unity_path = os.path.join(output_dir, "polylines_unity.json")
    roads_keypoints_path = os.path.join(output_dir, "roads_keypoints.json")

    save_image(mask_path, mask)
    save_image(skel_path, skel)
    save_json(poly_px_path, polylines_px)
    save_json(poly_unity_path, polylines_unity)
    save_json(roads_keypoints_path, roads_keypoints)

    return {
        "mask": mask_path,
        "skeleton": skel_path,
        "polylines_pixels": poly_px_path,
        "polylines_unity": poly_unity_path,
        "roads_keypoints": roads_keypoints_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract road polylines with RDP simplification.")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--lower_hsv", nargs=3, type=int, default=[0, 0, 180])
    parser.add_argument("--upper_hsv", nargs=3, type=int, default=[180, 60, 255])
    parser.add_argument("--morph_ksize", type=int, default=7)
    parser.add_argument("--simplify_eps", type=float, default=12.0)
    parser.add_argument("--resample_step", type=float, default=4.0)
    parser.add_argument("--target_points_min", type=int, default=5)
    parser.add_argument("--target_points_max", type=int, default=7)
    parser.add_argument("--min_branch_len", type=float, default=10.0)
    parser.add_argument("--unity_scale", type=float, default=1.0)
    args = parser.parse_args()

    params = {
        "lower_hsv": args.lower_hsv,
        "upper_hsv": args.upper_hsv,
        "morph_ksize": args.morph_ksize,
        "simplify_eps": args.simplify_eps,
        "resample_step": args.resample_step,
        "target_points_min": args.target_points_min,
        "target_points_max": args.target_points_max,
        "min_branch_len": args.min_branch_len,
        "unity_scale": args.unity_scale,
    }

    os.makedirs(args.output, exist_ok=True)
    extract(args.image, args.output, params)


if __name__ == "__main__":
    main()

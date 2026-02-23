from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


EPS = 1e-9

Vec2 = Tuple[float, float]
Mat2 = Tuple[Tuple[float, float], Tuple[float, float]]


@dataclass(frozen=True)
class Segment:
    u: int
    v: int
    is_boundary: bool


@dataclass(frozen=True)
class Transform2D:
    a: Mat2
    t: Vec2


def _norm_edge(u: int, v: int) -> Tuple[int, int]:
    return (u, v) if u < v else (v, u)


def _polygon_area(poly: Sequence[Vec2]) -> float:
    area2 = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area2 += x1 * y2 - x2 * y1
    return 0.5 * area2


def _point_on_segment(p: Vec2, a: Vec2, b: Vec2, eps: float = EPS) -> bool:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    seg_len = math.hypot(dx, dy)
    if seg_len <= eps:
        return math.hypot(px - ax, py - ay) <= eps
    cross = (px - ax) * dy - (py - ay) * dx
    if abs(cross) > eps * max(1.0, seg_len):
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= eps


def _contains_point(poly: Sequence[Vec2], q: Vec2, eps: float = EPS) -> bool:
    qx, qy = q
    n = len(poly)
    for i in range(n):
        if _point_on_segment(q, poly[i], poly[(i + 1) % n], eps=eps):
            return True

    inside = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = (y1 > qy) != (y2 > qy)
        if not cond:
            continue
        t = (qy - y1) / (y2 - y1)
        x_cross = x1 + t * (x2 - x1)
        if qx < x_cross:
            inside = not inside
    return inside


def _identity_transform() -> Transform2D:
    return Transform2D(a=((1.0, 0.0), (0.0, 1.0)), t=(0.0, 0.0))


def _matmul2(a: Mat2, b: Mat2) -> Mat2:
    return (
        (
            a[0][0] * b[0][0] + a[0][1] * b[1][0],
            a[0][0] * b[0][1] + a[0][1] * b[1][1],
        ),
        (
            a[1][0] * b[0][0] + a[1][1] * b[1][0],
            a[1][0] * b[0][1] + a[1][1] * b[1][1],
        ),
    )


def _matvec2(a: Mat2, p: Vec2) -> Vec2:
    return (
        a[0][0] * p[0] + a[0][1] * p[1],
        a[1][0] * p[0] + a[1][1] * p[1],
    )


def _compose(t1: Transform2D, t2: Transform2D) -> Transform2D:
    # Compose as t1(t2(x)).
    a = _matmul2(t1.a, t2.a)
    tx, ty = _matvec2(t1.a, t2.t)
    return Transform2D(a=a, t=(tx + t1.t[0], ty + t1.t[1]))


def _apply_transform(t: Transform2D, p: Vec2) -> Vec2:
    x, y = _matvec2(t.a, p)
    return (x + t.t[0], y + t.t[1])


def _reflect_about_line(a: Vec2, b: Vec2, eps: float = EPS) -> Transform2D:
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    length = math.hypot(dx, dy)
    if length <= eps:
        return _identity_transform()
    ux = dx / length
    uy = dy / length
    m00 = 2.0 * ux * ux - 1.0
    m01 = 2.0 * ux * uy
    m10 = 2.0 * ux * uy
    m11 = 2.0 * uy * uy - 1.0
    ma = ((m00, m01), (m10, m11))
    rax, ray = _matvec2(ma, a)
    tx = ax - rax
    ty = ay - ray
    return Transform2D(a=ma, t=(tx, ty))


def _transform_delta(a: Transform2D, b: Transform2D) -> float:
    vals = [
        abs(a.a[0][0] - b.a[0][0]),
        abs(a.a[0][1] - b.a[0][1]),
        abs(a.a[1][0] - b.a[1][0]),
        abs(a.a[1][1] - b.a[1][1]),
        abs(a.t[0] - b.t[0]),
        abs(a.t[1] - b.t[1]),
    ]
    return max(vals)


def _planarize_segments(vertices: Dict[int, Vec2], edges: Sequence[Segment]) -> List[Segment]:
    split_edges: Dict[Tuple[int, int], bool] = {}
    vertex_items = list(vertices.items())

    for edge in edges:
        p0 = vertices[edge.u]
        p1 = vertices[edge.v]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        denom = dx * dx + dy * dy
        if denom <= EPS:
            continue

        split_points: List[Tuple[float, int]] = [(0.0, edge.u), (1.0, edge.v)]
        for vid, pv in vertex_items:
            if vid == edge.u or vid == edge.v:
                continue
            if not _point_on_segment(pv, p0, p1):
                continue
            t = ((pv[0] - p0[0]) * dx + (pv[1] - p0[1]) * dy) / denom
            if t <= EPS or t >= 1.0 - EPS:
                continue
            split_points.append((t, vid))

        split_points.sort(key=lambda it: it[0])
        compact: List[Tuple[float, int]] = []
        for t, vid in split_points:
            if compact and abs(t - compact[-1][0]) <= 1e-8:
                continue
            compact.append((t, vid))
        for i in range(len(compact) - 1):
            u = compact[i][1]
            v = compact[i + 1][1]
            if u == v:
                continue
            key = _norm_edge(u, v)
            prev = split_edges.get(key)
            split_edges[key] = edge.is_boundary if prev is None else (prev or edge.is_boundary)

    return [Segment(u=k[0], v=k[1], is_boundary=b) for k, b in split_edges.items()]


def _extract_faces(vertices: Dict[int, Vec2], edges: Sequence[Segment]) -> Tuple[List[List[int]], Dict[Tuple[int, int], int]]:
    adj: Dict[int, Set[int]] = defaultdict(set)
    for e in edges:
        adj[e.u].add(e.v)
        adj[e.v].add(e.u)

    ordered_neighbors: Dict[int, List[int]] = {}
    pos: Dict[int, Dict[int, int]] = {}
    for v, nbrs in adj.items():
        vx, vy = vertices[v]
        ordered = sorted(nbrs, key=lambda n: math.atan2(vertices[n][1] - vy, vertices[n][0] - vx))
        ordered_neighbors[v] = ordered
        pos[v] = {n: i for i, n in enumerate(ordered)}

    directed_edges: List[Tuple[int, int]] = []
    for e in edges:
        directed_edges.append((e.u, e.v))
        directed_edges.append((e.v, e.u))

    visited: Set[Tuple[int, int]] = set()
    halfedge_face: Dict[Tuple[int, int], int] = {}
    faces: List[List[int]] = []
    max_steps = max(8, 2 * len(directed_edges) + 4)

    for start in directed_edges:
        if start in visited:
            continue
        cycle: List[int] = []
        hedges: List[Tuple[int, int]] = []
        cur = start
        ok = False
        for _ in range(max_steps):
            if cur in visited:
                break
            visited.add(cur)
            hedges.append(cur)
            u, v = cur
            cycle.append(u)

            nbrs = ordered_neighbors.get(v)
            if not nbrs:
                break
            idx = pos[v].get(u)
            if idx is None:
                break
            w = nbrs[idx - 1]  # predecessor in CCW order -> keep face on left.
            cur = (v, w)
            if cur == start:
                ok = True
                break
        if not ok or len(cycle) < 3:
            continue
        fid = len(faces)
        faces.append(cycle)
        for he in hedges:
            halfedge_face[he] = fid
    return faces, halfedge_face


def _face_centroid(poly: Sequence[Vec2]) -> Vec2:
    area = _polygon_area(poly)
    if abs(area) <= EPS:
        sx = sum(x for x, _ in poly)
        sy = sum(y for _, y in poly)
        n = max(1, len(poly))
        return (sx / n, sy / n)
    factor = 1.0 / (6.0 * area)
    cx = 0.0
    cy = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx * factor, cy * factor)


def _build_dual_graph(
    vertices: Dict[int, Vec2],
    edges: Sequence[Segment],
    halfedge_face: Dict[Tuple[int, int], int],
    valid_face_ids: Set[int],
) -> Dict[int, List[Tuple[int, Vec2, Vec2]]]:
    dual: Dict[int, List[Tuple[int, Vec2, Vec2]]] = defaultdict(list)
    for e in edges:
        if e.is_boundary:
            continue
        f0 = halfedge_face.get((e.u, e.v))
        f1 = halfedge_face.get((e.v, e.u))
        if f0 is None or f1 is None or f0 == f1:
            continue
        if f0 not in valid_face_ids or f1 not in valid_face_ids:
            continue
        p0 = vertices[e.u]
        p1 = vertices[e.v]
        dual[f0].append((f1, p0, p1))
        dual[f1].append((f0, p0, p1))
    return dual


def render_folded_preview(
    cp_graph_path: str,
    out_path: str,
    *,
    alpha: float = 0.28,
    line_width: float = 0.9,
    dpi: int = 220,
    show_face_id: bool = False,
) -> Dict[str, object]:
    with open(cp_graph_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("schema") != "cp_graph_v1":
        raise ValueError(f"unsupported schema: {payload.get('schema')!r}")

    vertices: Dict[int, Vec2] = {}
    for v in payload.get("vertices", []):
        vid = int(v["id"])
        point = v["point"]
        vertices[vid] = (float(point["x_approx"]), float(point["y_approx"]))
    if not vertices:
        raise ValueError("no vertices in cp_graph")

    raw_edges: List[Segment] = []
    for e in payload.get("edges", []):
        raw_edges.append(
            Segment(
                u=int(e["v0"]),
                v=int(e["v1"]),
                is_boundary=bool(e.get("is_boundary", False)),
            )
        )
    if not raw_edges:
        raise ValueError("no edges in cp_graph")

    segments = _planarize_segments(vertices, raw_edges)
    faces, halfedge_face = _extract_faces(vertices, segments)

    face_polys: Dict[int, List[Vec2]] = {}
    area_by_face: Dict[int, float] = {}
    valid_faces: Set[int] = set()
    for fid, fverts in enumerate(faces):
        poly = [vertices[v] for v in fverts]
        area = _polygon_area(poly)
        if area <= EPS:
            continue
        face_polys[fid] = poly
        area_by_face[fid] = area
        valid_faces.add(fid)
    if not valid_faces:
        raise ValueError("failed to reconstruct bounded faces from cp_graph")

    dual = _build_dual_graph(vertices, segments, halfedge_face, valid_faces)
    domain = payload.get("domain") or {}
    cx = 0.5 * (float(domain.get("x_min", 0.0)) + float(domain.get("x_max", 1.0)))
    cy = 0.5 * (float(domain.get("y_min", 0.0)) + float(domain.get("y_max", 1.0)))
    center = (cx, cy)

    root = None
    for fid in valid_faces:
        if _contains_point(face_polys[fid], center):
            root = fid
            break
    if root is None:
        root = max(valid_faces, key=lambda f: area_by_face[f])

    transforms: Dict[int, Transform2D] = {}
    depth: Dict[int, int] = {}
    inconsistencies = 0

    def _bfs(seed: int) -> None:
        nonlocal inconsistencies
        q: deque[int] = deque([seed])
        while q:
            f = q.popleft()
            tf = transforms[f]
            for g, p0, p1 in dual.get(f, []):
                cand = _compose(tf, _reflect_about_line(p0, p1))
                if g not in transforms:
                    transforms[g] = cand
                    depth[g] = depth[f] + 1
                    q.append(g)
                else:
                    if _transform_delta(transforms[g], cand) > 1e-6:
                        inconsistencies += 1

    transforms[root] = _identity_transform()
    depth[root] = 0
    _bfs(root)
    for fid in sorted(valid_faces):
        if fid in transforms:
            continue
        transforms[fid] = _identity_transform()
        depth[fid] = 0
        _bfs(fid)

    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    draw_order = sorted(valid_faces, key=lambda f: (depth.get(f, 0), area_by_face[f], f))
    transformed_polys: Dict[int, List[Vec2]] = {}
    for fid in draw_order:
        tf = transforms[fid]
        transformed_polys[fid] = [_apply_transform(tf, p) for p in face_polys[fid]]

    xs = [x for poly in transformed_polys.values() for x, _ in poly]
    ys = [y for poly in transformed_polys.values() for _, y in poly]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1e-3)
    pad = 0.08 * span

    fig, ax = plt.subplots(figsize=(6.2, 6.2), dpi=dpi)
    front_color = "#7db8ff"
    back_color = "#c6e3ff"
    edge_color = "#1f3f5b"

    for fid in draw_order:
        tf = transforms[fid]
        det = tf.a[0][0] * tf.a[1][1] - tf.a[0][1] * tf.a[1][0]
        color = front_color if det >= 0.0 else back_color
        poly = transformed_polys[fid]
        patch = Polygon(
            poly,
            closed=True,
            facecolor=color,
            edgecolor=edge_color,
            linewidth=line_width,
            alpha=alpha,
            joinstyle="round",
        )
        ax.add_patch(patch)
        if show_face_id:
            c = _face_centroid(poly)
            ax.text(c[0], c[1], str(fid), ha="center", va="center", fontsize=7, color="#0f2233")

    ax.set_xlim(min_x - pad, max_x + pad)
    ax.set_ylim(min_y - pad, max_y + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    fig.tight_layout(pad=0.0)

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    return {
        "cp_graph_path": cp_graph_path,
        "out_path": out_path,
        "segment_count": len(segments),
        "face_count": len(valid_faces),
        "dual_edge_count": sum(len(v) for v in dual.values()) // 2,
        "transform_inconsistencies": inconsistencies,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Render a translucent folded-style preview from cp_graph_v1 JSON."
    )
    p.add_argument("--cp-graph-path", type=str, required=True)
    p.add_argument("--out-path", type=str, default="_tmp_out/folded_preview.png")
    p.add_argument("--alpha", type=float, default=0.28)
    p.add_argument("--line-width", type=float, default=0.9)
    p.add_argument("--dpi", type=int, default=220)
    p.add_argument("--show-face-id", action="store_true")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    stats = render_folded_preview(
        cp_graph_path=args.cp_graph_path,
        out_path=args.out_path,
        alpha=float(args.alpha),
        line_width=float(args.line_width),
        dpi=int(args.dpi),
        show_face_id=bool(args.show_face_id),
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()

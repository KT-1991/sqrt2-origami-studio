from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple


def clone_graph(g, *, graph_cls):
    h = graph_cls(
        points=g.points,
        p2i=g.point_to_id,
        points_f=g.points_f,
        share_base=True,
        use_local_ray_dirty=g.use_local_ray_dirty,
    )
    h.active_vertices = set(g.active_vertices)
    h.edges = set(g.edges)
    h.boundary_edges = set(g.boundary_edges)
    h.edge_birth = dict(g.edge_birth)
    h.edge_birth_counter = g.edge_birth_counter
    h.adj = {k: set(vs) for k, vs in g.adj.items()}
    # Lightweight clone of ray rows: copy dictionaries only.
    # Row lists are replaced wholesale on recompute, so sharing row objects is safe.
    h.ray_next = dict(g.ray_next)
    h.ray_hit = dict(g.ray_hit)
    h.ray_hit_rev = {e: set(vs) for e, vs in g.ray_hit_rev.items()}
    h.ray_dirty = set(g.ray_dirty)
    h.edge_dir_idx = dict(g.edge_dir_idx)
    h.edge_parallel_buckets = [set(es) for es in g.edge_parallel_buckets]
    h.edge_unknown_dir = set(g.edge_unknown_dir)
    h.edge_scan_cache_version = g.edge_scan_cache_version
    h.edge_scan_cache = {k: tuple(vs) for k, vs in g.edge_scan_cache.items()}
    # These caches are small and frequently reused; keep them copied.
    h.incident_dirs_cache = {k: list(vs) for k, vs in g.incident_dirs_cache.items()}
    h.incident_dirs_dirty = set(g.incident_dirs_dirty)
    h.kawasaki_cache = dict(g.kawasaki_cache)
    h.kawasaki_dirty = set(g.kawasaki_dirty)
    h.point_int_cache = dict(g.point_int_cache)
    h.mirror_vid_cache = dict(g.mirror_vid_cache)
    h.state_hash1 = g.state_hash1
    h.state_hash2 = g.state_hash2
    h.edge_version = g.edge_version
    return h


def adopt_graph_state(dst, src) -> None:
    # Base geometry is immutable and shared; only mutable topology/caches are replaced.
    dst.active_vertices = set(src.active_vertices)
    dst.edges = set(src.edges)
    dst.boundary_edges = set(src.boundary_edges)
    dst.edge_birth = dict(src.edge_birth)
    dst.edge_birth_counter = src.edge_birth_counter
    dst.adj = {k: set(vs) for k, vs in src.adj.items()}
    dst.ray_next = {k: list(row) for k, row in src.ray_next.items()}
    dst.ray_hit = {k: list(row) for k, row in src.ray_hit.items()}
    dst.ray_hit_rev = {e: set(vs) for e, vs in src.ray_hit_rev.items()}
    dst.ray_dirty = set(src.ray_dirty)
    dst.edge_dir_idx = dict(src.edge_dir_idx)
    dst.edge_parallel_buckets = [set(es) for es in src.edge_parallel_buckets]
    dst.edge_unknown_dir = set(src.edge_unknown_dir)
    dst.edge_scan_cache_version = src.edge_scan_cache_version
    dst.edge_scan_cache = {k: tuple(vs) for k, vs in src.edge_scan_cache.items()}
    dst.incident_dirs_cache = {k: list(vs) for k, vs in src.incident_dirs_cache.items()}
    dst.incident_dirs_dirty = set(src.incident_dirs_dirty)
    dst.kawasaki_cache = dict(src.kawasaki_cache)
    dst.kawasaki_dirty = set(src.kawasaki_dirty)
    dst.point_int_cache = dict(src.point_int_cache)
    dst.mirror_vid_cache = dict(src.mirror_vid_cache)
    dst.state_hash1 = src.state_hash1
    dst.state_hash2 = src.state_hash2
    dst.use_local_ray_dirty = src.use_local_ray_dirty
    dst.edge_version = src.edge_version


def graph_state_key(g) -> Tuple[int, int, int]:
    return (g.state_hash1, g.state_hash2, len(g.edges))


def make_grid_graph(
    corners,
    a_max: int,
    b_max: int,
    k_max: int,
    *,
    enumerate_grid_points,
    graph_cls,
    seed_direct_corner_connections,
    add_segment_with_splits_ids,
    point_cls,
    zero,
    one,
    corner_max_deg: float = 45.0,
    min_corner_lines: int = 2,
    enforce_symmetry: bool = True,
    use_local_ray_dirty: bool = False,
    seed_stats: Optional[Dict[str, int]] = None,
):
    points, p2i = enumerate_grid_points(a_max=a_max, b_max=b_max, k_max=k_max)
    g = graph_cls(points=points, p2i=p2i, use_local_ray_dirty=use_local_ray_dirty)
    g.init_square_boundary()
    corner_ids = [g.add_vertex(p) for p in corners]
    # Seed direct corner-to-corner connections on the 16-direction grid.
    seed_direct_corner_connections(
        g,
        corner_ids,
        max_deg=corner_max_deg,
        min_corner_lines=min_corner_lines,
        enforce_symmetry=enforce_symmetry,
        stats=seed_stats,
    )
    # Seed the main diagonal y=x.
    # Using split-aware insertion keeps diagonal connectivity even when intersections exist.
    v00 = g.add_vertex(point_cls(zero, zero))
    v11 = g.add_vertex(point_cls(one, one))
    add_segment_with_splits_ids(g, v00, v11, max_steps=128, stats=seed_stats)
    g.recompute_ray_next_all()
    return g, corner_ids


def graph_stats(g, *, point_k_level) -> Dict[str, int]:
    max_k = -1
    for v in g.active_vertices:
        p = g.points[v]
        k = point_k_level(p)
        if k is not None:
            max_k = max(max_k, k)
    return {
        "grid_points_total": len(g.points),
        "active_vertices": len(g.active_vertices),
        "edges": len(g.edges),
        "max_k_active": max_k,
    }


def remap_graph_to_new_grid(src, dst, *, point_key) -> None:
    vmap: Dict[int, int] = {}
    for v in src.active_vertices:
        key = point_key(src.points[v])
        nv = dst.point_to_id.get(key)
        if nv is None:
            continue
        dst.activate_vertex(nv)
        vmap[v] = nv
    for i, j in src.edges:
        ni = vmap.get(i)
        nj = vmap.get(j)
        if ni is None or nj is None or ni == nj:
            continue
        e = (i, j) if i < j else (j, i)
        dst.add_edge(ni, nj, boundary=(e in src.boundary_edges))
    dst._mark_all_ray_dirty()


def lattice_bounds_active(g) -> Dict[str, int]:
    max_k = -1
    max_abs_a = 0
    max_abs_b = 0
    for v in g.active_vertices:
        p = g.points[v]
        for z in (p.x, p.y):
            max_k = max(max_k, z.k)
            max_abs_a = max(max_abs_a, abs(z.a))
            max_abs_b = max(max_abs_b, abs(z.b))
    return {"max_k": max_k, "max_abs_a": max_abs_a, "max_abs_b": max_abs_b}

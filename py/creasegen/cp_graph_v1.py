from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

from creasegen.core_types import PointE, Qsqrt2
from creasegen.graph import GridCreaseGraph

__all__ = [
    "CP_GRAPH_V1_KEYS",
    "build_cp_graph_v1",
    "write_cp_graph_v1",
]


CP_GRAPH_V1_KEYS: Tuple[str, ...] = (
    "schema",
    "domain",
    "direction",
    "vertices",
    "edges",
    "corners",
    "stats",
    "params",
    "search_stats",
    "stage_logs",
)


def _qsqrt2_payload(z: Qsqrt2) -> Dict[str, int]:
    return {
        "a": z.a,
        "b": z.b,
        "k": z.k,
    }


def _point_payload(p: PointE, p_f: Tuple[float, float]) -> Dict[str, object]:
    return {
        "x": _qsqrt2_payload(p.x),
        "y": _qsqrt2_payload(p.y),
        "x_approx": p_f[0],
        "y_approx": p_f[1],
    }


def _validate_cp_graph_v1_schema(payload: Dict[str, object]) -> None:
    keys_now = tuple(payload.keys())
    if keys_now != CP_GRAPH_V1_KEYS:
        raise ValueError(
            "cp_graph_v1 schema mismatch: expected keys "
            f"{CP_GRAPH_V1_KEYS} but got {keys_now}"
        )


def build_cp_graph_v1(
    g: GridCreaseGraph,
    *,
    corner_ids: Sequence[int],
    params: Optional[Dict[str, object]] = None,
    search_stats: Optional[Dict[str, int]] = None,
    stage_logs: Optional[Sequence[Dict[str, object]]] = None,
) -> Dict[str, object]:
    active_vertices = sorted(g.active_vertices)
    corner_set = set(corner_ids)
    missing_corners = sorted(v for v in corner_set if v not in g.active_vertices)
    if missing_corners:
        raise ValueError(f"corner vertices must be active, but missing: {missing_corners}")

    boundary_vertex_ids = set()
    for i, j in g.boundary_edges:
        boundary_vertex_ids.add(i)
        boundary_vertex_ids.add(j)

    vertices: List[Dict[str, object]] = []
    for v in active_vertices:
        vertices.append(
            {
                "id": v,
                "point": _point_payload(g.points[v], g.points_f[v]),
                "is_corner": (v in corner_set),
                "is_boundary": (v in boundary_vertex_ids),
            }
        )

    edge_pairs_unsorted: List[Tuple[int, int]] = list(g.edges)
    for e in edge_pairs_unsorted:
        if e not in g.edge_birth:
            raise ValueError(f"edge_birth is missing for edge {e}")
    edge_pairs: List[Tuple[int, int]] = sorted(
        edge_pairs_unsorted,
        key=lambda e: (
            g.edge_birth[e],
            e[0],
            e[1],
        ),
    )
    edges: List[Dict[str, object]] = []
    for edge_id, e in enumerate(edge_pairs):
        if e[0] not in g.active_vertices or e[1] not in g.active_vertices:
            raise ValueError(f"edge endpoint must be active: {e}")
        birth = g.edge_birth[e]
        axis8 = g.edge_dir_idx.get(e)
        if axis8 is None:
            raise ValueError(f"edge_dir_idx is missing for edge {e}")
        edges.append(
            {
                "id": edge_id,
                "v0": e[0],
                "v1": e[1],
                "is_boundary": (e in g.boundary_edges),
                "axis8": axis8,
                "birth_order": birth,
            }
        )

    payload = {
        "schema": "cp_graph_v1",
        "domain": {
            "shape": "unit_square",
            "x_min": 0.0,
            "x_max": 1.0,
            "y_min": 0.0,
            "y_max": 1.0,
        },
        "direction": {
            "dir_count": 16,
            "axis_count": 8,
        },
        "vertices": vertices,
        "edges": edges,
        "corners": sorted(corner_set),
        "stats": {
            "vertex_count": len(vertices),
            "edge_count": len(edges),
            "boundary_edge_count": len(g.boundary_edges),
            "corner_count": len(corner_set),
        },
        "params": (dict(params) if params is not None else None),
        "search_stats": (dict(search_stats) if search_stats is not None else None),
        "stage_logs": (list(stage_logs) if stage_logs is not None else None),
    }
    _validate_cp_graph_v1_schema(payload)
    return payload


def write_cp_graph_v1(path: str, payload: Dict[str, object]) -> None:
    _validate_cp_graph_v1_schema(payload)
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

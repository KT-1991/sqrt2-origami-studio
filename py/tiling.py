from __future__ import annotations

import bisect
import json
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple


Point = Tuple[float, float]

_OCT_PHASE = math.pi / 8.0
_OCT_UNIT_VERTS: Tuple[Point, ...] = tuple(
    (math.cos(_OCT_PHASE + 2.0 * math.pi * k / 8.0), math.sin(_OCT_PHASE + 2.0 * math.pi * k / 8.0))
    for k in range(8)
)


def _unit_polygon_axes(poly: Sequence[Point]) -> Tuple[Point, ...]:
    axes: List[Point] = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        ex, ey = (x2 - x1), (y2 - y1)
        nx, ny = (-ey, ex)
        l = math.hypot(nx, ny)
        if l <= 1e-15:
            continue
        axes.append((nx / l, ny / l))
    return tuple(axes)


_OCT_AXES: Tuple[Point, ...] = _unit_polygon_axes(_OCT_UNIT_VERTS)
_OCT_AXIS_EXTENTS: Tuple[float, ...] = tuple(
    max(vx * ax + vy * ay for (vx, vy) in _OCT_UNIT_VERTS) for (ax, ay) in _OCT_AXES
)


@dataclass(frozen=True)
class KadoSpec:
    name: str
    length: float
    symmetry: str  # "axis" or "pair"
    pair_name: Optional[str] = None


@dataclass(frozen=True)
class IndependentVar:
    name: str
    length: float
    symmetry: str  # "axis" or "pair_anchor"
    pair_name: Optional[str] = None


@dataclass
class SolveResult:
    ok: bool
    alpha: float
    den: int
    coeff_limit: int
    centers: Dict[str, Point]
    corner_hits: int
    contact_score: float
    message: str


def mirror_y_eq_x(p: Point) -> Point:
    return (p[1], p[0])


def dist(a: Point, b: Point) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.hypot(dx, dy)


def polygon_axes(poly: Sequence[Point]) -> List[Point]:
    axes: List[Point] = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        ex, ey = (x2 - x1), (y2 - y1)
        nx, ny = (-ey, ex)
        l = math.hypot(nx, ny)
        if l <= 1e-15:
            continue
        axes.append((nx / l, ny / l))
    return axes


def project_poly(poly: Sequence[Point], axis: Point) -> Tuple[float, float]:
    ax, ay = axis
    vals = [x * ax + y * ay for (x, y) in poly]
    return (min(vals), max(vals))


def convex_overlap_depth(poly_a: Sequence[Point], poly_b: Sequence[Point], eps: float = 1e-10) -> float:
    """
    SAT penetration depth for convex polygons.
    Returns 0 when separated or only touching (touch allowed).
    """
    min_depth = 1e30
    for axis in polygon_axes(poly_a) + polygon_axes(poly_b):
        a0, a1 = project_poly(poly_a, axis)
        b0, b1 = project_poly(poly_b, axis)
        if a1 <= b0 + eps or b1 <= a0 + eps:
            return 0.0
        depth = min(a1, b1) - max(a0, b0)
        if depth < min_depth:
            min_depth = depth
    return 0.0 if min_depth < eps else min_depth


def build_independent_vars(specs: Sequence[KadoSpec]) -> List[IndependentVar]:
    out: List[IndependentVar] = []
    used = set()
    by_name = {s.name: s for s in specs}
    for s in specs:
        if s.name in used:
            continue
        if s.symmetry == "axis":
            out.append(IndependentVar(name=s.name, length=s.length, symmetry="axis"))
            used.add(s.name)
            continue
        if s.symmetry == "pair":
            if not s.pair_name or s.pair_name not in by_name:
                raise ValueError(f"pair spec missing valid pair_name: {s.name}")
            p = by_name[s.pair_name]
            if abs(p.length - s.length) > 1e-9:
                raise ValueError(f"pair lengths must match: {s.name}, {p.name}")
            out.append(
                IndependentVar(
                    name=s.name,
                    length=s.length,
                    symmetry="pair_anchor",
                    pair_name=s.pair_name,
                )
            )
            used.add(s.name)
            used.add(s.pair_name)
            continue
        raise ValueError(f"unknown symmetry: {s.symmetry}")
    return out


def expand_centers(indep: Dict[str, Point], vars_: Sequence[IndependentVar]) -> Dict[str, Point]:
    out: Dict[str, Point] = {}
    for v in vars_:
        c = indep[v.name]
        out[v.name] = c
        if v.symmetry == "pair_anchor":
            out[v.pair_name] = mirror_y_eq_x(c)
    return out


def circles_from_centers(
    centers: Dict[str, Point],
    specs: Sequence[KadoSpec],
    alpha: float,
) -> List[Tuple[str, Point, float]]:
    by_name = {s.name: s for s in specs}
    out = []
    for name, c in centers.items():
        r = alpha * by_name[name].length
        out.append((name, c, r))
    return out


def boundary_penalty(center: Point) -> float:
    x, y = center
    pen = 0.0
    if x < 0.0:
        pen += (0.0 - x) ** 2
    if x > 1.0:
        pen += (x - 1.0) ** 2
    if y < 0.0:
        pen += (0.0 - y) ** 2
    if y > 1.0:
        pen += (y - 1.0) ** 2
    return pen


def oct_overlap_depth_same_orientation(
    center_a: Point,
    radius_a: float,
    center_b: Point,
    radius_b: float,
    eps: float = 1e-10,
) -> float:
    dx = center_a[0] - center_b[0]
    dy = center_a[1] - center_b[1]
    min_depth = 1e30
    for (ax, ay), extent in zip(_OCT_AXES, _OCT_AXIS_EXTENTS):
        sep = abs(dx * ax + dy * ay)
        ha = radius_a * extent
        hb = radius_b * extent
        depth = min((ha + hb) - sep, 2.0 * min(ha, hb))
        if depth <= eps:
            return 0.0
        if depth < min_depth:
            min_depth = depth
    return 0.0 if min_depth <= eps else min_depth


def oct_pair_overlap_penalty(
    center_a: Point,
    radius_a: float,
    center_b: Point,
    radius_b: float,
    margin: float = 0.0,
) -> float:
    dx = center_a[0] - center_b[0]
    dy = center_a[1] - center_b[1]
    rr = radius_a + radius_b
    # Fast broad phase via circumcircles.
    if (dx * dx + dy * dy) >= rr * rr:
        return 0.0
    depth = oct_overlap_depth_same_orientation(center_a, radius_a, center_b, radius_b)
    if depth <= 0.0:
        return 0.0
    return (depth + margin) ** 2 * 16.0


def packing_penalty(circles: Sequence[Tuple[str, Point, float]], margin: float = 0.0) -> float:
    pen = 0.0
    # Boundary (center-only): center must stay inside the square.
    # Circle itself is allowed to go outside.
    for _, center, _r in circles:
        pen += boundary_penalty(center)
    # Overlap: regular octagons (touching edges is allowed).
    for i in range(len(circles)):
        _, ci, ri = circles[i]
        for j in range(i + 1, len(circles)):
            _, cj, rj = circles[j]
            pen += oct_pair_overlap_penalty(ci, ri, cj, rj, margin=margin)
    return pen


def contact_score(circles: Sequence[Tuple[str, Point, float]]) -> float:
    score = 0.0
    for i in range(len(circles)):
        _, ci, ri = circles[i]
        for j in range(i + 1, len(circles)):
            _, cj, rj = circles[j]
            d = dist(ci, cj)
            target = ri + rj
            delta = abs(d - target)
            w = 2.0 if abs(ri - rj) <= 1e-9 else 1.0
            score += w / (1.0 + delta)
    return score


def regular_oct_vertices(center: Point, radius: float) -> List[Point]:
    cx, cy = center
    return [(cx + radius * ux, cy + radius * uy) for (ux, uy) in _OCT_UNIT_VERTS]


def corner_hits(centers: Dict[str, Point], specs: Sequence[KadoSpec], alpha: float, tol: float = 1e-3) -> int:
    corners = [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)]
    by_name = {s.name: s for s in specs}
    vertices: List[Point] = []
    for name, c in centers.items():
        vertices.extend(regular_oct_vertices(c, alpha * by_name[name].length))
    hit = 0
    for q in corners:
        best = min(dist(v, q) for v in vertices) if vertices else 1e9
        if best <= tol:
            hit += 1
    return hit


def rand_init_indep(vars_: Sequence[IndependentVar], rng: random.Random) -> Dict[str, Point]:
    out: Dict[str, Point] = {}
    for v in vars_:
        if v.symmetry == "axis":
            t = rng.random()
            out[v.name] = (t, t)
        else:
            x = rng.random()
            y = rng.random()
            if y > x:
                x, y = y, x
            out[v.name] = (x, y)
    return out


def project_point_to_symmetry(p: Point, symmetry: str) -> Point:
    x = min(1.0, max(0.0, p[0]))
    y = min(1.0, max(0.0, p[1]))
    if symmetry == "axis":
        t = 0.5 * (x + y)
        t = min(1.0, max(0.0, t))
        return (t, t)
    if y > x:
        x, y = y, x
    return (x, y)


def normalize_indep_hint(
    hint: Dict[str, Point],
    vars_: Sequence[IndependentVar],
) -> Dict[str, Point]:
    by_name = {v.name: v for v in vars_}
    out: Dict[str, Point] = {}
    for name, p in hint.items():
        v = by_name.get(name)
        if v is None:
            continue
        out[name] = project_point_to_symmetry(p, v.symmetry)
    return out


def indep_hint_from_centers(
    centers: Dict[str, Point],
    vars_: Sequence[IndependentVar],
) -> Dict[str, Point]:
    out: Dict[str, Point] = {}
    for v in vars_:
        c: Optional[Point] = None
        if v.name in centers:
            c = centers[v.name]
        elif v.symmetry == "pair_anchor" and v.pair_name in centers:
            c = mirror_y_eq_x(centers[v.pair_name])
        if c is None:
            continue
        out[v.name] = project_point_to_symmetry(c, v.symmetry)
    return out


def guided_init_indep(
    vars_: Sequence[IndependentVar],
    hint: Dict[str, Point],
    rng: random.Random,
    jitter: float,
) -> Dict[str, Point]:
    out = rand_init_indep(vars_, rng)
    for v in vars_:
        p = hint.get(v.name)
        if p is None:
            continue
        x, y = p
        if jitter > 0.0:
            x += rng.uniform(-jitter, jitter)
            y += rng.uniform(-jitter, jitter)
        out[v.name] = project_point_to_symmetry((x, y), v.symmetry)
    return out


def perturb_point(p: Point, symmetry: str, step: float, rng: random.Random) -> Point:
    x, y = p
    x += rng.uniform(-step, step)
    y += rng.uniform(-step, step)
    x = min(1.0, max(0.0, x))
    y = min(1.0, max(0.0, y))
    if symmetry == "axis":
        t = 0.5 * (x + y)
        t = min(1.0, max(0.0, t))
        return (t, t)
    if y > x:
        x, y = y, x
    return (x, y)


def continuous_pack(
    specs: Sequence[KadoSpec],
    vars_: Sequence[IndependentVar],
    alpha: float,
    seed: int = 0,
    restarts: int = 24,
    iters: int = 1800,
    initial_indep: Optional[Dict[str, Point]] = None,
    guided_restarts: int = 0,
    guided_jitter: float = 0.08,
) -> Tuple[Dict[str, Point], float]:
    rng = random.Random(seed)
    best_indep: Dict[str, Point] = {}
    best_pen = 1e30
    hint = normalize_indep_hint(initial_indep, vars_) if initial_indep else {}
    guided_slots = min(restarts, max(1, guided_restarts)) if hint else 0
    for rr in range(restarts):
        rr_rng = random.Random(seed + 1009 * rr)
        if rr < guided_slots:
            jitter = 0.0 if rr == 0 else guided_jitter * (0.65 ** (rr - 1))
            indep = guided_init_indep(vars_, hint, rr_rng, jitter=jitter)
        else:
            indep = rand_init_indep(vars_, rr_rng)
        step = 0.14
        cur_pen = packing_penalty(circles_from_centers(expand_centers(indep, vars_), specs, alpha))
        for _ in range(iters):
            v = vars_[rng.randrange(len(vars_))]
            old = indep[v.name]
            indep[v.name] = perturb_point(old, v.symmetry, step, rng)
            pen2 = packing_penalty(circles_from_centers(expand_centers(indep, vars_), specs, alpha))
            if pen2 <= cur_pen:
                cur_pen = pen2
            else:
                indep[v.name] = old
            step *= 0.9992
        if cur_pen < best_pen:
            best_pen = cur_pen
            best_indep = dict(indep)
    return best_indep, best_pen


@lru_cache(maxsize=None)
def lattice_values(den: int, coeff_limit: int) -> Tuple[float, ...]:
    vals = set()
    root2 = math.sqrt(2.0)
    m = coeff_limit * den
    for a in range(-m, m + 1):
        for b in range(-m, m + 1):
            v = (a + b * root2) / den
            if -1e-9 <= v <= 1.0 + 1e-9:
                vals.add(min(1.0, max(0.0, v)))
    vals.update([0.0, 1.0, 0.5])
    return tuple(sorted(vals))


def nearest_value(v: float, vals: Sequence[float]) -> float:
    return min(vals, key=lambda u: abs(u - v))


def nearest_values(v: float, vals: Sequence[float], limit: int) -> List[float]:
    if limit >= len(vals):
        return list(vals)
    idx = bisect.bisect_left(vals, v)
    left = idx - 1
    right = idx
    out: List[float] = []
    while len(out) < limit and (left >= 0 or right < len(vals)):
        if left < 0:
            out.append(vals[right])
            right += 1
            continue
        if right >= len(vals):
            out.append(vals[left])
            left -= 1
            continue
        if abs(vals[left] - v) <= abs(vals[right] - v):
            out.append(vals[left])
            left -= 1
        else:
            out.append(vals[right])
            right += 1
    return out


def snap_indep(
    indep: Dict[str, Point],
    vars_: Sequence[IndependentVar],
    den: int,
    coeff_limit: int,
) -> Dict[str, Point]:
    vals = lattice_values(den, coeff_limit)
    out: Dict[str, Point] = {}
    for v in vars_:
        x, y = indep[v.name]
        if v.symmetry == "axis":
            t = nearest_value(0.5 * (x + y), vals)
            out[v.name] = (t, t)
        else:
            sx = nearest_value(x, vals)
            sy = nearest_value(y, vals)
            if sy > sx:
                sx, sy = sy, sx
            out[v.name] = (sx, sy)
    return out


def local_repair_snap(
    indep: Dict[str, Point],
    vars_: Sequence[IndependentVar],
    specs: Sequence[KadoSpec],
    alpha: float,
    den: int,
    coeff_limit: int,
    rounds: int = 4,
) -> Dict[str, Point]:
    vals = lattice_values(den, coeff_limit)
    out = dict(indep)
    by_name = {s.name: s for s in specs}
    radii = {s.name: alpha * s.length for s in specs}
    order = sorted(vars_, key=lambda v: by_name[v.name].length)

    centers = expand_centers(out, vars_)
    all_names = sorted(centers.keys())

    def pair_key(a: str, b: str) -> Tuple[str, str]:
        return (a, b) if a < b else (b, a)

    dep_names: Dict[str, Tuple[str, ...]] = {}
    affected_pairs: Dict[str, Tuple[Tuple[str, str], ...]] = {}
    for v in vars_:
        dep = [v.name]
        if v.symmetry == "pair_anchor" and v.pair_name is not None:
            dep.append(v.pair_name)
        dep_uniq = tuple(sorted(set(dep)))
        dep_names[v.name] = dep_uniq
        aff = set()
        for a in dep_uniq:
            for b in all_names:
                if a == b:
                    continue
                aff.add(pair_key(a, b))
        affected_pairs[v.name] = tuple(sorted(aff))

    boundary_by_name = {name: boundary_penalty(centers[name]) for name in all_names}
    pair_pen: Dict[Tuple[str, str], float] = {}
    total_pen = sum(boundary_by_name.values())
    for i in range(len(all_names)):
        ni = all_names[i]
        ci = centers[ni]
        ri = radii[ni]
        for j in range(i + 1, len(all_names)):
            nj = all_names[j]
            p = oct_pair_overlap_penalty(ci, ri, centers[nj], radii[nj])
            k = pair_key(ni, nj)
            pair_pen[k] = p
            total_pen += p

    for _ in range(rounds):
        for v in order:
            ox, oy = out[v.name]
            candidates: List[Point] = []
            if v.symmetry == "axis":
                near = nearest_values(0.5 * (ox + oy), vals, 18)
                candidates = [(t, t) for t in near]
            else:
                nearx = nearest_values(ox, vals, 10)
                neary = nearest_values(oy, vals, 10)
                for x in nearx:
                    for y in neary:
                        if y > x:
                            x2, y2 = y, x
                        else:
                            x2, y2 = x, y
                        candidates.append((x2, y2))

            dep = dep_names[v.name]
            aff_pairs = affected_pairs[v.name]
            old_contrib = sum(boundary_by_name[name] for name in dep)
            old_contrib += sum(pair_pen[k] for k in aff_pairs)

            best = out[v.name]
            best_pen = total_pen
            for c in candidates:
                trial_centers: Dict[str, Point] = {v.name: c}
                if v.symmetry == "pair_anchor" and v.pair_name is not None:
                    trial_centers[v.pair_name] = mirror_y_eq_x(c)

                new_contrib = sum(boundary_penalty(trial_centers[name]) for name in dep)
                for a, b in aff_pairs:
                    ca = trial_centers[a] if a in trial_centers else centers[a]
                    cb = trial_centers[b] if b in trial_centers else centers[b]
                    new_contrib += oct_pair_overlap_penalty(ca, radii[a], cb, radii[b])

                p = total_pen - old_contrib + new_contrib
                if p + 1e-15 < best_pen:
                    best_pen = p
                    best = c

            if best != out[v.name]:
                out[v.name] = best
                centers[v.name] = best
                if v.symmetry == "pair_anchor" and v.pair_name is not None:
                    mirrored = mirror_y_eq_x(best)
                    centers[v.pair_name] = mirrored

                for name in dep:
                    boundary_by_name[name] = boundary_penalty(centers[name])
                for a, b in aff_pairs:
                    pair_pen[(a, b)] = oct_pair_overlap_penalty(
                        centers[a], radii[a], centers[b], radii[b]
                    )
                total_pen = best_pen
    return out


def solve_kado_layout(
    specs: Sequence[KadoSpec],
    den_candidates: Sequence[int] = (1, 2),
    coeff_candidates: Sequence[int] = (1, 2),
    seed: int = 0,
    alpha_steps: int = 14,
    pack_restarts: int = 10,
    pack_iters: int = 700,
    initial_centers: Optional[Dict[str, Point]] = None,
    initial_indep: Optional[Dict[str, Point]] = None,
    pack_guided_restarts: int = 3,
    pack_guided_jitter: float = 0.08,
    warm_start: bool = True,
) -> SolveResult:
    vars_ = build_independent_vars(specs)
    max_len = max(s.length for s in specs)
    lo = 0.0
    hi = 0.5 / max_len
    best: Optional[SolveResult] = None
    manual_hint: Dict[str, Point] = {}
    if initial_centers:
        manual_hint.update(indep_hint_from_centers(initial_centers, vars_))
    if initial_indep:
        manual_hint.update(normalize_indep_hint(initial_indep, vars_))
    warm_hints: Dict[Tuple[int, int], Dict[str, Point]] = {}

    for _ in range(alpha_steps):
        alpha = 0.5 * (lo + hi)
        best_trial: Optional[SolveResult] = None
        feasible_any = False

        for den in den_candidates:
            for coeff in coeff_candidates:
                key = (den, coeff)
                start_hint: Optional[Dict[str, Point]] = None
                if warm_start:
                    start_hint = warm_hints.get(key)
                if start_hint is None and manual_hint:
                    start_hint = manual_hint
                indep_cont, _ = continuous_pack(
                    specs,
                    vars_,
                    alpha,
                    seed=seed + 17 * den + 101 * coeff,
                    restarts=pack_restarts,
                    iters=pack_iters,
                    initial_indep=start_hint,
                    guided_restarts=pack_guided_restarts,
                    guided_jitter=pack_guided_jitter,
                )
                if warm_start:
                    warm_hints[key] = dict(indep_cont)
                indep_snap = snap_indep(indep_cont, vars_, den=den, coeff_limit=coeff)
                indep_fix = local_repair_snap(
                    indep_snap, vars_, specs, alpha, den=den, coeff_limit=coeff
                )
                centers = expand_centers(indep_fix, vars_)
                circles = circles_from_centers(centers, specs, alpha)
                pen = packing_penalty(circles)
                if pen <= 1e-10:
                    feasible_any = True
                    hits = corner_hits(centers, specs, alpha)
                    csc = contact_score(circles)
                    cur = SolveResult(
                        ok=True,
                        alpha=alpha,
                        den=den,
                        coeff_limit=coeff,
                        centers=centers,
                        corner_hits=hits,
                        contact_score=csc,
                        message="feasible",
                    )
                    if best_trial is None:
                        best_trial = cur
                    else:
                        lhs = (cur.corner_hits, cur.contact_score)
                        rhs = (best_trial.corner_hits, best_trial.contact_score)
                        if lhs > rhs:
                            best_trial = cur

        if feasible_any and best_trial is not None:
            lo = alpha
            best = best_trial
        else:
            hi = alpha

    if best is None:
        return SolveResult(
            ok=False,
            alpha=0.0,
            den=int(den_candidates[0]),
            coeff_limit=int(coeff_candidates[0]),
            centers={},
            corner_hits=0,
            contact_score=0.0,
            message="no feasible layout found",
        )
    return best


def save_result_json(res: SolveResult, path: str) -> None:
    data = {
        "ok": res.ok,
        "alpha": res.alpha,
        "den": res.den,
        "coeff_limit": res.coeff_limit,
        "corner_hits": res.corner_hits,
        "contact_score": res.contact_score,
        "centers": {k: [v[0], v[1]] for k, v in res.centers.items()},
        "message": res.message,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_result_plot(res: SolveResult, specs: Sequence[KadoSpec], path: str) -> None:
    import matplotlib.pyplot as plt

    by_name = {s.name: s for s in specs}
    fig, ax = plt.subplots(figsize=(6, 6), dpi=140)

    # Paper boundary
    ax.plot([0, 1, 1, 0, 0], [0, 0, 1, 1, 0], color="black", linewidth=1.2)

    # Octagons and circle-approx
    for name, c in sorted(res.centers.items()):
        r = res.alpha * by_name[name].length
        vx, vy = zip(*(regular_oct_vertices(c, r) + [regular_oct_vertices(c, r)[0]]))
        ax.plot(vx, vy, linewidth=1.2, label=f"{name} oct")
        circ = plt.Circle(c, r, fill=False, linestyle="--", linewidth=0.8, alpha=0.45)
        ax.add_patch(circ)
        ax.scatter([c[0]], [c[1]], s=20)
        ax.text(c[0], c[1], name, fontsize=8, ha="left", va="bottom")

    # Corners
    corners = [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)]
    ax.scatter([p[0] for p in corners], [p[1] for p in corners], s=24, color="red")

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.25)
    ax.set_title(
        f"Tiling result alpha={res.alpha:.6f}, den={res.den}, coeff={res.coeff_limit}, "
        f"corner_hits={res.corner_hits}"
    )
    ax.legend(loc="upper right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    specs = [
        KadoSpec(name="A0", length=1.0, symmetry="axis"),
        KadoSpec(name="A1", length=1.0, symmetry="axis"),
        KadoSpec(name="P1", length=1.0, symmetry="pair", pair_name="P2"),
        KadoSpec(name="P2", length=1.0, symmetry="pair", pair_name="P1"),
    ]
    res = solve_kado_layout(
        specs=specs,
        den_candidates=(1, 2),
        coeff_candidates=(1, 2),
        seed=0,
    )
    print(
        f"ok={res.ok} alpha={res.alpha:.6f} den={res.den} coeff={res.coeff_limit} "
        f"corner_hits={res.corner_hits} contact={res.contact_score:.6f}"
    )
    for name, c in sorted(res.centers.items()):
        print(f"{name}: ({c[0]:.6f}, {c[1]:.6f})")
    save_result_json(res, "tiling_result.json")
    save_result_plot(res, specs, "tiling_result.png")
    print("saved: tiling_result.json")
    print("saved: tiling_result.png")


if __name__ == "__main__":
    main()

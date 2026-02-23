import type {
  CreaseGraphMem,
  FoldPreviewInput,
  FoldPreviewResult,
} from "./types";

const EPS = 1e-9;

type Point = [number, number];
type Mat2 = [[number, number], [number, number]];

interface Segment {
  u: number;
  v: number;
  isBoundary: boolean;
}

interface Transform2D {
  a: Mat2;
  t: Point;
}

function normEdge(u: number, v: number): [number, number] {
  return u < v ? [u, v] : [v, u];
}

function edgeKey(u: number, v: number): string {
  const [a, b] = normEdge(u, v);
  return `${a}:${b}`;
}

function halfEdgeKey(u: number, v: number): string {
  return `${u}->${v}`;
}

function polygonArea(poly: Point[]): number {
  let area2 = 0.0;
  const n = poly.length;
  for (let i = 0; i < n; i += 1) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % n];
    area2 += x1 * y2 - x2 * y1;
  }
  return 0.5 * area2;
}

function pointOnSegment(p: Point, a: Point, b: Point, eps = EPS): boolean {
  const [ax, ay] = a;
  const [bx, by] = b;
  const [px, py] = p;
  const dx = bx - ax;
  const dy = by - ay;
  const segLen = Math.hypot(dx, dy);
  if (segLen <= eps) {
    return Math.hypot(px - ax, py - ay) <= eps;
  }
  const cross = (px - ax) * dy - (py - ay) * dx;
  if (Math.abs(cross) > eps * Math.max(1.0, segLen)) {
    return false;
  }
  const dot = (px - ax) * (px - bx) + (py - ay) * (py - by);
  return dot <= eps;
}

function containsPoint(poly: Point[], q: Point, eps = EPS): boolean {
  const [qx, qy] = q;
  const n = poly.length;
  for (let i = 0; i < n; i += 1) {
    if (pointOnSegment(q, poly[i], poly[(i + 1) % n], eps)) {
      return true;
    }
  }

  let inside = false;
  for (let i = 0; i < n; i += 1) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % n];
    const cond = (y1 > qy) !== (y2 > qy);
    if (!cond) {
      continue;
    }
    const t = (qy - y1) / (y2 - y1);
    const xCross = x1 + t * (x2 - x1);
    if (qx < xCross) {
      inside = !inside;
    }
  }
  return inside;
}

function identityTransform(): Transform2D {
  return { a: [[1.0, 0.0], [0.0, 1.0]], t: [0.0, 0.0] };
}

function matmul2(a: Mat2, b: Mat2): Mat2 {
  return [
    [
      a[0][0] * b[0][0] + a[0][1] * b[1][0],
      a[0][0] * b[0][1] + a[0][1] * b[1][1],
    ],
    [
      a[1][0] * b[0][0] + a[1][1] * b[1][0],
      a[1][0] * b[0][1] + a[1][1] * b[1][1],
    ],
  ];
}

function matvec2(a: Mat2, p: Point): Point {
  return [
    a[0][0] * p[0] + a[0][1] * p[1],
    a[1][0] * p[0] + a[1][1] * p[1],
  ];
}

function compose(t1: Transform2D, t2: Transform2D): Transform2D {
  // Compose as t1(t2(x)).
  const a = matmul2(t1.a, t2.a);
  const [tx, ty] = matvec2(t1.a, t2.t);
  return { a, t: [tx + t1.t[0], ty + t1.t[1]] };
}

function applyTransform(t: Transform2D, p: Point): Point {
  const [x, y] = matvec2(t.a, p);
  return [x + t.t[0], y + t.t[1]];
}

function reflectAboutLine(a: Point, b: Point, eps = EPS): Transform2D {
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  const length = Math.hypot(dx, dy);
  if (length <= eps) {
    return identityTransform();
  }
  const ux = dx / length;
  const uy = dy / length;
  const m00 = 2.0 * ux * ux - 1.0;
  const m01 = 2.0 * ux * uy;
  const m10 = 2.0 * ux * uy;
  const m11 = 2.0 * uy * uy - 1.0;
  const ma: Mat2 = [
    [m00, m01],
    [m10, m11],
  ];
  const [rax, ray] = matvec2(ma, a);
  return { a: ma, t: [ax - rax, ay - ray] };
}

function transformDelta(a: Transform2D, b: Transform2D): number {
  return Math.max(
    Math.abs(a.a[0][0] - b.a[0][0]),
    Math.abs(a.a[0][1] - b.a[0][1]),
    Math.abs(a.a[1][0] - b.a[1][0]),
    Math.abs(a.a[1][1] - b.a[1][1]),
    Math.abs(a.t[0] - b.t[0]),
    Math.abs(a.t[1] - b.t[1]),
  );
}

function planarizeSegments(
  vertices: Map<number, Point>,
  edges: Segment[],
): Segment[] {
  const splitEdges = new Map<string, Segment>();
  const vertexItems = Array.from(vertices.entries());

  for (const edge of edges) {
    const p0 = vertices.get(edge.u);
    const p1 = vertices.get(edge.v);
    if (!p0 || !p1) {
      continue;
    }
    const dx = p1[0] - p0[0];
    const dy = p1[1] - p0[1];
    const denom = dx * dx + dy * dy;
    if (denom <= EPS) {
      continue;
    }

    const splitPoints: Array<[number, number]> = [
      [0.0, edge.u],
      [1.0, edge.v],
    ];
    for (const [vid, pv] of vertexItems) {
      if (vid === edge.u || vid === edge.v) {
        continue;
      }
      if (!pointOnSegment(pv, p0, p1)) {
        continue;
      }
      const t = ((pv[0] - p0[0]) * dx + (pv[1] - p0[1]) * dy) / denom;
      if (t <= EPS || t >= 1.0 - EPS) {
        continue;
      }
      splitPoints.push([t, vid]);
    }

    splitPoints.sort((lhs, rhs) => lhs[0] - rhs[0]);
    const compact: Array<[number, number]> = [];
    for (const [t, vid] of splitPoints) {
      if (compact.length > 0 && Math.abs(t - compact[compact.length - 1][0]) <= 1e-8) {
        continue;
      }
      compact.push([t, vid]);
    }

    for (let i = 0; i < compact.length - 1; i += 1) {
      const u = compact[i][1];
      const v = compact[i + 1][1];
      if (u === v) {
        continue;
      }
      const key = edgeKey(u, v);
      const prev = splitEdges.get(key);
      if (!prev) {
        splitEdges.set(key, { u: normEdge(u, v)[0], v: normEdge(u, v)[1], isBoundary: edge.isBoundary });
      } else if (!prev.isBoundary && edge.isBoundary) {
        splitEdges.set(key, { ...prev, isBoundary: true });
      }
    }
  }

  return Array.from(splitEdges.values());
}

function extractFaces(
  vertices: Map<number, Point>,
  edges: Segment[],
): {
  faces: number[][];
  halfedgeFace: Map<string, number>;
} {
  const adj = new Map<number, Set<number>>();
  for (const e of edges) {
    if (!adj.has(e.u)) {
      adj.set(e.u, new Set<number>());
    }
    if (!adj.has(e.v)) {
      adj.set(e.v, new Set<number>());
    }
    adj.get(e.u)!.add(e.v);
    adj.get(e.v)!.add(e.u);
  }

  const orderedNeighbors = new Map<number, number[]>();
  const pos = new Map<number, Map<number, number>>();
  for (const [v, nbrs] of adj.entries()) {
    const vp = vertices.get(v);
    if (!vp) {
      continue;
    }
    const [vx, vy] = vp;
    const ordered = Array.from(nbrs.values()).sort((lhs, rhs) => {
      const lp = vertices.get(lhs)!;
      const rp = vertices.get(rhs)!;
      const la = Math.atan2(lp[1] - vy, lp[0] - vx);
      const ra = Math.atan2(rp[1] - vy, rp[0] - vx);
      return la - ra;
    });
    orderedNeighbors.set(v, ordered);
    const p = new Map<number, number>();
    ordered.forEach((n, idx) => p.set(n, idx));
    pos.set(v, p);
  }

  const directedEdges: Array<[number, number]> = [];
  for (const e of edges) {
    directedEdges.push([e.u, e.v]);
    directedEdges.push([e.v, e.u]);
  }

  const visited = new Set<string>();
  const halfedgeFace = new Map<string, number>();
  const faces: number[][] = [];
  const maxSteps = Math.max(8, 2 * directedEdges.length + 4);

  for (const start of directedEdges) {
    const startKey = halfEdgeKey(start[0], start[1]);
    if (visited.has(startKey)) {
      continue;
    }
    const cycle: number[] = [];
    const hedges: Array<[number, number]> = [];
    let cur: [number, number] = [start[0], start[1]];
    let ok = false;

    for (let step = 0; step < maxSteps; step += 1) {
      const curKey = halfEdgeKey(cur[0], cur[1]);
      if (visited.has(curKey)) {
        break;
      }
      visited.add(curKey);
      hedges.push(cur);
      const [u, v] = cur;
      cycle.push(u);

      const nbrs = orderedNeighbors.get(v);
      const rowPos = pos.get(v);
      if (!nbrs || !rowPos) {
        break;
      }
      const idx = rowPos.get(u);
      if (idx === undefined) {
        break;
      }
      const w = idx === 0 ? nbrs[nbrs.length - 1] : nbrs[idx - 1];
      cur = [v, w];
      if (cur[0] === start[0] && cur[1] === start[1]) {
        ok = true;
        break;
      }
    }

    if (!ok || cycle.length < 3) {
      continue;
    }
    const fid = faces.length;
    faces.push(cycle);
    for (const [u, v] of hedges) {
      halfedgeFace.set(halfEdgeKey(u, v), fid);
    }
  }
  return { faces, halfedgeFace };
}

function buildDualGraph(
  vertices: Map<number, Point>,
  edges: Segment[],
  halfedgeFace: Map<string, number>,
  validFaceIds: Set<number>,
): Map<number, Array<[number, Point, Point]>> {
  const dual = new Map<number, Array<[number, Point, Point]>>();
  const add = (f: number, item: [number, Point, Point]): void => {
    if (!dual.has(f)) {
      dual.set(f, []);
    }
    dual.get(f)!.push(item);
  };

  for (const e of edges) {
    if (e.isBoundary) {
      continue;
    }
    const f0 = halfedgeFace.get(halfEdgeKey(e.u, e.v));
    const f1 = halfedgeFace.get(halfEdgeKey(e.v, e.u));
    if (f0 === undefined || f1 === undefined || f0 === f1) {
      continue;
    }
    if (!validFaceIds.has(f0) || !validFaceIds.has(f1)) {
      continue;
    }
    const p0 = vertices.get(e.u);
    const p1 = vertices.get(e.v);
    if (!p0 || !p1) {
      continue;
    }
    add(f0, [f1, p0, p1]);
    add(f1, [f0, p0, p1]);
  }
  return dual;
}

export function estimateFoldedPreview(input: FoldPreviewInput): FoldPreviewResult {
  const graph: CreaseGraphMem = input.graph;
  if (graph.schema !== "cp_graph_mem_v1") {
    throw new Error(`unsupported schema: ${String(graph.schema)}`);
  }

  const vertices = new Map<number, Point>();
  for (const v of graph.vertices) {
    vertices.set(v.id, [v.pointApprox.x, v.pointApprox.y]);
  }
  if (vertices.size === 0) {
    throw new Error("no vertices in graph");
  }

  const rawEdges: Segment[] = graph.edges.map((e) => ({
    u: e.v0,
    v: e.v1,
    isBoundary: e.isBoundary,
  }));
  if (rawEdges.length === 0) {
    throw new Error("no edges in graph");
  }

  const segments = planarizeSegments(vertices, rawEdges);
  const { faces, halfedgeFace } = extractFaces(vertices, segments);

  const facePolys = new Map<number, Point[]>();
  const areaByFace = new Map<number, number>();
  const validFaces = new Set<number>();
  for (let fid = 0; fid < faces.length; fid += 1) {
    const fverts = faces[fid];
    const poly: Point[] = [];
    for (const vid of fverts) {
      const p = vertices.get(vid);
      if (!p) {
        throw new Error(`missing vertex id in face: ${vid}`);
      }
      poly.push(p);
    }
    const area = polygonArea(poly);
    if (area <= EPS) {
      continue;
    }
    facePolys.set(fid, poly);
    areaByFace.set(fid, area);
    validFaces.add(fid);
  }
  if (validFaces.size === 0) {
    throw new Error("failed to reconstruct bounded faces from graph");
  }

  const dual = buildDualGraph(vertices, segments, halfedgeFace, validFaces);

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const [x, y] of vertices.values()) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  const center: Point = [0.5 * (minX + maxX), 0.5 * (minY + maxY)];

  let root: number | null = null;
  for (const fid of validFaces.values()) {
    const poly = facePolys.get(fid)!;
    if (containsPoint(poly, center)) {
      root = fid;
      break;
    }
  }
  if (root === null) {
    let bestArea = -1.0;
    for (const fid of validFaces.values()) {
      const a = areaByFace.get(fid)!;
      if (a > bestArea) {
        bestArea = a;
        root = fid;
      }
    }
  }
  if (root === null) {
    throw new Error("failed to choose root face");
  }

  const transforms = new Map<number, Transform2D>();
  const depth = new Map<number, number>();
  let inconsistencies = 0;

  const bfs = (seed: number): void => {
    const q: number[] = [seed];
    let qHead = 0;
    while (qHead < q.length) {
      const f = q[qHead];
      qHead += 1;
      const tf = transforms.get(f)!;
      const nbrs = dual.get(f) ?? [];
      for (const [g, p0, p1] of nbrs) {
        const cand = compose(tf, reflectAboutLine(p0, p1));
        if (!transforms.has(g)) {
          transforms.set(g, cand);
          depth.set(g, (depth.get(f) ?? 0) + 1);
          q.push(g);
        } else if (transformDelta(transforms.get(g)!, cand) > 1e-6) {
          inconsistencies += 1;
        }
      }
    }
  };

  transforms.set(root, identityTransform());
  depth.set(root, 0);
  bfs(root);

  const sortedFaceIds = Array.from(validFaces.values()).sort((a, b) => a - b);
  for (const fid of sortedFaceIds) {
    if (transforms.has(fid)) {
      continue;
    }
    transforms.set(fid, identityTransform());
    depth.set(fid, 0);
    bfs(fid);
  }

  const drawOrder = Array.from(validFaces.values()).sort((a, b) => {
    const da = depth.get(a) ?? 0;
    const db = depth.get(b) ?? 0;
    if (da !== db) {
      return da - db;
    }
    const aa = areaByFace.get(a) ?? 0.0;
    const ab = areaByFace.get(b) ?? 0.0;
    if (aa !== ab) {
      return aa - ab;
    }
    return a - b;
  });

  const outPolys = drawOrder.map((fid) => {
    const tf = transforms.get(fid)!;
    const srcPoly = facePolys.get(fid)!;
    const poly = srcPoly.map((p) => applyTransform(tf, p));
    const det = tf.a[0][0] * tf.a[1][1] - tf.a[0][1] * tf.a[1][0];
    return {
      faceId: fid,
      points: poly.map(([x, y]) => ({ x, y })),
      depth: depth.get(fid) ?? 0,
      frontSide: det >= 0.0,
    };
  });

  let dualEdgeCount = 0;
  for (const list of dual.values()) {
    dualEdgeCount += list.length;
  }

  return {
    facePolygons: outPolys,
    stats: {
      segmentCount: segments.length,
      faceCount: validFaces.size,
      dualEdgeCount: Math.floor(dualEdgeCount / 2),
      transformInconsistencies: inconsistencies,
    },
  };
}


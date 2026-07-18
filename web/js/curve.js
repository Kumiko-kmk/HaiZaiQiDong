/** Curve flattening — mirrors core/curves/flatten.py for WYSIWYG preview. */

const PREVIEW_FLATNESS_PX = 0.5;
const PREVIEW_MAX_STEP_PX = 8.0;
const EPS = 1e-9;
const MAX_DEPTH = 24;

function distance(a, b) {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

function lerp(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

function chordHeight(point, start, end) {
  const chord = distance(start, end);
  if (chord < EPS) return distance(point, start);
  const cross = Math.abs(
    (end[0] - start[0]) * (start[1] - point[1]) - (start[0] - point[0]) * (end[1] - point[1])
  );
  return cross / chord;
}

function subdivideLine(start, end, maxStepPx) {
  const length = distance(start, end);
  if (length <= maxStepPx + EPS) return [start, end];
  const steps = Math.max(1, Math.ceil(length / maxStepPx));
  return Array.from({ length: steps + 1 }, (_, index) => lerp(start, end, index / steps));
}

function cubicAt(p0, p1, p2, p3, t) {
  const u = 1 - t;
  return [
    u ** 3 * p0[0] + 3 * u ** 2 * t * p1[0] + 3 * u * t ** 2 * p2[0] + t ** 3 * p3[0],
    u ** 3 * p0[1] + 3 * u ** 2 * t * p1[1] + 3 * u * t ** 2 * p2[1] + t ** 3 * p3[1],
  ];
}

function quadraticAt(p0, p1, p2, t) {
  const u = 1 - t;
  return [
    u ** 2 * p0[0] + 2 * u * t * p1[0] + t ** 2 * p2[0],
    u ** 2 * p0[1] + 2 * u * t * p1[1] + t ** 2 * p2[1],
  ];
}

function flattenCubic(p0, p1, p2, p3, flatnessPx, maxStepPx, depth = 0) {
  const mid = cubicAt(p0, p1, p2, p3, 0.5);
  const sagitta = chordHeight(mid, p0, p3);
  const span = distance(p0, p3);
  if (depth >= MAX_DEPTH || (sagitta <= flatnessPx && span <= maxStepPx)) {
    return [p0, p3];
  }
  const p01 = lerp(p0, p1, 0.5);
  const p12 = lerp(p1, p2, 0.5);
  const p23 = lerp(p2, p3, 0.5);
  const p012 = lerp(p01, p12, 0.5);
  const p123 = lerp(p12, p23, 0.5);
  const midSplit = lerp(p012, p123, 0.5);
  const left = flattenCubic(p0, p01, p012, midSplit, flatnessPx, maxStepPx, depth + 1);
  const right = flattenCubic(midSplit, p123, p23, p3, flatnessPx, maxStepPx, depth + 1);
  return left.slice(0, -1).concat(right);
}

function flattenQuadratic(p0, p1, p2, flatnessPx, maxStepPx, depth = 0) {
  const mid = quadraticAt(p0, p1, p2, 0.5);
  const sagitta = chordHeight(mid, p0, p2);
  const span = distance(p0, p2);
  if (depth >= MAX_DEPTH || (sagitta <= flatnessPx && span <= maxStepPx)) {
    return [p0, p2];
  }
  const p01 = lerp(p0, p1, 0.5);
  const p12 = lerp(p1, p2, 0.5);
  const midSplit = lerp(p01, p12, 0.5);
  const left = flattenQuadratic(p0, p01, midSplit, flatnessPx, maxStepPx, depth + 1);
  const right = flattenQuadratic(midSplit, p12, p2, flatnessPx, maxStepPx, depth + 1);
  return left.slice(0, -1).concat(right);
}

function flattenParametric(evaluate, tStart, tEnd, flatnessPx, maxStepPx, depth = 0) {
  const start = evaluate(tStart);
  const end = evaluate(tEnd);
  const midT = (tStart + tEnd) * 0.5;
  const mid = evaluate(midT);
  const sagitta = chordHeight(mid, start, end);
  const span = distance(start, end);
  if (depth >= MAX_DEPTH || (sagitta <= flatnessPx && span <= maxStepPx)) {
    return [start, end];
  }
  const left = flattenParametric(evaluate, tStart, midT, flatnessPx, maxStepPx, depth + 1);
  const right = flattenParametric(evaluate, midT, tEnd, flatnessPx, maxStepPx, depth + 1);
  return left.slice(0, -1).concat(right);
}

function flattenArc(segment, flatnessPx, maxStepPx) {
  const [cx, cy] = segment.center;
  const r = segment.radius;
  let startRad = (segment.startAngle * Math.PI) / 180;
  let endRad = (segment.endAngle * Math.PI) / 180;
  if (segment.closed && Math.abs(segment.endAngle - segment.startAngle) >= 359.9) {
    endRad = startRad + 2 * Math.PI;
  } else if (endRad < startRad) {
    endRad += 2 * Math.PI;
  }
  return flattenParametric(
    (angle) => [cx + r * Math.cos(angle), cy + r * Math.sin(angle)],
    startRad,
    endRad,
    flatnessPx,
    maxStepPx
  );
}

function flattenEllipse(segment, flatnessPx, maxStepPx) {
  const [cx, cy] = segment.center;
  const rot = (segment.rotation * Math.PI) / 180;
  const cosR = Math.cos(rot);
  const sinR = Math.sin(rot);
  let startRad = (segment.startAngle * Math.PI) / 180;
  let endRad = (segment.endAngle * Math.PI) / 180;
  if (endRad < startRad) endRad += 2 * Math.PI;
  return flattenParametric(
    (angle) => {
      const lx = segment.rx * Math.cos(angle);
      const ly = segment.ry * Math.sin(angle);
      return [cx + lx * cosR - ly * sinR, cy + lx * sinR + ly * cosR];
    },
    startRad,
    endRad,
    flatnessPx,
    maxStepPx
  );
}

function normalizeStroke(stroke) {
  if (stroke.segments && stroke.segments.length) return stroke.segments;
  if (stroke.points && stroke.points.length) return [{ type: "polyline", points: stroke.points }];
  return [];
}

function parseSegment(raw) {
  const type = String(raw.type || "");
  if (type === "move") return { type, to: raw.to };
  if (type === "line") return { type, to: raw.to };
  if (type === "polyline") return { type, points: raw.points };
  if (type === "arc") {
    return {
      type,
      center: raw.center,
      radius: raw.radius,
      startAngle: raw.startAngle ?? raw.start_angle ?? 0,
      endAngle: raw.endAngle ?? raw.end_angle ?? 360,
      closed: !!raw.closed,
    };
  }
  if (type === "cubicBezier") return { type, c1: raw.c1, c2: raw.c2, to: raw.to };
  if (type === "quadraticBezier") return { type, c: raw.c, to: raw.to };
  if (type === "ellipse") {
    return {
      type,
      center: raw.center,
      rx: raw.rx,
      ry: raw.ry,
      rotation: raw.rotation ?? 0,
      startAngle: raw.startAngle ?? raw.start_angle ?? 0,
      endAngle: raw.endAngle ?? raw.end_angle ?? 360,
    };
  }
  return null;
}

function appendPoints(target, points) {
  for (const point of points) {
    if (!target.length || distance(target[target.length - 1], point) > EPS) {
      target.push(point);
    }
  }
}

function flattenSegment(segment, pen, flatnessPx, maxStepPx, includeStart) {
  if (segment.type === "move") return [segment.to];
  if (segment.type === "line") {
    if (!pen) throw new Error("line segment requires a starting pen position");
    const subdivided = subdivideLine(pen, segment.to, maxStepPx);
    return includeStart ? subdivided : subdivided.slice(1);
  }
  if (segment.type === "polyline") {
    if (!segment.points.length) return [];
    const vertices = [...segment.points];
    if (pen && distance(pen, vertices[0]) > EPS) vertices.unshift(pen);
    else if (pen) vertices[0] = pen;
    const out = includeStart ? [vertices[0]] : [];
    for (let i = 0; i < vertices.length - 1; i += 1) {
      const edge = subdivideLine(vertices[i], vertices[i + 1], maxStepPx);
      appendPoints(out, edge.slice(1));
    }
    return out;
  }
  if (segment.type === "arc") {
    const flattened = flattenArc(segment, flatnessPx, maxStepPx);
    return includeStart ? flattened : flattened.slice(1);
  }
  if (segment.type === "cubicBezier") {
    const flattened = flattenCubic(pen, segment.c1, segment.c2, segment.to, flatnessPx, maxStepPx);
    return includeStart ? flattened : flattened.slice(1);
  }
  if (segment.type === "quadraticBezier") {
    const flattened = flattenQuadratic(pen, segment.c, segment.to, flatnessPx, maxStepPx);
    return includeStart ? flattened : flattened.slice(1);
  }
  if (segment.type === "ellipse") {
    const flattened = flattenEllipse(segment, flatnessPx, maxStepPx);
    return includeStart ? flattened : flattened.slice(1);
  }
  return [];
}

function flattenStroke(segments, flatnessPx = PREVIEW_FLATNESS_PX, maxStepPx = PREVIEW_MAX_STEP_PX) {
  if (!segments || !segments.length) return [];

  const dense = [];
  let pen = null;

  for (const raw of segments) {
    const segment = parseSegment(raw);
    if (!segment) continue;
    const includeStart = !dense.length;

    if (segment.type === "move") {
      pen = segment.to;
      if (includeStart) dense.push(segment.to);
      continue;
    }

    const points = flattenSegment(segment, pen, flatnessPx, maxStepPx, includeStart);
    if (!points.length) continue;

    if (dense.length && distance(dense[dense.length - 1], points[0]) < EPS) {
      dense.push(...points.slice(1));
    } else {
      dense.push(...points);
    }
    pen = dense[dense.length - 1];
  }
  return dense;
}

function flattenStrokes(strokes, flatnessPx = PREVIEW_FLATNESS_PX, maxStepPx = PREVIEW_MAX_STEP_PX) {
  const result = [];
  for (const stroke of strokes || []) {
    const segments = normalizeStroke(stroke);
    const points = flattenStroke(segments, flatnessPx, maxStepPx);
    if (points.length) result.push(points);
  }
  return result;
}

window.CurveEngine = {
  flattenStroke,
  flattenStrokes,
  PREVIEW_FLATNESS_PX,
  PREVIEW_MAX_STEP_PX,
};

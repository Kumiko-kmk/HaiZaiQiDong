/** Render preset strokes as inline SVG using curve flattening. */

function buildPreviewSvg(strokes, size = 48) {
  const denseStrokes = window.CurveEngine.flattenStrokes(strokes);
  const points = denseStrokes.flat();
  if (!points.length) {
    return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}"></svg>`;
  }

  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const margin = 6;
  const scale = Math.min((size - margin * 2) / spanX, (size - margin * 2) / spanY);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  const toCanvas = ([x, y]) => [
    size / 2 + (x - centerX) * scale,
    size / 2 + (y - centerY) * scale,
  ];

  const parts = [];
  for (const stroke of denseStrokes) {
    const mapped = stroke.map(toCanvas);
    if (mapped.length >= 2) {
      const pathData = mapped.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
      parts.push(
        `<path d="${pathData}" fill="none" stroke="var(--preview-stroke)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />`
      );
    } else if (mapped.length === 1) {
      const [x, y] = mapped[0];
      parts.push(`<circle cx="${x}" cy="${y}" r="2" fill="var(--preview-stroke)" />`);
    }
  }

  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${parts.join("")}</svg>`;
}

window.PresetPreview = { buildPreviewSvg };

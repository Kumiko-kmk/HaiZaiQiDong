/** Borderless pointer canvas used to create custom polyline presets. */

class CanvasPresetEditor {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d");
    this.strokes = [];
    this.activeStroke = null;
    this.activePointerId = null;
    this.cssWidth = 0;
    this.cssHeight = 0;
    this.pixelRatio = 1;

    this._bindPointerEvents();
    this.resizeObserver = typeof ResizeObserver === "function"
      ? new ResizeObserver(() => this.resize())
      : null;
    if (this.resizeObserver) this.resizeObserver.observe(canvas.parentElement);
    window.addEventListener("resize", () => this.resize());
    this.resize();
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const width = Math.max(0, rect.width);
    const height = Math.max(0, rect.height);
    if (width < 1 || height < 1) return;
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const pixelWidth = Math.max(1, Math.round(width * ratio));
    const pixelHeight = Math.max(1, Math.round(height * ratio));
    if (
      this.canvas.width === pixelWidth &&
      this.canvas.height === pixelHeight &&
      this.cssWidth === width &&
      this.cssHeight === height
    ) return;
    this.cssWidth = width;
    this.cssHeight = height;
    this.pixelRatio = ratio;
    this.canvas.width = pixelWidth;
    this.canvas.height = pixelHeight;
    this._redraw();
  }

  clear() {
    this.strokes = [];
    this.activeStroke = null;
    this.activePointerId = null;
    this._redraw();
  }

  hasDrawing() {
    return this.strokes.some((stroke) => stroke.length >= 1);
  }

  buildPayload(name) {
    if (!this.hasDrawing() || this.cssWidth < 1 || this.cssHeight < 1) {
      throw new Error("请先在画布上拖动画笔绘制图案。");
    }
    return {
      name,
      canvasWidth: Math.round(this.cssWidth * 1000) / 1000,
      canvasHeight: Math.round(this.cssHeight * 1000) / 1000,
      strokes: this.strokes
        .filter((stroke) => stroke.length >= 1)
        .map((stroke) => stroke.map(([x, y]) => [x, y])),
      previewDataUrl: this._buildPreviewDataUrl(),
    };
  }

  _bindPointerEvents() {
    this.canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || this.activePointerId !== null) return;
      event.preventDefault();
      this.activePointerId = event.pointerId;
      this.activeStroke = [];
      this.strokes.push(this.activeStroke);
      this._appendPointerPoint(event, true);
      try {
        this.canvas.setPointerCapture(event.pointerId);
      } catch (_error) {
        // Pointer capture is optional in older embedded browser runtimes.
      }
    });

    this.canvas.addEventListener("pointermove", (event) => {
      if (event.pointerId !== this.activePointerId || !this.activeStroke) return;
      event.preventDefault();
      const samples = typeof event.getCoalescedEvents === "function"
        ? event.getCoalescedEvents()
        : [event];
      for (const sample of samples) this._appendPointerPoint(sample, false);
    });

    const finishStroke = (event) => {
      if (event.pointerId !== this.activePointerId) return;
      event.preventDefault();
      this._appendPointerPoint(event, false);
      this.activeStroke = null;
      this.activePointerId = null;
      try {
        this.canvas.releasePointerCapture(event.pointerId);
      } catch (_error) {
        // The browser may already have released capture.
      }
      this._redraw();
    };
    this.canvas.addEventListener("pointerup", finishStroke);
    this.canvas.addEventListener("pointercancel", finishStroke);
  }

  _appendPointerPoint(event, force) {
    if (!this.activeStroke || this.cssWidth < 1 || this.cssHeight < 1) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    const last = this.activeStroke[this.activeStroke.length - 1];
    if (!force && last) {
      const distance = Math.hypot(
        (x - last[0]) * this.cssWidth,
        (y - last[1]) * this.cssHeight,
      );
      if (distance < 1.1) return;
    }
    this.activeStroke.push([x, y]);
    this._redraw();
  }

  _prepareContext(context, ratio = 1) {
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.lineWidth = 3;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = "#111111";
    context.fillStyle = "#111111";
  }

  _redraw() {
    const context = this.context;
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this._prepareContext(context, this.pixelRatio);
    for (const stroke of this.strokes) {
      this._drawNormalizedStroke(context, stroke, this.cssWidth, this.cssHeight);
    }
  }

  _drawNormalizedStroke(context, stroke, width, height, transform = null) {
    if (!stroke.length) return;
    const mapPoint = transform || (([x, y]) => [x * width, y * height]);
    const [startX, startY] = mapPoint(stroke[0]);
    if (stroke.length === 1) {
      context.beginPath();
      context.arc(startX, startY, 1.5, 0, Math.PI * 2);
      context.fill();
      return;
    }
    context.beginPath();
    context.moveTo(startX, startY);
    for (let index = 1; index < stroke.length; index += 1) {
      const [x, y] = mapPoint(stroke[index]);
      context.lineTo(x, y);
    }
    context.stroke();
  }

  _buildPreviewDataUrl() {
    const width = 480;
    const height = 320;
    const padding = 28;
    const preview = document.createElement("canvas");
    preview.width = width;
    preview.height = height;
    const context = preview.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);

    const points = this.strokes.flat();
    const xs = points.map(([x]) => x * this.cssWidth);
    const ys = points.map(([, y]) => y * this.cssHeight);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const drawingWidth = Math.max(1, maxX - minX);
    const drawingHeight = Math.max(1, maxY - minY);
    const scale = Math.min(
      (width - padding * 2) / drawingWidth,
      (height - padding * 2) / drawingHeight,
    );
    const offsetX = (width - drawingWidth * scale) / 2 - minX * scale;
    const offsetY = (height - drawingHeight * scale) / 2 - minY * scale;
    this._prepareContext(context, 1);
    context.lineWidth = 4;
    const transform = ([x, y]) => [
      x * this.cssWidth * scale + offsetX,
      y * this.cssHeight * scale + offsetY,
    ];
    for (const stroke of this.strokes) {
      if (stroke.length >= 1) {
        this._drawNormalizedStroke(context, stroke, width, height, transform);
      }
    }
    return preview.toDataURL("image/png");
  }
}

window.CanvasPresetEditor = CanvasPresetEditor;

/** Borderless pointer canvas used to create custom polyline presets. */

const CANVAS_ERASER_RADIUS = 11;
const MAX_CANVAS_STROKES = 1024;
const CANVAS_HISTORY_LIMIT = 30;
const CANVAS_HISTORY_POINT_LIMIT = 200000;

class CanvasPresetEditor {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d");
    this.strokes = [];
    this.activeStroke = null;
    this.activePointerId = null;
    this.lastEraserPoint = null;
    this.historyTransaction = null;
    this.undoStack = [];
    this.redoStack = [];
    this.historyChangeListener = null;
    this.tool = "draw";
    this.suggestedName = "";
    this.cssWidth = 0;
    this.cssHeight = 0;
    this.pixelRatio = 1;
    this.canvas.dataset.tool = this.tool;

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

  setTool(tool) {
    if (tool !== "draw" && tool !== "erase") {
      throw new Error(`未知画布工具：${tool}`);
    }
    this._cancelPointerInteraction();
    this.tool = tool;
    this.canvas.dataset.tool = tool;
  }

  setHistoryChangeListener(listener) {
    this.historyChangeListener = typeof listener === "function" ? listener : null;
    this._emitHistoryChanged();
  }

  undo() {
    this._cancelPointerInteraction();
    const previous = this.undoStack.pop();
    if (!previous) return false;
    this.redoStack.push(this._createSnapshot());
    this._restoreSnapshot(previous);
    this._trimHistory();
    this._emitHistoryChanged();
    return true;
  }

  redo() {
    this._cancelPointerInteraction();
    const next = this.redoStack.pop();
    if (!next) return false;
    this.undoStack.push(this._createSnapshot());
    this._restoreSnapshot(next);
    this._trimHistory();
    this._emitHistoryChanged();
    return true;
  }

  clear() {
    this._cancelPointerInteraction();
    this.strokes = [];
    this.suggestedName = "";
    this.undoStack = [];
    this.redoStack = [];
    this.historyTransaction = null;
    this._emitHistoryChanged();
    this._redraw();
  }

  loadPresetStrokes(strokes, suggestedName = "", resetHistory = false) {
    if (!Array.isArray(strokes)) throw new Error("SVG 轮廓数据无效。");
    this.resize();
    if (this.cssWidth < 1 || this.cssHeight < 1) {
      throw new Error("画布尚未就绪，请稍后重试。");
    }

    const denseStrokes = window.CurveEngine.flattenStrokes(strokes);
    if (!denseStrokes.length) throw new Error("SVG 中没有可显示的轮廓。");
    if (denseStrokes.length > MAX_CANVAS_STROKES) throw new Error("SVG 轮廓数量过多，不能超过 1024 笔。");

    let pointCount = 0;
    const cleanStrokes = denseStrokes.map((stroke) => {
      if (!Array.isArray(stroke)) throw new Error("SVG 轮廓数据无效。");
      const clean = stroke.map((point) => {
        if (
          !Array.isArray(point) ||
          point.length < 2 ||
          !Number.isFinite(Number(point[0])) ||
          !Number.isFinite(Number(point[1]))
        ) {
          throw new Error("SVG 包含无效坐标。");
        }
        pointCount += 1;
        if (pointCount > 50000) throw new Error("SVG 采样点过多，请适当简化后重试。");
        return [Number(point[0]), Number(point[1])];
      });
      if (!clean.length) throw new Error("SVG 轮廓数据无效。");
      return clean;
    });

    const allPoints = cleanStrokes.flat();
    const xs = allPoints.map(([x]) => x);
    const ys = allPoints.map(([, y]) => y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const drawingWidth = maxX - minX;
    const drawingHeight = maxY - minY;
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const padding = 0.08;
    const availableWidth = this.cssWidth * (1 - padding * 2);
    const availableHeight = this.cssHeight * (1 - padding * 2);
    const scale = drawingWidth > 1e-9 || drawingHeight > 1e-9
      ? Math.min(
        drawingWidth > 1e-9 ? availableWidth / drawingWidth : Infinity,
        drawingHeight > 1e-9 ? availableHeight / drawingHeight : Infinity,
      )
      : 1;

    const nextStrokes = cleanStrokes.map((stroke) => stroke.map(([x, y]) => [
      Math.min(1, Math.max(0, (this.cssWidth / 2 + (x - centerX) * scale) / this.cssWidth)),
      Math.min(1, Math.max(0, (this.cssHeight / 2 + (y - centerY) * scale) / this.cssHeight)),
    ]));
    this._cancelPointerInteraction();
    const previous = this._createSnapshot();
    this.strokes = nextStrokes;
    this.suggestedName = String(suggestedName || "").trim().slice(0, 40);
    if (resetHistory) {
      this.undoStack = [];
      this.redoStack = [];
      this.historyTransaction = null;
      this._emitHistoryChanged();
    } else {
      this._recordHistory(previous);
    }
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
      this.historyTransaction = {
        previous: this._createSnapshot(),
        changed: false,
      };
      if (this.tool === "draw") {
        this.activeStroke = [];
        this.strokes.push(this.activeStroke);
        this._appendPointerPoint(event, true);
      } else {
        this.lastEraserPoint = null;
        this._erasePointerPoint(event, true);
      }
      try {
        this.canvas.setPointerCapture(event.pointerId);
      } catch (_error) {
        // Pointer capture is optional in older embedded browser runtimes.
      }
    });

    this.canvas.addEventListener("pointermove", (event) => {
      if (event.pointerId !== this.activePointerId) return;
      event.preventDefault();
      const samples = typeof event.getCoalescedEvents === "function"
        ? event.getCoalescedEvents()
        : [event];
      for (const sample of samples) {
        if (this.tool === "draw") {
          this._appendPointerPoint(sample, false);
        } else {
          this._erasePointerPoint(sample, false);
        }
      }
    });

    const finishInteraction = (event, applyFinalPoint) => {
      if (event.pointerId !== this.activePointerId) return;
      event.preventDefault();
      if (applyFinalPoint) {
        if (this.tool === "draw") {
          this._appendPointerPoint(event, false);
        } else {
          this._erasePointerPoint(event, false);
        }
      }
      this._cancelPointerInteraction();
      this._redraw();
    };
    this.canvas.addEventListener("pointerup", (event) => finishInteraction(event, true));
    this.canvas.addEventListener("pointercancel", (event) => finishInteraction(event, false));
  }

  _appendPointerPoint(event, force) {
    if (!this.activeStroke || this.cssWidth < 1 || this.cssHeight < 1) return false;
    const rect = this.canvas.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    const last = this.activeStroke[this.activeStroke.length - 1];
    if (!force && last) {
      const distance = Math.hypot(
        (x - last[0]) * this.cssWidth,
        (y - last[1]) * this.cssHeight,
      );
      if (distance < 1.1) return false;
    }
    this.activeStroke.push([x, y]);
    if (this.historyTransaction) this.historyTransaction.changed = true;
    this._redraw();
    return true;
  }

  _erasePointerPoint(event, force) {
    if (this.cssWidth < 1 || this.cssHeight < 1) return false;
    const rect = this.canvas.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return false;
    const point = [
      Math.min(this.cssWidth, Math.max(0, (event.clientX - rect.left) * this.cssWidth / rect.width)),
      Math.min(this.cssHeight, Math.max(0, (event.clientY - rect.top) * this.cssHeight / rect.height)),
    ];
    if (!force && this.lastEraserPoint) {
      if (Math.hypot(point[0] - this.lastEraserPoint[0], point[1] - this.lastEraserPoint[1]) < 1.5) {
        return false;
      }
    }
    this.lastEraserPoint = point;
    const changed = this._eraseAt(point[0], point[1], CANVAS_ERASER_RADIUS);
    if (changed) {
      if (this.historyTransaction) this.historyTransaction.changed = true;
      this._redraw();
    }
    return changed;
  }

  _eraseAt(centerX, centerY, radius) {
    const nextStrokes = [];
    let changed = false;
    for (const stroke of this.strokes) {
      const pieces = this._eraseStroke(stroke, centerX, centerY, radius);
      if (pieces === null) {
        nextStrokes.push(stroke);
      } else {
        changed = true;
        nextStrokes.push(...pieces);
      }
    }
    if (!changed || nextStrokes.length > MAX_CANVAS_STROKES) return false;
    this.strokes = nextStrokes;
    return true;
  }

  _eraseStroke(stroke, centerX, centerY, radius) {
    if (!stroke.length) return [];
    if (stroke.length === 1) {
      const distance = Math.hypot(
        stroke[0][0] * this.cssWidth - centerX,
        stroke[0][1] * this.cssHeight - centerY,
      );
      return distance < radius ? [] : null;
    }

    let intersects = false;
    for (let index = 1; index < stroke.length; index += 1) {
      if (this._distanceToSegment(stroke[index - 1], stroke[index], centerX, centerY) < radius) {
        intersects = true;
        break;
      }
    }
    if (!intersects) return null;

    const pieces = [];
    let currentPiece = null;
    const epsilon = 1e-7;
    for (let index = 1; index < stroke.length; index += 1) {
      const start = stroke[index - 1];
      const end = stroke[index];
      const intervals = this._outsideCircleIntervals(start, end, centerX, centerY, radius);
      if (!intervals.length) {
        currentPiece = null;
        continue;
      }
      for (const [from, to] of intervals) {
        if (from > epsilon) currentPiece = null;
        const first = this._lerpPoint(start, end, from);
        const last = this._lerpPoint(start, end, to);
        if (!currentPiece || !this._samePoint(currentPiece[currentPiece.length - 1], first)) {
          currentPiece = [first];
          pieces.push(currentPiece);
        }
        if (!this._samePoint(currentPiece[currentPiece.length - 1], last)) {
          currentPiece.push(last);
        }
        if (to < 1 - epsilon) currentPiece = null;
      }
    }
    return pieces.filter((piece) => piece.length >= 2);
  }

  _outsideCircleIntervals(start, end, centerX, centerY, radius) {
    const startX = start[0] * this.cssWidth;
    const startY = start[1] * this.cssHeight;
    const deltaX = (end[0] - start[0]) * this.cssWidth;
    const deltaY = (end[1] - start[1]) * this.cssHeight;
    const offsetX = startX - centerX;
    const offsetY = startY - centerY;
    const quadratic = deltaX * deltaX + deltaY * deltaY;
    if (quadratic < 1e-12) {
      return offsetX * offsetX + offsetY * offsetY >= radius * radius ? [[0, 1]] : [];
    }

    const linear = 2 * (offsetX * deltaX + offsetY * deltaY);
    const constant = offsetX * offsetX + offsetY * offsetY - radius * radius;
    const discriminant = linear * linear - 4 * quadratic * constant;
    const cuts = [0, 1];
    if (discriminant > 0) {
      const root = Math.sqrt(discriminant);
      const first = (-linear - root) / (2 * quadratic);
      const second = (-linear + root) / (2 * quadratic);
      if (first > 0 && first < 1) cuts.push(first);
      if (second > 0 && second < 1) cuts.push(second);
    }
    cuts.sort((left, right) => left - right);

    const outside = [];
    for (let index = 1; index < cuts.length; index += 1) {
      const from = cuts[index - 1];
      const to = cuts[index];
      if (to - from < 1e-9) continue;
      const middle = (from + to) / 2;
      const x = offsetX + deltaX * middle;
      const y = offsetY + deltaY * middle;
      if (x * x + y * y >= radius * radius) outside.push([from, to]);
    }
    return outside;
  }

  _distanceToSegment(start, end, centerX, centerY) {
    const startX = start[0] * this.cssWidth;
    const startY = start[1] * this.cssHeight;
    const deltaX = (end[0] - start[0]) * this.cssWidth;
    const deltaY = (end[1] - start[1]) * this.cssHeight;
    const lengthSquared = deltaX * deltaX + deltaY * deltaY;
    const projection = lengthSquared > 1e-12
      ? Math.max(0, Math.min(1, ((centerX - startX) * deltaX + (centerY - startY) * deltaY) / lengthSquared))
      : 0;
    return Math.hypot(
      startX + deltaX * projection - centerX,
      startY + deltaY * projection - centerY,
    );
  }

  _lerpPoint(start, end, amount) {
    return [
      start[0] + (end[0] - start[0]) * amount,
      start[1] + (end[1] - start[1]) * amount,
    ];
  }

  _samePoint(first, second) {
    return Math.abs(first[0] - second[0]) < 1e-9 && Math.abs(first[1] - second[1]) < 1e-9;
  }

  _cancelPointerInteraction() {
    const pointerId = this.activePointerId;
    this._commitHistoryTransaction();
    this.activeStroke = null;
    this.activePointerId = null;
    this.lastEraserPoint = null;
    if (pointerId === null) return;
    try {
      this.canvas.releasePointerCapture(pointerId);
    } catch (_error) {
      // The browser may already have released capture.
    }
  }

  _createSnapshot() {
    const strokes = this.strokes.map((stroke) => stroke.map(([x, y]) => [x, y]));
    return {
      strokes,
      suggestedName: this.suggestedName,
      pointCount: strokes.reduce((total, stroke) => total + stroke.length, 0),
    };
  }

  _restoreSnapshot(snapshot) {
    this.strokes = snapshot.strokes.map((stroke) => stroke.map(([x, y]) => [x, y]));
    this.suggestedName = snapshot.suggestedName;
    this._redraw();
  }

  _commitHistoryTransaction() {
    const transaction = this.historyTransaction;
    this.historyTransaction = null;
    if (transaction?.changed) this._recordHistory(transaction.previous);
  }

  _recordHistory(previous) {
    this.undoStack.push(previous);
    this.redoStack = [];
    this._trimHistory();
    this._emitHistoryChanged();
  }

  _trimHistory() {
    while (this.undoStack.length > CANVAS_HISTORY_LIMIT) this.undoStack.shift();
    while (this.redoStack.length > CANVAS_HISTORY_LIMIT) this.redoStack.shift();
    let totalPoints = [...this.undoStack, ...this.redoStack]
      .reduce((total, snapshot) => total + snapshot.pointCount, 0);
    while (totalPoints > CANVAS_HISTORY_POINT_LIMIT && this.undoStack.length + this.redoStack.length > 1) {
      const stack = this.undoStack.length > 1 ? this.undoStack : this.redoStack;
      const removed = stack.shift();
      if (!removed) break;
      totalPoints -= removed.pointCount;
    }
  }

  _emitHistoryChanged() {
    if (!this.historyChangeListener) return;
    this.historyChangeListener({
      canUndo: this.undoStack.length > 0,
      canRedo: this.redoStack.length > 0,
    });
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

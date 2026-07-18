/**
 * Draw-page preset selector: stacked cards (left) + grouped thumbnail
 * navigation (right), driven by lightweight rAF springs. Public API is kept
 * compatible with app.js: constructor({ onTopChanged, onConfirm }), and the
 * methods setPresets / bringToFront / setEnabled plus the `cards` array.
 */

const SCROLL_THRESHOLD = 50; // wheel pixels per selection step
const WHEEL_COOLDOWN_MS = 200; // ignore duplicate wheel events from one physical notch

// Stage (card) layout, tuned for the small 480x297 window.
const CARD_STEP_X = 40; // horizontal spacing per index of distance (up-right stagger)
const CARD_STEP_Y = 30; // vertical spacing per index of distance
const POP_X = 120; // selected card pulled horizontally to the right, out of the stack
const FADE_INNER = 3; // |diff| fully visible below this
const FADE_OUTER = 5; // |diff| fully hidden beyond this

const OWNER_TAGS = new Set(["战士", "猎手", "储君", "骨妹", "鸡煲", "其他"]);


const CARD_HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

function escapeCardHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => CARD_HTML_ESCAPES[ch]);
}

function mod(value, n) {
  return ((value % n) + n) % n;
}

function ownerTagForPreset(tags) {
  const ownerTag = Array.isArray(tags) && tags.length > 0 ? String(tags[0]) : "";
  return OWNER_TAGS.has(ownerTag) ? ownerTag : "其他";
}

/** Signed circular distance, mapped into (-n/2, n/2]. */
function wrapDiff(value, n) {
  let d = value % n;
  if (d > n / 2) d -= n;
  else if (d < -n / 2) d += n;
  return d;
}

class Spring {
  constructor(value, { stiffness, damping, mass = 1 } = {}) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
    this.stiffness = stiffness;
    this.damping = damping;
    this.mass = mass;
  }

  set(target) {
    this.target = target;
  }

  jump(value) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
  }

  step(dt) {
    const x = this.value - this.target;
    const acc = (-this.stiffness * x - this.damping * this.velocity) / this.mass;
    this.velocity += acc * dt;
    this.value += this.velocity * dt;
    if (Math.abs(this.value - this.target) < 0.0008 && Math.abs(this.velocity) < 0.0008) {
      this.value = this.target;
      this.velocity = 0;
      return true;
    }
    return false;
  }
}

class WheelCardMenu {
  constructor(root, { onTopChanged, onConfirm } = {}) {
    this.root = root;
    this.onTopChanged = onTopChanged || (() => {});
    this.onConfirm = onConfirm || (() => {});

    this.cards = [];
    this.enabled = true;
    // Unbounded "virtual" index on an infinite circular strip; the real card
    // is `mod(targetIndex, cards.length)`. Keeps spring motion continuous
    // when the selection wraps past either end.
    this.targetIndex = 0;
    this._userInteracted = false;

    this._scrollAccumulator = 0;
    this._lastWheelStepAt = 0;
    this._scrollTimeout = null;
    this._rafId = null;
    this._navResizeRaf = null;
    this._lastTime = 0;

    this.progress = new Spring(0, { stiffness: 250, damping: 28, mass: 1 });
    this.scrolling = new Spring(1, { stiffness: 300, damping: 25, mass: 1 });

    this._buildStructure();
    this._bindEvents();
  }

  _buildStructure() {
    this.root.classList.add("selector");

    this.stage = document.createElement("div");
    this.stage.className = "stage";

    this.menu = document.createElement("div");
    this.menu.className = "thumbnail-nav";
    this.menu.setAttribute("aria-label", "预设缩略导航");

    this.root.appendChild(this.stage);
    this.root.appendChild(this.menu);
  }

  _bindEvents() {
    this.root.addEventListener("wheel", (e) => this._onWheel(e), { passive: false });

    this.stage.addEventListener("click", (e) => {
      if (!this.enabled) return;
      const card = e.target.closest(".card3d");
      if (!card) return;
      const delta = this._deltaToCard(Number(card.dataset.index));
      if (delta === 0) {
        this.onConfirm();
      } else {
        this._setTarget(this.targetIndex + delta, false);
      }
    });

    this.menu.addEventListener("click", (e) => {
      if (!this.enabled) return;
      const item = e.target.closest("[data-preset-index]");
      if (!item) return;
      const delta = this._deltaToCard(Number(item.dataset.presetIndex));
      if (delta !== 0) this._setTarget(this.targetIndex + delta, false);
    });

    document.addEventListener("keydown", (e) => {
      if (!this.enabled || this.cards.length === 0) return;
      const page = this.root.closest(".page");
      if (page && !page.classList.contains("page--active")) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        this._setTarget(this.targetIndex + 1, false);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        this._setTarget(this.targetIndex - 1, false);
      }
    });

    window.addEventListener("resize", () => {
      if (this.cards.length === 0 || this._navResizeRaf !== null) return;
      this._navResizeRaf = requestAnimationFrame(() => {
        this._navResizeRaf = null;
        this._syncNavigator(mod(this.targetIndex, this.cards.length), false);
      });
    });
  }

  /** Shortest signed step count from the current selection to a real card index. */
  _deltaToCard(cardIndex) {
    const n = this.cards.length;
    if (n === 0) return 0;
    return Math.round(wrapDiff(cardIndex - mod(this.targetIndex, n), n));
  }

  // --- public API (consumed by app.js) ---

  setPresets(presets) {
    this.cards = presets.map((preset) => ({
      id: preset.id,
      name: preset.name,
      description: preset.description || "简笔画预设",
      tags: Array.isArray(preset.tags) ? preset.tags : [],
      ownerTag: ownerTagForPreset(preset.tags),
      strokes: preset.strokes || [],
      // Optional card artwork; falls back to the stroke SVG preview.
      previewUrl: preset.previewUrl || "",
    }));
    // Re-anchor the virtual index onto the fresh list.
    const n = this.cards.length;
    this.targetIndex = n > 0 ? Math.min(mod(this.targetIndex, n), n - 1) : 0;
    this._render();
    this.progress.jump(this.targetIndex);
    this.scrolling.jump(1);
    this._userInteracted = false;
    this._update();
    if (n > 0) this._syncNavigator(mod(this.targetIndex, n), false);
  }

  bringToFront(presetId) {
    const index = this.cards.findIndex((c) => c.id === presetId);
    if (index < 0) return;
    const delta = this._deltaToCard(index);
    if (delta === 0) {
      this._syncNavigator(index, false);
      return;
    }
    this.targetIndex += delta;
    if (this._userInteracted) {
      this.progress.set(this.targetIndex);
    } else {
      this.progress.jump(this.targetIndex);
    }
    this._syncNavigator(index, this._userInteracted);
    this._wake();
  }

  setEnabled(enabled) {
    this.enabled = enabled;
    this.root.classList.toggle("selector--disabled", !enabled);
  }

  // --- interaction helpers ---

  _onWheel(e) {
    if (!this.enabled || this.cards.length < 2) return;
    e.preventDefault();

    const now = performance.now();
    if (now - this._lastWheelStepAt < WHEEL_COOLDOWN_MS) return;

    this._scrollAccumulator += e.deltaY;
    if (Math.abs(this._scrollAccumulator) < SCROLL_THRESHOLD) return;

    // Exactly one card per physical wheel notch: use direction only, never
    // the magnitude (which can span multiple thresholds in a single event).
    const step = Math.sign(this._scrollAccumulator);
    this._scrollAccumulator = 0;
    this._lastWheelStepAt = now;
    this._setTarget(this.targetIndex + step, true);
  }

  _setTarget(virtualIndex, isWheel) {
    if (virtualIndex === this.targetIndex) return;
    const distance = Math.abs(virtualIndex - this.targetIndex);
    this._userInteracted = true;
    this.targetIndex = virtualIndex;
    this.progress.set(virtualIndex);

    this.scrolling.set(0);
    if (this._scrollTimeout) clearTimeout(this._scrollTimeout);
    const settleMs = isWheel ? 160 : Math.min(700, 260 + distance * 24);
    this._scrollTimeout = setTimeout(() => {
      this.scrolling.set(1);
      this._wake();
    }, settleMs);

    this._wake();
    const selectedIndex = mod(virtualIndex, this.cards.length);
    this._syncNavigator(selectedIndex, true);
    const card = this.cards[selectedIndex];
    if (card) this.onTopChanged(card.id);
  }

  // --- rendering ---

  _render() {
    this.stage.innerHTML = "";
    this.menu.innerHTML = "";
    this.cardEls = [];
    this.navLineEls = new Array(this.cards.length);
    this.navGroupEls = [];

    this.cards.forEach((card, index) => {
      this.stage.appendChild(this._createCard(card, index));
    });
    this._renderNavigator();
  }

  _createCard(card, index) {
    const el = document.createElement("div");
    el.className = "card3d";
    el.dataset.index = String(index);
    el.title = card.description;
    const art = card.previewUrl
      ? `<img class="card3d__img" src="${escapeCardHtml(card.previewUrl)}" alt="" draggable="false" />`
      : window.PresetPreview.buildPreviewSvg(card.strokes, 64);
    el.innerHTML = `
      <div class="card3d__panel" aria-hidden="true">
        <div class="card3d__header">
          <span class="card3d__tick"></span>
          <span class="card3d__name">${escapeCardHtml(card.name)}</span>
          <span class="card3d__index">${String(index + 1).padStart(2, "0")}</span>
        </div>
        <div class="card3d__art">${art}</div>
      </div>
    `;
    if (card.previewUrl) {
      const artElement = el.querySelector(".card3d__art");
      artElement.classList.add("card3d__art--image");
      artElement.style.backgroundImage = `url("${card.previewUrl}")`;
    }
    this.cardEls.push({ el });
    return el;
  }

  _renderNavigator() {
    const groups = [];
    const groupByOwner = new Map();
    this.cards.forEach((card, index) => {
      let group = groupByOwner.get(card.ownerTag);
      if (!group) {
        group = { ownerTag: card.ownerTag, entries: [] };
        groupByOwner.set(card.ownerTag, group);
        groups.push(group);
      }
      group.entries.push({ card, index });
    });

    groups.forEach((group) => {
      const section = document.createElement("section");
      section.className = "thumbnail-nav__group";
      section.dataset.owner = group.ownerTag;

      const header = document.createElement("button");
      header.type = "button";
      header.className = "thumbnail-nav__header";
      header.dataset.presetIndex = String(group.entries[0].index);
      header.setAttribute("aria-label", `跳转到${group.ownerTag}分类`);
      header.innerHTML = `
        <span class="thumbnail-nav__label">${escapeCardHtml(group.ownerTag)}</span>
        <span class="thumbnail-nav__dot" aria-hidden="true"></span>
      `;
      section.appendChild(header);

      const levels = document.createElement("div");
      levels.className = "thumbnail-nav__levels";
      group.entries.forEach(({ card, index }) => {
        const line = document.createElement("button");
        line.type = "button";
        line.className = "thumbnail-nav__line";
        line.dataset.presetIndex = String(index);
        line.setAttribute("aria-label", card.name);
        levels.appendChild(line);
        this.navLineEls[index] = line;
      });
      section.appendChild(levels);
      this.menu.appendChild(section);
      this.navGroupEls.push({ el: section, ownerTag: group.ownerTag });
    });
  }

  _syncNavigator(index, smooth) {
    if (!this.navLineEls || this.navLineEls.length === 0) return;
    const card = this.cards[index];
    this.navLineEls.forEach((line, lineIndex) => {
      if (!line) return;
      const active = lineIndex === index;
      line.classList.toggle("thumbnail-nav__line--active", active);
      if (active) line.setAttribute("aria-current", "true");
      else line.removeAttribute("aria-current");
    });
    this.navGroupEls.forEach(({ el, ownerTag }) => {
      el.classList.toggle("thumbnail-nav__group--active", !!card && ownerTag === card.ownerTag);
    });

    const activeLine = this.navLineEls[index];
    if (!activeLine) return;
    requestAnimationFrame(() => {
      const navRect = this.menu.getBoundingClientRect();
      const lineRect = activeLine.getBoundingClientRect();
      const centeredTop = this.menu.scrollTop + lineRect.top - navRect.top -
        (this.menu.clientHeight - lineRect.height) / 2;
      const maxScrollTop = Math.max(0, this.menu.scrollHeight - this.menu.clientHeight);
      this.menu.scrollTo({
        top: Math.max(0, Math.min(centeredTop, maxScrollTop)),
        behavior: smooth ? "smooth" : "auto",
      });
    });
  }

  _wake() {
    if (this._rafId !== null) return;
    this._lastTime = performance.now();
    this._rafId = requestAnimationFrame((t) => this._tick(t));
  }

  _tick(now) {
    let dt = (now - this._lastTime) / 1000;
    this._lastTime = now;
    if (dt > 1 / 30) dt = 1 / 30;

    const doneA = this.progress.step(dt);
    const doneB = this.scrolling.step(dt);
    this._update();

    if (doneA && doneB) {
      this._rafId = null;
    } else {
      this._rafId = requestAnimationFrame((t) => this._tick(t));
    }
  }

  _update() {
    if (!this.cardEls) return;
    const n = this.cardEls.length;
    if (n === 0) return;
    const p = this.progress.value;
    const s = this.scrolling.value;
    const half = n / 2;
    // The circular strip re-enters at |diff| = n/2; cards must be fully
    // faded out there so wrapping from one side to the other is invisible.
    const fadeOuter = Math.min(FADE_OUTER, half);
    const fadeInner = Math.min(FADE_INNER, Math.max(0.5, fadeOuter - 1));
    for (let i = 0; i < n; i += 1) {
      const { el } = this.cardEls[i];
      const diff = wrapDiff(i - p, n);
      const abs = Math.abs(diff);
      let opacity;
      if (abs <= fadeInner) opacity = 1;
      else if (abs >= fadeOuter) opacity = 0;
      else opacity = 1 - (abs - fadeInner) / (fadeOuter - fadeInner);

      if (opacity <= 0.001) {
        if (el.style.display !== "none") el.style.display = "none";
        continue;
      }
      if (el.style.display === "none") el.style.display = "";

      const closeness = Math.max(0, 1 - abs);
      const pop = closeness * s;
      // Selected card slides strictly horizontally to the right, out of the
      // stack; no vertical drift and no scaling during the pull.
      const x = diff * CARD_STEP_X + pop * POP_X;
      const y = diff * -CARD_STEP_Y;
      // Physical depth follows circular distance: cards in front (negative
      // diff, lower left) always cover cards behind. The pulled card keeps
      // its own depth — it slides out from underneath the cards in front of
      // it and over the cards behind it, like drawing a card from a deck.
      const z = Math.round(10000 - diff * 100);

      el.style.opacity = String(opacity);
      el.style.zIndex = String(z);
      el.style.transform =
        `translate(-50%, -50%) translate(${x.toFixed(2)}px, ${y.toFixed(2)}px)`;
      el.classList.toggle("card3d--active", pop > 0.5);
    }

  }
}

window.WheelCardMenu = WheelCardMenu;

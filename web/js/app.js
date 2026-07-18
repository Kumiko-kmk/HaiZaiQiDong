/** Main UI controller — talks to Python via pywebview.api */

const api = () => window.pywebview && window.pywebview.api;
const THEME_STORAGE_KEY = "mouse-sketch-drawer.theme";
const THEMES = new Set(["ironclad", "silent", "regent", "necrobinder", "defect"]);

let wheelMenu = null;
let toastTimer = null;
let canvasEditor = null;
let currentState = null;
let manageMode = null;

function applyTheme(theme, persist = true) {
  const selected = THEMES.has(theme) ? theme : "ironclad";
  document.documentElement.dataset.theme = selected;
  document.querySelectorAll(".theme-dot").forEach((dot) => {
    dot.setAttribute("aria-pressed", String(dot.dataset.themeValue === selected));
  });
  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, selected);
    } catch (_error) {
      // Theme selection still applies when storage is unavailable.
    }
  }
}

function showToast(message) {
  if (!message) return;
  const el = document.getElementById("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 2800);
}

function showPage(pageId) {
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("page--active", page.id === `page-${pageId}`);
  });
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageId);
  });
  if (pageId === "canvas" && canvasEditor) {
    requestAnimationFrame(() => canvasEditor.resize());
  }
}

function renderHistory(history) {
  const list = document.getElementById("history-list");
  list.innerHTML = "";
  if (!history.length) {
    list.innerHTML = '<li class="history-item history-item--empty"><span>暂无记录</span></li>';
    return;
  }
  for (const entry of history) {
    const li = document.createElement("li");
    li.className = "history-item";
    const eventCount = Number.isFinite(Number(entry.eventCount)) ? Number(entry.eventCount) : 0;
    const drawButton = entry.drawButton === "left" ? "左键" : "右键";
    const failureDetail = entry.message ? ` · ${entry.message}` : "";
    const exactTime = entry.timestamp
      ? String(entry.timestamp).replace("T", " ")
      : entry.time;
    li.title = `${entry.presetName} · ${entry.status} · ${exactTime}` +
      ` · 缩放 ${entry.scale}x · ${drawButton}` +
      ` · ${entry.durationSec}s · ${eventCount} 个事件${failureDetail}`;
    li.innerHTML = `
      <strong class="history-name">${escapeHtml(entry.presetName)}</strong>
      <span class="history-status" title="${escapeHtml(entry.message || entry.status)}">${escapeHtml(entry.status)}</span>
      <span class="history-detail">${escapeHtml(entry.time)}</span>
      <span class="history-detail" title="缩放">${entry.scale}×</span>
      <span class="history-detail history-draw-button">${drawButton}</span>
      <span class="history-detail" title="耗时">${entry.durationSec}s</span>
      <span class="history-detail history-events" title="输入事件数">${eventCount}点</span>
    `;
    list.appendChild(li);
  }
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function customPresets() {
  const presets = currentState && Array.isArray(currentState.presets)
    ? currentState.presets
    : [];
  return presets.filter((preset) =>
    Array.isArray(preset.tags) && preset.tags.includes("自定义")
  );
}

function renderManagedPresets() {
  const list = document.getElementById("manage-preset-list");
  if (!list) return;
  const presets = customPresets();
  if (!presets.length) {
    list.innerHTML = '<p class="manage-preset-empty">暂无自定义预设</p>';
    return;
  }

  list.innerHTML = presets.map((preset) => {
    const id = escapeHtml(preset.id);
    const name = escapeHtml(preset.name);
    const preview = preset.previewUrl
      ? `<img class="managed-preset__preview" src="${escapeHtml(preset.previewUrl)}" alt="" />`
      : '<span class="managed-preset__preview managed-preset__preview--empty" aria-hidden="true"></span>';
    if (manageMode && manageMode.id === preset.id && manageMode.type === "rename") {
      return `
        <div class="managed-preset" data-preset-id="${id}">
          ${preview}
          <input class="managed-preset__input" type="text" maxlength="40" value="${name}" aria-label="新预设名称" />
          <div class="managed-preset__actions">
            <button class="managed-preset__button" type="button" data-manage-action="rename-cancel">取消</button>
            <button class="managed-preset__button" type="button" data-manage-action="rename-save">保存</button>
          </div>
        </div>`;
    }
    if (manageMode && manageMode.id === preset.id && manageMode.type === "delete") {
      return `
        <div class="managed-preset" data-preset-id="${id}">
          ${preview}
          <span class="managed-preset__confirm" title="${name}">确定删除「${name}」？</span>
          <div class="managed-preset__actions">
            <button class="managed-preset__button" type="button" data-manage-action="delete-cancel">取消</button>
            <button class="managed-preset__button managed-preset__button--danger" type="button" data-manage-action="delete-confirm">删除</button>
          </div>
        </div>`;
    }
    return `
      <div class="managed-preset" data-preset-id="${id}">
        ${preview}
        <span class="managed-preset__name" title="${name}">${name}</span>
        <div class="managed-preset__actions">
          <button class="managed-preset__button" type="button" data-manage-action="rename-start">重命名</button>
          <button class="managed-preset__button managed-preset__button--danger" type="button" data-manage-action="delete-start">删除</button>
        </div>
      </div>`;
  }).join("");
}

async function callApi(method, ...args) {
  const bridge = api();
  if (!bridge || typeof bridge[method] !== "function") return null;
  return bridge[method](...args);
}

function renderScaleHint(state) {
  const el = document.getElementById("scale-hint");
  if (!el || !state.transform) return;
  const { zoom, minZoom, maxZoom } = state.transform;
  if (state.appState === "ready") {
    el.textContent = `缩放 ${zoom}x（屏幕 1/4 默认，范围 ${minZoom}–${maxZoom}，滚轮调整）`;
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

window.app = {
  async onStateUpdate(state) {
    currentState = state;
    document.getElementById("topmost-switch").checked = !!state.topmost;
    const manageButton = document.getElementById("btn-manage-presets");
    if (manageButton) manageButton.disabled = state.appState !== "idle";
    const drawButton = state.drawButton === "left" ? "left" : "right";
    document.querySelectorAll('input[name="draw-button"]').forEach((input) => {
      input.checked = input.value === drawButton;
    });
    renderHistory(state.history || []);
    renderScaleHint(state);

    if (wheelMenu) {
      const samePresets =
        wheelMenu.cards.length === state.presets.length &&
        wheelMenu.cards.every((card, index) => {
          const preset = state.presets[index];
          const tags = Array.isArray(preset.tags) ? preset.tags : [];
          return card.id === preset.id &&
            card.name === preset.name &&
            card.tags.length === tags.length &&
            card.tags.every((tag, tagIndex) => tag === tags[tagIndex]);
        });
      if (!samePresets) {
        wheelMenu.setPresets(state.presets);
      }
      if (state.selectedPresetId) {
        wheelMenu.bringToFront(state.selectedPresetId);
      }
      wheelMenu.setEnabled(!!state.cardsEnabled);
    }

    const manageDialog = document.getElementById("manage-presets-dialog");
    if (manageDialog && manageDialog.open) renderManagedPresets();

    if (state.message) showToast(state.message);
  },
};

function initUi() {
  applyTheme(document.documentElement.dataset.theme, false);

  canvasEditor = new window.CanvasPresetEditor(document.getElementById("sketch-canvas"));

  wheelMenu = new window.WheelCardMenu(document.getElementById("wheel-root"), {
    onTopChanged: (presetId) => callApi("select_preset", presetId),
    onConfirm: () => callApi("confirm_card"),
  });

  document.getElementById("nav").addEventListener("click", (e) => {
    const btn = e.target.closest(".nav-btn");
    if (!btn) return;
    showPage(btn.dataset.page);
  });

  document.getElementById("btn-canvas-clear").addEventListener("click", () => {
    canvasEditor.clear();
  });

  const manageDialog = document.getElementById("manage-presets-dialog");
  const manageList = document.getElementById("manage-preset-list");
  document.getElementById("btn-manage-presets").addEventListener("click", () => {
    manageMode = null;
    renderManagedPresets();
    manageDialog.showModal();
  });
  document.getElementById("btn-manage-close").addEventListener("click", () => {
    manageDialog.close();
  });
  manageDialog.addEventListener("close", () => {
    manageMode = null;
  });
  manageList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-manage-action]");
    const row = event.target.closest("[data-preset-id]");
    if (!button || !row) return;
    const presetId = row.dataset.presetId;
    const action = button.dataset.manageAction;
    if (action === "rename-start" || action === "delete-start") {
      manageMode = {id: presetId, type: action.startsWith("rename") ? "rename" : "delete"};
      renderManagedPresets();
      const input = manageList.querySelector(".managed-preset__input");
      if (input) {
        input.focus();
        input.select();
      }
      return;
    }
    if (action === "rename-cancel" || action === "delete-cancel") {
      manageMode = null;
      renderManagedPresets();
      return;
    }
    button.disabled = true;
    try {
      if (action === "rename-save") {
        const input = row.querySelector(".managed-preset__input");
        const name = input ? input.value.trim() : "";
        if (!name) {
          showToast("预设名称不能为空。");
          if (input) input.focus();
          return;
        }
        const state = await callApi("rename_custom_preset", presetId, name);
        if (state) {
          if (state.renamedPresetId) manageMode = null;
          window.app.onStateUpdate(state);
        }
        return;
      }
      if (action === "delete-confirm") {
        const state = await callApi("delete_custom_preset", presetId);
        if (state) {
          if (state.deletedPresetId) manageMode = null;
          window.app.onStateUpdate(state);
        }
      }
    } catch (error) {
      showToast(error.message || "预设管理操作失败，请重试。");
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  });

  const saveDialog = document.getElementById("save-preset-dialog");
  const saveForm = document.getElementById("save-preset-form");
  const nameInput = document.getElementById("preset-name-input");
  const nameError = document.getElementById("preset-name-error");
  const saveConfirm = document.getElementById("btn-save-confirm");

  const showNameError = (message) => {
    nameError.textContent = message || "";
    nameError.hidden = !message;
  };

  document.getElementById("btn-canvas-save").addEventListener("click", () => {
    if (!canvasEditor.hasDrawing()) {
      showToast("请先在画布上拖动画笔绘制图案。");
      return;
    }
    nameInput.value = "";
    showNameError("");
    saveDialog.showModal();
    requestAnimationFrame(() => nameInput.focus());
  });

  document.getElementById("btn-save-cancel").addEventListener("click", () => {
    if (!saveConfirm.disabled) saveDialog.close();
  });

  nameInput.addEventListener("input", () => showNameError(""));
  saveForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = nameInput.value.trim();
    if (!name) {
      showNameError("请输入预设名称。");
      nameInput.focus();
      return;
    }

    let payload;
    try {
      payload = canvasEditor.buildPayload(name);
    } catch (error) {
      showNameError(error.message || "画布数据无效。");
      return;
    }

    saveConfirm.disabled = true;
    saveConfirm.textContent = "保存中…";
    try {
      const state = await callApi("save_canvas_preset", payload);
      if (!state) {
        showNameError("无法连接到程序后端。");
        return;
      }
      window.app.onStateUpdate(state);
      if (state.savedPresetId) {
        canvasEditor.clear();
        saveDialog.close();
      } else {
        showNameError(state.message || "保存失败，请重试。");
      }
    } catch (error) {
      showNameError(error.message || "保存失败，请重试。");
    } finally {
      saveConfirm.disabled = false;
      saveConfirm.textContent = "确认";
    }
  });

  document.getElementById("btn-history-refresh").addEventListener("click", async () => {
    const state = await callApi("get_state");
    if (state) window.app.onStateUpdate(state);
  });

  document.getElementById("topmost-switch").addEventListener("change", async (e) => {
    await callApi("set_topmost", e.target.checked);
  });

  document.getElementById("draw-button-picker").addEventListener("change", async (e) => {
    if (!e.target.matches('input[name="draw-button"]')) return;
    const state = await callApi("set_draw_button", e.target.value);
    if (state) window.app.onStateUpdate(state);
  });

  document.getElementById("theme-picker").addEventListener("click", (e) => {
    const dot = e.target.closest(".theme-dot");
    if (dot) applyTheme(dot.dataset.themeValue);
  });

  document.getElementById("btn-close").addEventListener("click", () => {
    callApi("close_window");
  });

  document.getElementById("btn-about").addEventListener("click", () => {
    document.getElementById("about-dialog").showModal();
  });

  document.getElementById("btn-about-close").addEventListener("click", () => {
    document.getElementById("about-dialog").close();
  });
}

function waitForApi() {
  if (api()) {
    initUi();
    callApi("get_state").then((state) => {
      if (state) window.app.onStateUpdate(state);
    });
    return;
  }
  setTimeout(waitForApi, 50);
}

waitForApi();

/* ──────────────────────────────────────────────────────────────────
   Annotation Wizard — Human-in-the-Loop Annotation Canvas Engine
   ────────────────────────────────────────────────────────────────── */
(function () {
  "use strict";

  // ─── Class Config ────────────────────────────────────────────────
  const CLASS_CONFIG = {
    D00: { id: 0, color: "#ef4444", label: "Longitudinal" },
    D10: { id: 1, color: "#f59e0b", label: "Transverse" },
    D20: { id: 2, color: "#3b82f6", label: "Alligator" },
    D40: { id: 3, color: "#14b8a6", label: "Pothole" },
  };
  const CLASS_BY_ID = {};
  for (const [name, cfg] of Object.entries(CLASS_CONFIG)) {
    CLASS_BY_ID[cfg.id] = { name, ...cfg };
  }

  // ─── Canvas State ────────────────────────────────────────────────
  const state = {
    jobId: null,
    images: [],          // [{id, filename, status, width, height, annotation_count, image_url}]
    currentIndex: -1,
    currentImageData: null,  // full data incl. annotations
    boxes: [],           // [{id, class_id, class_name, x_min, y_min, x_max, y_max, confidence, is_prediction, is_modified}]
    selectedBoxIdx: -1,
    dirtyImages: new Set(),  // image IDs with unsaved edits
    tool: "select",      // "select" | "draw"
    zoom: 1.0,
    panX: 0,
    panY: 0,
    filter: "all",
    searchQuery: "",
    // canvas image element
    imageEl: null,
    // interaction tracking
    isDragging: false,
    isResizing: false,
    isDrawing: false,
    dragStartX: 0,
    dragStartY: 0,
    drawRect: null,      // {x1, y1, x2, y2} during draw
    resizeHandle: null,  // "nw"|"ne"|"se"|"sw"|"n"|"s"|"e"|"w"
    boxSnapshot: null,   // snapshot before drag/resize
    isPanning: false,
    panStartX: 0,
    panStartY: 0,
    panStartViewX: 0,
    panStartViewY: 0,
    saveTimeout: null,
  };

  // ─── DOM References ──────────────────────────────────────────────
  const $ = id => document.getElementById(id);
  const canvas = $("interactive-editor-canvas");
  const ctx = canvas ? canvas.getContext("2d") : null;
  const viewport = $("canvas-stage-viewport");
  const transformWrapper = $("canvas-transform-wrapper");
  const emptyState = $("canvas-empty-state");

  // Guard: only run if editor tab exists
  if (!canvas || !ctx) return;

  // ─── API Key Helper ──────────────────────────────────────────────
  // Reads the API key stored by app.js in sessionStorage.
  function getApiKey() {
    return sessionStorage.getItem("aw-api-key") || "";
  }

  // ─── Utility ─────────────────────────────────────────────────────
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function formatConf(v) {
    if (v === null || v === undefined) return "—";
    return (parseFloat(v) * 100).toFixed(0) + "%";
  }

  function classColor(name) {
    return (CLASS_CONFIG[name] || CLASS_CONFIG.D00).color;
  }

  function classId(name) {
    return (CLASS_CONFIG[name] || CLASS_CONFIG.D00).id;
  }

  // ─── Header Update ───────────────────────────────────────────────
  function updateHeader() {
    const title = $("editor-dataset-title");
    const imgCountBadge = $("editor-image-count-badge");
    const progressBadge = $("editor-progress-badge");
    const unsavedBadge = $("editor-unsaved-badge");
    const unsavedText = $("editor-unsaved-text");

    if (!title) return;

    if (state.jobId && state.images.length > 0) {
      const total = state.images.length;
      const reviewed = state.images.filter(i => i.status === "reviewed").length;
      const pct = total ? Math.round((reviewed / total) * 100) : 0;

      imgCountBadge && (imgCountBadge.textContent = `Images · ${total}`);
      progressBadge && (progressBadge.textContent = `Reviewed: ${reviewed}/${total} (${pct}%)`);

      if (state.dirtyImages.size > 0) {
        unsavedBadge && unsavedBadge.classList.remove("hidden");
        unsavedText && (unsavedText.textContent = `Unsaved edits: ${state.dirtyImages.size}`);
      } else {
        unsavedBadge && unsavedBadge.classList.add("hidden");
      }
    } else {
      title.textContent = "No dataset loaded";
      imgCountBadge && (imgCountBadge.textContent = "Images · 0");
      progressBadge && (progressBadge.textContent = "Reviewed: 0/0 (0%)");
      unsavedBadge && unsavedBadge.classList.add("hidden");
    }

    // Enable/disable export & save buttons
    const exportBtn = $("editor-export-btn");
    const saveBtn = $("editor-save-btn");
    if (exportBtn) exportBtn.disabled = !state.jobId;
    if (saveBtn) saveBtn.disabled = state.dirtyImages.size === 0;
  }

  // ─── Image List Rendering ────────────────────────────────────────
  function renderImageList() {
    const list = $("editor-images-list");
    const emptyMsg = $("editor-gallery-empty");
    if (!list) return;

    let images = state.images;
    if (state.filter !== "all") {
      images = images.filter(img => img.status === state.filter);
    }
    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      images = images.filter(img => img.filename.toLowerCase().includes(q));
    }

    list.innerHTML = "";
    if (images.length === 0) {
      const p = document.createElement("p");
      p.className = "empty-gallery";
      p.textContent = state.images.length === 0
        ? "No dataset loaded. Upload images or a ZIP above."
        : "No images match the current filter.";
      list.appendChild(p);
      return;
    }

    images.forEach(img => {
      const originalIdx = state.images.findIndex(i => i.id === img.id);
      const card = document.createElement("div");
      card.className = "image-item-card" + (originalIdx === state.currentIndex ? " active" : "");
      card.setAttribute("role", "option");
      card.setAttribute("aria-selected", originalIdx === state.currentIndex ? "true" : "false");
      card.dataset.imgId = img.id;

      const isDirty = state.dirtyImages.has(img.id);
      const statusLabel = isDirty ? "editing" : img.status;

      card.innerHTML = `
        <div class="item-thumb-wrapper">
          <img src="${img.image_url}" alt="${img.filename}" loading="lazy" />
        </div>
        <div class="item-info">
          <div class="item-filename" title="${img.filename}">${img.filename}</div>
          <div class="item-meta-row">
            <span class="status-pill ${statusLabel.replace("_", "-")}">${statusLabel.replace("_", " ")}</span>
            <span class="box-count-tag">${img.annotation_count || 0} box${(img.annotation_count || 0) !== 1 ? "es" : ""}</span>
          </div>
        </div>`;

      card.addEventListener("click", () => loadImageByOriginalIndex(originalIdx));
      list.appendChild(card);
    });
  }

  // ─── Load Image ──────────────────────────────────────────────────
  async function loadImageByOriginalIndex(idx) {
    if (idx < 0 || idx >= state.images.length) return;

    // Auto-save current image if dirty before navigating
    if (state.currentIndex >= 0 && state.dirtyImages.has(state.images[state.currentIndex]?.id)) {
      await saveCurrentImage(false);
    }

    state.currentIndex = idx;
    state.selectedBoxIdx = -1;
    state.boxes = [];
    state.imageEl = null;
    state.zoom = 1.0;
    state.panX = 0;
    state.panY = 0;

    const img = state.images[idx];
    if (!img) return;

    updateNavControls();
    renderImageList();

    // Fetch image annotations from backend
    try {
      const res = await fetch(`/datasets/jobs/${state.jobId}/images/${img.id}`, {
        headers: { "X-API-Key": getApiKey() },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.currentImageData = await res.json();
      state.boxes = (state.currentImageData.annotations || []).map(a => ({ ...a }));
    } catch (e) {
      console.warn("Failed to load annotations:", e);
      state.boxes = [];
    }

    // Load image onto canvas
    const imageEl = new Image();
    imageEl.crossOrigin = "anonymous";
    imageEl.onload = () => {
      state.imageEl = imageEl;
      fitToViewport();
      render();
      updatePropertiesPanel();
      updateBoxesList();
      updateStatusBar();
    };
    imageEl.onerror = () => {
      console.warn("Image load failed for", img.image_url);
    };
    imageEl.src = img.image_url;

    // Show/hide empty state
    if (emptyState) emptyState.style.display = "none";

    // Update reviewed toggle
    const toggle = $("editor-reviewed-toggle");
    if (toggle) toggle.checked = img.status === "reviewed";

    setSaveState("saved");
  }

  // ─── Canvas Fit & Zoom ───────────────────────────────────────────
  function fitToViewport() {
    if (!state.imageEl || !viewport) return;
    const vw = viewport.clientWidth - 32;
    const vh = viewport.clientHeight - 32;
    const iw = state.imageEl.naturalWidth;
    const ih = state.imageEl.naturalHeight;
    const scale = Math.min(vw / iw, vh / ih, 1.5);
    state.zoom = Math.max(0.05, scale);
    state.panX = 0;
    state.panY = 0;
    applyTransform();
    updateZoomDisplay();
  }

  function applyTransform() {
    if (!state.imageEl || !canvas || !transformWrapper) return;
    const iw = state.imageEl.naturalWidth;
    const ih = state.imageEl.naturalHeight;
    canvas.width = iw;
    canvas.height = ih;
    const w = Math.round(iw * state.zoom);
    const h = Math.round(ih * state.zoom);
    transformWrapper.style.width = w + "px";
    transformWrapper.style.height = h + "px";
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    // Pan via viewport scroll
    if (viewport) {
      viewport.scrollLeft = state.panX;
      viewport.scrollTop = state.panY;
    }
  }

  function updateZoomDisplay() {
    const el = $("canvas-zoom-val");
    if (el) el.textContent = Math.round(state.zoom * 100) + "%";
  }

  function changeZoom(delta) {
    const oldZoom = state.zoom;
    state.zoom = clamp(state.zoom * (1 + delta), 0.05, 8);
    applyTransform();
    updateZoomDisplay();
    render();
  }

  // ─── Main Render ─────────────────────────────────────────────────
  function render() {
    if (!ctx || !canvas) return;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // Draw image
    if (state.imageEl) {
      ctx.drawImage(state.imageEl, 0, 0, W, H);
    }

    // Draw each box
    state.boxes.forEach((box, idx) => {
      drawBox(box, idx === state.selectedBoxIdx);
    });

    // Draw in-progress rectangle during draw mode
    if (state.isDrawing && state.drawRect) {
      const r = normalizeRect(state.drawRect);
      const color = classColor(state.newBoxClass || "D00");
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.fillStyle = hexToRgba(color, 0.12);
      ctx.fillRect(r.x, r.y, r.w, r.h);
      ctx.restore();
    }
  }

  function drawBox(box, isSelected) {
    const x = box.x_min;
    const y = box.y_min;
    const w = box.x_max - box.x_min;
    const h = box.y_max - box.y_min;
    const color = classColor(box.class_name);

    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = isSelected ? 2.5 : 1.8;
    ctx.setLineDash(box.is_prediction && !box.is_modified ? [5, 3] : []);
    ctx.strokeRect(x, y, w, h);

    // Fill
    ctx.fillStyle = hexToRgba(color, isSelected ? 0.15 : 0.07);
    ctx.fillRect(x, y, w, h);
    ctx.setLineDash([]);

    // Label background
    const label = `${box.class_name}`;
    const confStr = box.confidence !== null && box.confidence !== undefined
      ? ` ${(box.confidence * 100).toFixed(0)}%` : "";
    const fullLabel = label + confStr;
    ctx.font = "bold 12px Inter, sans-serif";
    const textW = ctx.measureText(fullLabel).width;
    const labelH = 18;
    const labelY = y > labelH ? y - labelH : y;

    ctx.fillStyle = color;
    ctx.fillRect(x, labelY, textW + 8, labelH);
    ctx.fillStyle = "#fff";
    ctx.fillText(fullLabel, x + 4, labelY + 13);

    // Draw resize handles if selected
    if (isSelected) {
      drawHandles(x, y, w, h, color);
    }
    ctx.restore();
  }

  const HANDLE_SIZE = 8;

  function drawHandles(x, y, w, h, color) {
    const handles = getHandlePositions(x, y, w, h);
    ctx.fillStyle = "#fff";
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    Object.values(handles).forEach(([hx, hy]) => {
      ctx.beginPath();
      ctx.arc(hx, hy, HANDLE_SIZE / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    });
  }

  function getHandlePositions(x, y, w, h) {
    const mx = x + w / 2, my = y + h / 2;
    return {
      nw: [x, y], n: [mx, y], ne: [x + w, y],
      w: [x, my],               e: [x + w, my],
      sw: [x, y + h], s: [mx, y + h], se: [x + w, y + h],
    };
  }

  function normalizeRect(r) {
    return {
      x: Math.min(r.x1, r.x2),
      y: Math.min(r.y1, r.y2),
      w: Math.abs(r.x2 - r.x1),
      h: Math.abs(r.y2 - r.y1),
    };
  }

  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  // ─── Canvas → Image Coordinate Conversion ────────────────────────
  function canvasPosFromEvent(e) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    };
  }

  // ─── Hit Testing ─────────────────────────────────────────────────
  function hitTestHandle(pos, box) {
    const x = box.x_min, y = box.y_min;
    const w = box.x_max - x, h = box.y_max - y;
    const handles = getHandlePositions(x, y, w, h);
    for (const [name, [hx, hy]] of Object.entries(handles)) {
      if (Math.hypot(pos.x - hx, pos.y - hy) <= HANDLE_SIZE) return name;
    }
    return null;
  }

  function hitTestBox(pos) {
    // Reverse so topmost drawn box is selected first
    for (let i = state.boxes.length - 1; i >= 0; i--) {
      const b = state.boxes[i];
      if (pos.x >= b.x_min && pos.x <= b.x_max && pos.y >= b.y_min && pos.y <= b.y_max) {
        return i;
      }
    }
    return -1;
  }

  function getCursorStyle(pos) {
    if (state.tool === "draw") return "crosshair";
    if (state.selectedBoxIdx >= 0) {
      const box = state.boxes[state.selectedBoxIdx];
      const handle = hitTestHandle(pos, box);
      if (handle) {
        const cursors = { nw: "nw-resize", ne: "ne-resize", se: "se-resize", sw: "sw-resize",
          n: "n-resize", s: "s-resize", e: "e-resize", w: "w-resize" };
        return cursors[handle] || "default";
      }
    }
    const boxIdx = hitTestBox(pos);
    return boxIdx >= 0 ? "move" : "default";
  }

  // ─── Mouse / Touch Handlers ──────────────────────────────────────
  function onPointerDown(e) {
    if (e.button === 1 || e.button === 2) return;
    e.preventDefault();
    const pos = canvasPosFromEvent(e);

    if (state.tool === "draw") {
      state.isDrawing = true;
      state.drawRect = { x1: pos.x, y1: pos.y, x2: pos.x, y2: pos.y };
      state.newBoxClass = getActiveDrawClass();
      return;
    }

    // Select tool: check resize handles first
    if (state.selectedBoxIdx >= 0) {
      const box = state.boxes[state.selectedBoxIdx];
      const handle = hitTestHandle(pos, box);
      if (handle) {
        state.isResizing = true;
        state.resizeHandle = handle;
        state.boxSnapshot = { ...box };
        state.dragStartX = pos.x;
        state.dragStartY = pos.y;
        return;
      }
    }

    // Check if clicking a box
    const hitIdx = hitTestBox(pos);
    if (hitIdx >= 0) {
      state.selectedBoxIdx = hitIdx;
      state.isDragging = true;
      state.dragStartX = pos.x;
      state.dragStartY = pos.y;
      state.boxSnapshot = { ...state.boxes[hitIdx] };
      updatePropertiesPanel();
      updateBoxesList();
      render();
      return;
    }

    // Click on empty canvas: deselect
    state.selectedBoxIdx = -1;
    updatePropertiesPanel();
    updateBoxesList();
    render();
  }

  function onPointerMove(e) {
    e.preventDefault();
    const pos = canvasPosFromEvent(e);
    canvas.style.cursor = getCursorStyle(pos);

    if (state.isDrawing && state.drawRect) {
      const iw = state.imageEl ? state.imageEl.naturalWidth : canvas.width;
      const ih = state.imageEl ? state.imageEl.naturalHeight : canvas.height;
      state.drawRect.x2 = clamp(pos.x, 0, iw);
      state.drawRect.y2 = clamp(pos.y, 0, ih);
      render();
      return;
    }

    if (state.isResizing && state.resizeHandle && state.boxSnapshot) {
      const dx = pos.x - state.dragStartX;
      const dy = pos.y - state.dragStartY;
      const snap = state.boxSnapshot;
      const iw = state.imageEl ? state.imageEl.naturalWidth : canvas.width;
      const ih = state.imageEl ? state.imageEl.naturalHeight : canvas.height;
      const box = state.boxes[state.selectedBoxIdx];
      const h = state.resizeHandle;

      let x1 = snap.x_min, y1 = snap.y_min, x2 = snap.x_max, y2 = snap.y_max;
      if (h.includes("w")) x1 = clamp(snap.x_min + dx, 0, x2 - 2);
      if (h.includes("e")) x2 = clamp(snap.x_max + dx, x1 + 2, iw);
      if (h.includes("n")) y1 = clamp(snap.y_min + dy, 0, y2 - 2);
      if (h.includes("s")) y2 = clamp(snap.y_max + dy, y1 + 2, ih);

      box.x_min = x1; box.y_min = y1; box.x_max = x2; box.y_max = y2;
      box.is_modified = true;
      markDirty();
      render();
      updateCoordDisplay(box);
      return;
    }

    if (state.isDragging && state.boxSnapshot) {
      const dx = pos.x - state.dragStartX;
      const dy = pos.y - state.dragStartY;
      const snap = state.boxSnapshot;
      const iw = state.imageEl ? state.imageEl.naturalWidth : canvas.width;
      const ih = state.imageEl ? state.imageEl.naturalHeight : canvas.height;
      const bw = snap.x_max - snap.x_min;
      const bh = snap.y_max - snap.y_min;
      const box = state.boxes[state.selectedBoxIdx];

      box.x_min = clamp(snap.x_min + dx, 0, iw - bw);
      box.y_min = clamp(snap.y_min + dy, 0, ih - bh);
      box.x_max = box.x_min + bw;
      box.y_max = box.y_min + bh;
      box.is_modified = true;
      markDirty();
      render();
      updateCoordDisplay(box);
    }
  }

  function onPointerUp(e) {
    e.preventDefault();

    if (state.isDrawing && state.drawRect) {
      const r = normalizeRect(state.drawRect);
      if (r.w > 5 && r.h > 5) {
        const iw = state.imageEl ? state.imageEl.naturalWidth : canvas.width;
        const ih = state.imageEl ? state.imageEl.naturalHeight : canvas.height;
        const className = state.newBoxClass || "D00";
        const newBox = {
          id: null,
          class_id: classId(className),
          class_name: className,
          x_min: clamp(r.x, 0, iw),
          y_min: clamp(r.y, 0, ih),
          x_max: clamp(r.x + r.w, 0, iw),
          y_max: clamp(r.y + r.h, 0, ih),
          confidence: null,
          is_prediction: false,
          is_modified: true,
        };
        state.boxes.push(newBox);
        state.selectedBoxIdx = state.boxes.length - 1;
        markDirty();
        updatePropertiesPanel();
        updateBoxesList();
        updateImageAnnotationCount();
      }
      state.drawRect = null;
      state.isDrawing = false;
      render();
      return;
    }

    if (state.isResizing || state.isDragging) {
      // Update the annotation count display
      updateBoxesList();
    }

    state.isDragging = false;
    state.isResizing = false;
    state.resizeHandle = null;
    state.boxSnapshot = null;
  }

  function getActiveDrawClass() {
    const active = document.querySelector(".class-card-btn.active");
    return active ? (active.dataset.class || "D00") : "D00";
  }

  // ─── Properties Panel Update ─────────────────────────────────────
  function updatePropertiesPanel() {
    const propCard = $("prop-box-card");
    const noSel = $("prop-no-selection");

    if (state.selectedBoxIdx < 0 || !state.boxes[state.selectedBoxIdx]) {
      propCard && (propCard.style.display = "none");
      noSel && noSel.classList.remove("hidden");
      return;
    }

    propCard && (propCard.style.display = "flex");
    noSel && noSel.classList.add("hidden");

    const box = state.boxes[state.selectedBoxIdx];
    const boxTitle = $("prop-box-title");
    const confBadge = $("prop-conf-badge");

    if (boxTitle) boxTitle.textContent = `Box ${state.selectedBoxIdx + 1}`;
    if (confBadge) {
      confBadge.textContent = box.confidence !== null && box.confidence !== undefined
        ? `Confidence ${formatConf(box.confidence)}` : "Manually drawn";
    }

    // Highlight active class button
    document.querySelectorAll(".class-card-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.class === box.class_name);
    });

    updateCoordDisplay(box);
  }

  function updateCoordDisplay(box) {
    const round = v => Math.round(v);
    const el = id => document.getElementById(id);
    el("coord-val-x1") && (el("coord-val-x1").textContent = round(box.x_min));
    el("coord-val-y1") && (el("coord-val-y1").textContent = round(box.y_min));
    el("coord-val-x2") && (el("coord-val-x2").textContent = round(box.x_max));
    el("coord-val-y2") && (el("coord-val-y2").textContent = round(box.y_max));
    el("coord-val-w") && (el("coord-val-w").textContent = round(box.x_max - box.x_min));
    el("coord-val-h") && (el("coord-val-h").textContent = round(box.y_max - box.y_min));
  }

  // ─── Boxes List (right panel) ────────────────────────────────────
  function updateBoxesList() {
    const container = $("editor-boxes-container");
    const emptyMsg = $("editor-empty-boxes-msg");
    const countBadge = $("editor-current-box-count");

    if (!container) return;
    if (countBadge) countBadge.textContent = state.boxes.length;

    container.innerHTML = "";

    if (state.boxes.length === 0) {
      const p = document.createElement("p");
      p.className = "empty-boxes-msg";
      p.textContent = "No bounding boxes on this image.";
      container.appendChild(p);
      return;
    }

    state.boxes.forEach((box, idx) => {
      const row = document.createElement("div");
      row.className = "box-list-row" + (idx === state.selectedBoxIdx ? " active" : "");

      const cn = box.class_name.toLowerCase();
      const conf = formatConf(box.confidence);

      row.innerHTML = `
        <div class="box-row-left">
          <span class="box-row-tag ${cn}">${box.class_name}</span>
          <span class="box-row-title">Box ${idx + 1}</span>
          ${box.is_prediction && !box.is_modified ? '<span style="font-size:9px;color:var(--muted);background:#f3f4f6;padding:1px 4px;border-radius:3px;">AI</span>' : ""}
        </div>
        <div class="box-row-right">
          <span class="box-row-conf">${conf}</span>
          <button class="box-row-del-btn" data-idx="${idx}" type="button" title="Delete box" aria-label="Delete box ${idx + 1}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>`;

      row.addEventListener("click", (e) => {
        if (e.target.closest(".box-row-del-btn")) return;
        state.selectedBoxIdx = idx;
        updatePropertiesPanel();
        updateBoxesList();
        render();
      });

      row.querySelector(".box-row-del-btn")?.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteBox(parseInt(e.currentTarget.dataset.idx));
      });

      container.appendChild(row);
    });
  }

  // ─── Box Operations ──────────────────────────────────────────────
  function deleteBox(idx) {
    if (idx < 0 || idx >= state.boxes.length) return;
    state.boxes.splice(idx, 1);
    if (state.selectedBoxIdx === idx) state.selectedBoxIdx = -1;
    else if (state.selectedBoxIdx > idx) state.selectedBoxIdx--;
    markDirty();
    updatePropertiesPanel();
    updateBoxesList();
    updateImageAnnotationCount();
    render();
  }

  function deleteSelectedBox() {
    deleteBox(state.selectedBoxIdx);
  }

  function duplicateSelectedBox() {
    if (state.selectedBoxIdx < 0) return;
    const orig = state.boxes[state.selectedBoxIdx];
    const dupe = {
      ...orig,
      id: null,
      x_min: orig.x_min + 10,
      y_min: orig.y_min + 10,
      x_max: orig.x_max + 10,
      y_max: orig.y_max + 10,
      is_modified: true,
      confidence: null,
    };
    state.boxes.push(dupe);
    state.selectedBoxIdx = state.boxes.length - 1;
    markDirty();
    updatePropertiesPanel();
    updateBoxesList();
    updateImageAnnotationCount();
    render();
  }

  function changeSelectedBoxClass(className) {
    if (state.selectedBoxIdx < 0) return;
    const box = state.boxes[state.selectedBoxIdx];
    box.class_name = className;
    box.class_id = classId(className);
    box.is_modified = true;
    markDirty();
    updatePropertiesPanel();
    updateBoxesList();
    render();
  }

  function updateImageAnnotationCount() {
    if (state.currentIndex < 0) return;
    const img = state.images[state.currentIndex];
    if (img) img.annotation_count = state.boxes.length;
  }

  // ─── Dirty Tracking ──────────────────────────────────────────────
  function markDirty() {
    if (state.currentIndex < 0) return;
    const img = state.images[state.currentIndex];
    if (img) {
      state.dirtyImages.add(img.id);
      setSaveState("unsaved");
    }
    updateHeader();
    scheduleAutoSave();
  }

  function scheduleAutoSave() {
    if (state.saveTimeout) clearTimeout(state.saveTimeout);
    state.saveTimeout = setTimeout(() => saveCurrentImage(false), 3500);
  }

  function setSaveState(s) {
    const dot = document.querySelector(".save-dot");
    const text = $("editor-save-state-text");
    if (!dot || !text) return;
    if (s === "saved") {
      dot.className = "save-dot green";
      text.textContent = "Edits saved";
    } else if (s === "unsaved") {
      dot.className = "save-dot amber";
      text.textContent = "Unsaved changes";
    } else if (s === "saving") {
      dot.className = "save-dot amber";
      text.textContent = "Saving…";
    }
  }

  // ─── Save Image Annotations ──────────────────────────────────────
  async function saveCurrentImage(markReviewed) {
    if (state.currentIndex < 0 || !state.jobId) return;
    const img = state.images[state.currentIndex];
    if (!img) return;

    const reviewToggle = $("editor-reviewed-toggle");
    const isReviewed = markReviewed !== undefined
      ? markReviewed
      : (reviewToggle ? reviewToggle.checked : false);

    const status = isReviewed ? "reviewed" : (state.dirtyImages.has(img.id) ? "editing" : img.status);

    const payload = {
      status,
      annotations: state.boxes.map(b => ({
        id: b.id || null,
        class_id: b.class_id,
        class_name: b.class_name,
        x_min: Math.round(b.x_min * 100) / 100,
        y_min: Math.round(b.y_min * 100) / 100,
        x_max: Math.round(b.x_max * 100) / 100,
        y_max: Math.round(b.y_max * 100) / 100,
        confidence: b.confidence ?? null,
        is_prediction: b.is_prediction || false,
        is_modified: b.is_modified || true,
      })),
    };

    setSaveState("saving");
    try {
      const res = await fetch(`/datasets/jobs/${state.jobId}/images/${img.id}/annotations`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": getApiKey(),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = await res.json();

      // Update local state
      state.boxes = (updated.annotations || []).map(a => ({ ...a }));
      img.status = updated.status || status;
      img.annotation_count = state.boxes.length;
      state.dirtyImages.delete(img.id);

      if (reviewToggle) reviewToggle.checked = img.status === "reviewed";
      setSaveState("saved");
      updateHeader();
      renderImageList();
      updateBoxesList();
    } catch (err) {
      console.error("Save failed:", err);
      setSaveState("unsaved");
    }
  }

  // ─── Navigation ──────────────────────────────────────────────────
  function updateNavControls() {
    const prev = $("canvas-prev-btn");
    const next = $("canvas-next-btn");
    const pos = $("canvas-pos-indicator");
    if (prev) prev.disabled = state.currentIndex <= 0;
    if (next) next.disabled = state.currentIndex >= state.images.length - 1;
    if (pos) pos.textContent = state.images.length > 0
      ? `${state.currentIndex + 1} / ${state.images.length}` : "0 / 0";
  }

  // ─── Status Bar ──────────────────────────────────────────────────
  function updateStatusBar() {
    const dimsEl = $("canvas-status-dims");
    if (dimsEl && state.imageEl) {
      dimsEl.textContent = `${state.imageEl.naturalWidth} × ${state.imageEl.naturalHeight} px`;
    }
  }

  // ─── Tool Switching ──────────────────────────────────────────────
  function setTool(tool) {
    state.tool = tool;
    document.querySelectorAll(".tool-btn").forEach(btn => {
      btn.classList.toggle("active", btn.id === `tool-${tool}`);
    });
    if (viewport) {
      viewport.classList.toggle("drawing-mode", tool === "draw");
    }
  }

  // ─── Dataset Job Creation (Upload) ───────────────────────────────
  async function uploadAndCreateJob(files) {
    if (!getApiKey()) {
      alert("Please connect an API key first (sidebar → API session).");
      return;
    }
    if (!files || files.length === 0) return;

    // Show loading overlay
    const overlay = $("editor-loading-overlay");
    const loadTitle = $("editor-loading-title");
    const loadMsg = $("editor-loading-msg");

    if (overlay) overlay.classList.remove("hidden");
    if (loadTitle) loadTitle.textContent = "Uploading & predicting…";
    if (loadMsg) loadMsg.textContent = "Running YOLO ONNX on each image. This may take a while for large datasets.";

    const formData = new FormData();
    let primaryName = "";
    for (const f of files) {
      formData.append("file", f);
      if (!primaryName) primaryName = f.name;
    }
    formData.append("name", primaryName);

    try {
      const res = await fetch("/datasets/jobs", {
        method: "POST",
        headers: { "X-API-Key": getApiKey() },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const job = await res.json();
      await loadJob(job.job_id);
    } catch (err) {
      console.error("Job creation failed:", err);
      alert("Failed to create dataset job: " + err.message);
    } finally {
      if (overlay) overlay.classList.add("hidden");
    }
  }

  async function loadSampleDataset() {
    if (!getApiKey()) {
      alert("Please connect an API key first.");
      return;
    }

    const overlay = $("editor-loading-overlay");
    const loadTitle = $("editor-loading-title");
    const loadMsg = $("editor-loading-msg");

    if (overlay) overlay.classList.remove("hidden");
    if (loadTitle) loadTitle.textContent = "Loading Sample Road Dataset…";
    if (loadMsg) loadMsg.textContent = "Downloading sample dataset and running YOLO ONNX predictions.";

    try {
      // Download sample dataset ZIP
      const zipRes = await fetch("/sample-dataset");
      if (!zipRes.ok) throw new Error("Could not download sample dataset");
      const zipBlob = await zipRes.blob();
      const zipFile = new File([zipBlob], "sample-road-dataset.zip", { type: "application/zip" });

      const formData = new FormData();
      formData.append("file", zipFile);
      formData.append("name", "sample-road-dataset");

      const res = await fetch("/datasets/jobs", {
        method: "POST",
        headers: { "X-API-Key": getApiKey() },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const job = await res.json();
      await loadJob(job.job_id);
    } catch (err) {
      console.error("Sample load failed:", err);
      alert("Failed to load sample dataset: " + err.message);
    } finally {
      if (overlay) overlay.classList.add("hidden");
    }
  }

  // ─── Load Job by ID ───────────────────────────────────────────────
  async function loadJob(jobId) {
    try {
      const res = await fetch(`/datasets/jobs/${jobId}`, {
        headers: { "X-API-Key": getApiKey() },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      state.jobId = data.id;
      state.images = data.images || [];
      state.currentIndex = -1;
      state.dirtyImages = new Set();
      state.boxes = [];
      state.selectedBoxIdx = -1;

      const title = $("editor-dataset-title");
      if (title) title.textContent = data.name || data.id;

      updateHeader();
      renderImageList();
      updateNavControls();

      // Automatically load first image
      if (state.images.length > 0) {
        await loadImageByOriginalIndex(0);
      }

      // Switch to editor tab
      const editorTab = document.querySelector(".nav-item[data-tab='editor']");
      if (editorTab) editorTab.click();

      return data;
    } catch (err) {
      console.error("Failed to load job:", err);
      alert("Failed to load dataset job: " + err.message);
    }
  }

  // ─── Export YOLO Labels ──────────────────────────────────────────
  async function exportJob() {
    if (!state.jobId) return;

    // Save current image first
    if (state.dirtyImages.size > 0) {
      await saveCurrentImage(false);
    }

    try {
      const res = await fetch(`/datasets/jobs/${state.jobId}/export`, {
        headers: { "X-API-Key": getApiKey() },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const cd = res.headers.get("content-disposition") || "";
      const fnMatch = cd.match(/filename[^;=\n]*=([^;\n]*)/);
      a.download = fnMatch ? fnMatch[1].replace(/['"]/g, "") : "annotation-wizard-labels.zip";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
      alert("Export failed: " + err.message);
    }
  }

  // ─── Connect "Review in Canvas" button on dataset tab ────────────
  function hookDatasetTabReviewButton() {
    // "Review & Edit in Canvas" button in the dataset tab
    const reviewBtn = document.querySelector("#zip-review-button");
    if (reviewBtn) {
      reviewBtn.addEventListener("click", async () => {
        const fileInput = document.querySelector("#zip-file-input");
        const file = fileInput && fileInput.files[0];
        if (!file) return;
        await uploadAndCreateJob([file]);
      });
    }

    // "Review Demo in Canvas" button
    const sampleCanvasBtn = document.querySelector("#open-sample-canvas-btn");
    if (sampleCanvasBtn) {
      sampleCanvasBtn.addEventListener("click", () => loadSampleDataset());
    }
  }

  // ─── Keyboard Shortcuts ──────────────────────────────────────────
  document.addEventListener("keydown", (e) => {
    // Only handle shortcuts when editor tab is active
    const editorTab = document.querySelector("#tab-editor");
    if (!editorTab || !editorTab.classList.contains("active")) return;
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

    const ctrl = e.ctrlKey || e.metaKey;

    if (ctrl && e.key === "s") {
      e.preventDefault();
      saveCurrentImage(false);
      return;
    }

    switch (e.key) {
      case "v": case "V": case "s": case "S":
        setTool("select"); break;
      case "b": case "B": case "d": case "D":
        setTool("draw"); break;
      case "Delete": case "Backspace":
        if (state.selectedBoxIdx >= 0) deleteSelectedBox();
        break;
      case "1": changeSelectedBoxClass("D00"); break;
      case "2": changeSelectedBoxClass("D10"); break;
      case "3": changeSelectedBoxClass("D20"); break;
      case "4": changeSelectedBoxClass("D40"); break;
      case "ArrowLeft": case "[":
        if (state.currentIndex > 0) loadImageByOriginalIndex(state.currentIndex - 1);
        break;
      case "ArrowRight": case "]":
        if (state.currentIndex < state.images.length - 1) loadImageByOriginalIndex(state.currentIndex + 1);
        break;
      case "f": case "F":
        fitToViewport(); render(); break;
      case "+": case "=":
        changeZoom(0.15); break;
      case "-":
        changeZoom(-0.15); break;
      case "Escape":
        state.selectedBoxIdx = -1;
        state.isDrawing = false;
        state.drawRect = null;
        setTool("select");
        updatePropertiesPanel();
        updateBoxesList();
        render();
        break;
    }
  });

  // ─── Wire Up Event Listeners ─────────────────────────────────────
  function initEventListeners() {
    // Canvas pointer events
    canvas.addEventListener("mousedown", onPointerDown);
    canvas.addEventListener("mousemove", onPointerMove);
    canvas.addEventListener("mouseup", onPointerUp);
    canvas.addEventListener("mouseleave", onPointerUp);
    canvas.addEventListener("touchstart", onPointerDown, { passive: false });
    canvas.addEventListener("touchmove", onPointerMove, { passive: false });
    canvas.addEventListener("touchend", onPointerUp);

    // Zoom scroll
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.1 : -0.1;
      changeZoom(delta);
      render();
    }, { passive: false });

    // Tool buttons
    $("tool-select")?.addEventListener("click", () => setTool("select"));
    $("tool-draw")?.addEventListener("click", () => setTool("draw"));
    $("tool-delete")?.addEventListener("click", () => deleteSelectedBox());

    // Zoom buttons
    $("canvas-zoom-in")?.addEventListener("click", () => { changeZoom(0.2); render(); });
    $("canvas-zoom-out")?.addEventListener("click", () => { changeZoom(-0.2); render(); });
    $("canvas-zoom-fit")?.addEventListener("click", () => { fitToViewport(); render(); });

    // Navigation
    $("canvas-prev-btn")?.addEventListener("click", () => {
      if (state.currentIndex > 0) loadImageByOriginalIndex(state.currentIndex - 1);
    });
    $("canvas-next-btn")?.addEventListener("click", () => {
      if (state.currentIndex < state.images.length - 1) loadImageByOriginalIndex(state.currentIndex + 1);
    });

    // Upload button
    const uploadBtn = $("editor-upload-btn");
    const fileInput = $("editor-file-input");
    uploadBtn?.addEventListener("click", () => fileInput?.click());
    fileInput?.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      if (files.length > 0) uploadAndCreateJob(files);
      fileInput.value = "";
    });

    // Sample dataset buttons
    $("editor-load-sample-btn")?.addEventListener("click", () => loadSampleDataset());
    $("stage-load-sample-btn")?.addEventListener("click", () => loadSampleDataset());
    $("stage-upload-btn")?.addEventListener("click", () => fileInput?.click());

    // Save / Export
    $("editor-save-btn")?.addEventListener("click", () => saveCurrentImage(false));
    $("editor-export-btn")?.addEventListener("click", () => exportJob());

    // Reviewed toggle
    $("editor-reviewed-toggle")?.addEventListener("change", (e) => {
      saveCurrentImage(e.target.checked);
    });

    // Properties panel - class selection
    document.querySelectorAll(".class-card-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        changeSelectedBoxClass(btn.dataset.class);
      });
    });

    // Properties panel - delete / duplicate
    $("prop-del-box-btn")?.addEventListener("click", () => deleteSelectedBox());
    $("prop-dup-box-btn")?.addEventListener("click", () => duplicateSelectedBox());
    $("prop-start-draw-btn")?.addEventListener("click", () => setTool("draw"));

    // Filter tabs
    document.querySelectorAll(".filter-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        state.filter = btn.dataset.filter || "all";
        renderImageList();
      });
    });

    // Search
    $("editor-search-input")?.addEventListener("input", (e) => {
      state.searchQuery = e.target.value.trim();
      renderImageList();
    });

    // Drag-and-drop file onto editor area
    const editorShell = document.querySelector(".editor-shell");
    if (editorShell) {
      editorShell.addEventListener("dragover", (e) => e.preventDefault());
      editorShell.addEventListener("drop", (e) => {
        e.preventDefault();
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) uploadAndCreateJob(files);
      });
    }

    // Dataset tab review button
    hookDatasetTabReviewButton();
  }

  // ─── Initial Setup ───────────────────────────────────────────────
  function init() {
    initEventListeners();

    // Show "no selection" state initially
    const propCard = $("prop-box-card");
    const noSel = $("prop-no-selection");
    if (propCard) propCard.style.display = "none";
    if (noSel) noSel.classList.remove("hidden");

    // Initialise unsaved badge hidden
    $("editor-unsaved-badge")?.classList.add("hidden");

    updateHeader();
    updateNavControls();

    // Show empty state on canvas
    if (emptyState) emptyState.style.display = "flex";

    console.log("[Annotation Canvas] Editor engine initialised.");
  }

  // Run after DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();

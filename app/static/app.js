/* ──────────────────────────────────────────────────────────────────
   Annotation Wizard — Application Logic
   ────────────────────────────────────────────────────────────────── */

// ─── 1. Element References ───
const elements = {
  apiKey: document.querySelector("#api-key"),
  connect: document.querySelector("#connect-button"),
  connectionState: document.querySelector("#connection-state"),
  clientName: document.querySelector("#client-name"),
  healthDot: document.querySelector("#health-dot"),
  healthState: document.querySelector("#health-state"),
  today: document.querySelector("#today"),
  // Single-image assessment
  dropZone: document.querySelector("#drop-zone"),
  fileInput: document.querySelector("#file-input"),
  fileName: document.querySelector("#file-name"),
  previewImage: document.querySelector("#preview-image"),
  canvas: document.querySelector("#annotation-canvas"),
  analyze: document.querySelector("#analyze-button"),
  clear: document.querySelector("#clear-button"),
  saveReport: document.querySelector("#save-report"),
  formMessage: document.querySelector("#form-message"),
  reportState: document.querySelector("#report-state"),
  total: document.querySelector("#total-detections"),
  summary: document.querySelector("#report-summary"),
  damageTypes: document.querySelector("#damage-types"),
  // Activity log
  activityList: document.querySelector("#activity-list"),
  sessionCount: document.querySelector("#session-count"),
  clearActivity: document.querySelector("#clear-activity-button"),
  // Dataset labeling
  zipDropZone: document.querySelector("#zip-drop-zone"),
  zipDropInner: document.querySelector("#zip-drop-inner"),
  zipFileInput: document.querySelector("#zip-file-input"),
  zipFileLabel: document.querySelector("#zip-file-label"),
  zipClear: document.querySelector("#zip-clear-button"),
  zipLabel: document.querySelector("#zip-label-button"),
  zipReview: document.querySelector("#zip-review-button"),
  openSampleCanvas: document.querySelector("#open-sample-canvas-btn"),
  zipDownload: document.querySelector("#zip-download-button"),
  zipProgressArea: document.querySelector("#zip-progress-area"),
  zipProgressFill: document.querySelector("#zip-progress-fill"),
  zipProgressText: document.querySelector("#zip-progress-text"),
  zipFormMessage: document.querySelector("#zip-form-message"),
  // Image register
  registerList: document.querySelector("#register-list"),
  registerCount: document.querySelector("#register-count"),
  registerEmpty: document.querySelector("#register-empty"),
};

// ─── 2. Constants & State ───
const colors = ["#ef4444", "#f59e0b", "#3b82f6", "#14b8a6"];
const classColors = { D00: colors[0], D10: colors[1], D20: colors[2], D40: colors[3] };

const STORAGE_KEYS = {
  apiKey: "aw-api-key",
  activity: "aw-activity-log",
  register: "aw-image-register",
};

let selectedFile = null;
let previewUrl = null;
let selectedZipFile = null;

// ─── 3. Initialization ───
elements.apiKey.value = sessionStorage.getItem(STORAGE_KEYS.apiKey) || "";
elements.today.textContent = new Intl.DateTimeFormat(undefined, {
  month: "short", day: "numeric", year: "numeric",
}).format(new Date());

// ─── 4. Tab Navigation ───
const navItems = document.querySelectorAll(".nav-item[data-tab]");

function switchTab(tabId) {
  navItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-content").forEach((el) => {
    el.classList.toggle("active", el.id === `tab-${tabId}`);
  });
}

navItems.forEach((item) => {
  item.addEventListener("click", (e) => {
    e.preventDefault();
    switchTab(item.dataset.tab);
  });
});

// ─── 5. Utility Helpers ───
function setMessage(el, message = "", type = "") {
  el.textContent = message;
  el.classList.remove("error", "success");
  if (type) el.classList.add(type);
}

function getColor(className, classId = 0) {
  return classColors[className] || colors[classId % colors.length];
}

function formatTime(date) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

function formatDateTime(dateStr) {
  const d = new Date(dateStr);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(d);
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── 6. Canvas Drawing ───
function resetCanvas() {
  const context = elements.canvas.getContext("2d");
  context.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
}

function drawDetections(detections = [], imageWidth, imageHeight) {
  const image = elements.previewImage;
  const naturalWidth = image.naturalWidth || imageWidth;
  const naturalHeight = image.naturalHeight || imageHeight;
  if (!naturalWidth || !naturalHeight) return;

  const canvas = elements.canvas;
  canvas.width = naturalWidth;
  canvas.height = naturalHeight;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  const scaleX = naturalWidth / (imageWidth || naturalWidth);
  const scaleY = naturalHeight / (imageHeight || naturalHeight);
  const lineWidth = Math.max(2, Math.round(naturalWidth / 350));
  const fontSize = Math.max(13, Math.round(naturalWidth / 42));

  detections.forEach((detection, index) => {
    const [x1, y1, x2, y2] = detection.bbox || [];
    if (![x1, y1, x2, y2].every(Number.isFinite)) return;
    const x = x1 * scaleX;
    const y = y1 * scaleY;
    const width = Math.max(1, (x2 - x1) * scaleX);
    const height = Math.max(1, (y2 - y1) * scaleY);
    const color = getColor(detection.class_name, detection.class_id || index);
    const label = `${detection.class_name} ${Math.round((detection.confidence || 0) * 100)}%`;

    context.lineWidth = lineWidth;
    context.strokeStyle = color;
    context.strokeRect(x, y, width, height);
    context.font = `700 ${fontSize}px Inter, system-ui, sans-serif`;
    const labelWidth = context.measureText(label).width + fontSize;
    const labelY = Math.max(0, y - fontSize * 1.45);
    context.fillStyle = color;
    context.fillRect(x, labelY, labelWidth, fontSize * 1.45);
    context.fillStyle = "#ffffff";
    context.fillText(label, x + fontSize / 2, labelY + fontSize * 1.06);
  });
}

// ─── 7. Report Rendering ───
function renderRows(damageTypes) {
  elements.damageTypes.replaceChildren();
  if (!damageTypes.length) {
    const empty = document.createElement("p");
    empty.className = "empty-row";
    empty.textContent = "No damage classes detected.";
    elements.damageTypes.append(empty);
    return;
  }

  damageTypes.forEach((type) => {
    const row = document.createElement("div");
    row.className = "damage-row";
    const className = document.createElement("span");
    className.className = "damage-class";
    const swatch = document.createElement("i");
    swatch.style.background = getColor(type.class_name, type.class_id);
    className.append(swatch, document.createTextNode(type.class_name));
    const count = document.createElement("span");
    count.textContent = type.count;
    const confidence = document.createElement("span");
    confidence.textContent = `${Math.round(type.highest_confidence * 100)}%`;
    row.append(className, count, confidence);
    elements.damageTypes.append(row);
  });
}

function renderReport(report) {
  const isDamage = report.status === "damage_detected";
  elements.reportState.textContent = isDamage ? "Damage found" : "Clear result";
  elements.reportState.dataset.status = report.status;
  elements.total.textContent = report.total_detections;
  elements.summary.textContent = report.summary;
  renderRows(report.damage_types || []);
}

// ─── 8. Activity Log (localStorage-persisted) ───
function loadActivity() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.activity) || "[]");
  } catch { return []; }
}

function saveActivity(entries) {
  localStorage.setItem(STORAGE_KEYS.activity, JSON.stringify(entries));
}

function renderActivityList() {
  const entries = loadActivity();
  elements.activityList.replaceChildren();
  elements.sessionCount.textContent = `${entries.length} ${entries.length === 1 ? "entry" : "entries"}`;

  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "empty-activity";
    empty.textContent = "No activity recorded yet.";
    elements.activityList.append(empty);
    return;
  }

  entries.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "activity-row";

    const typeBadge = document.createElement("span");
    typeBadge.className = `activity-type type-${entry.type || "analyze"}`;
    const typeLabels = { analyze: "Analyze", dataset: "Dataset", register: "Register" };
    typeBadge.textContent = typeLabels[entry.type] || "Analyze";

    const name = document.createElement("span");
    name.className = "activity-file";
    name.textContent = entry.fileName;

    const time = document.createElement("span");
    time.className = "activity-time";
    time.textContent = formatDateTime(entry.timestamp);

    const result = document.createElement("span");
    result.className = `activity-result ${entry.resultClass || ""}`;
    result.textContent = entry.resultText || "";

    row.append(typeBadge, name, time, result);
    elements.activityList.append(row);
  });
}

function addActivity(type, fileName, resultText, resultClass) {
  const entries = loadActivity();
  entries.unshift({
    type,
    fileName,
    resultText,
    resultClass,
    timestamp: new Date().toISOString(),
  });
  // Keep last 200 entries
  if (entries.length > 200) entries.length = 200;
  saveActivity(entries);
  renderActivityList();
}

function clearActivity() {
  localStorage.removeItem(STORAGE_KEYS.activity);
  renderActivityList();
}

// ─── 9. Image Register (localStorage-persisted) ───
function loadRegister() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.register) || "[]");
  } catch { return []; }
}

function saveRegister(entries) {
  localStorage.setItem(STORAGE_KEYS.register, JSON.stringify(entries));
}

function renderRegisterList() {
  const entries = loadRegister();
  elements.registerList.replaceChildren();
  elements.registerCount.textContent = `${entries.length} ${entries.length === 1 ? "image" : "images"}`;

  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "empty-activity";
    empty.id = "register-empty";
    empty.textContent = "No images have been saved to the register yet.";
    elements.registerList.append(empty);
    return;
  }

  entries.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "register-row";

    const id = document.createElement("span");
    id.className = "register-id";
    id.textContent = `#${entry.imageId}`;

    const name = document.createElement("span");
    name.className = "register-filename";
    name.textContent = entry.originalName || entry.filename;
    name.title = `Server filename: ${entry.filename}`;

    const time = document.createElement("span");
    time.className = "register-time";
    time.textContent = formatDateTime(entry.savedAt);

    const result = document.createElement("span");
    const isDamage = entry.status === "damage_detected";
    result.className = `register-result ${isDamage ? "damage" : "clear"}`;
    result.textContent = isDamage ? `${entry.totalDetections} found` : "No damage";

    const action = document.createElement("span");
    action.className = "register-action";
    const viewBtn = document.createElement("button");
    viewBtn.textContent = "View";
    viewBtn.addEventListener("click", () => {
      // Switch to single-image tab and show the file info
      switchTab("assessment");
      elements.reportState.textContent = isDamage ? "Damage found" : "Clear result";
      elements.reportState.dataset.status = entry.status;
      elements.total.textContent = entry.totalDetections;
      elements.summary.textContent = entry.summary || (isDamage ? "Damage detected in this image." : "No damage detected.");
      if (entry.damageTypes) renderRows(entry.damageTypes);
    });
    action.append(viewBtn);

    row.append(id, name, time, result, action);
    elements.registerList.append(row);
  });
}

function addToRegister(data, originalFileName) {
  const entries = loadRegister();
  const prediction = data.prediction || data;
  const report = data.report || prediction.report;

  entries.unshift({
    imageId: data.image_id,
    filename: data.filename,
    originalName: originalFileName,
    savedAt: data.created_at || new Date().toISOString(),
    status: report.status,
    totalDetections: report.total_detections,
    summary: report.summary,
    damageTypes: report.damage_types || [],
  });

  if (entries.length > 500) entries.length = 500;
  saveRegister(entries);
  renderRegisterList();
}

// ─── 10. File Selection (Single Image) ───
function selectFile(file) {
  if (!file) return;
  const allowed = ["image/jpeg", "image/png", "image/webp"];
  if (!allowed.includes(file.type)) {
    setMessage(elements.formMessage, "Use a JPEG, PNG, or WebP image.", "error");
    return;
  }
  if (file.size > 1024 * 1024) {
    setMessage(elements.formMessage, "This image exceeds the 1 MB upload limit.", "error");
    return;
  }

  selectedFile = file;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  elements.previewImage.src = previewUrl;
  elements.previewImage.alt = `Selected road image: ${file.name}`;
  elements.fileName.textContent = file.name;
  elements.dropZone.classList.add("has-upload");
  elements.analyze.disabled = false;
  resetCanvas();
  setMessage(elements.formMessage);
  elements.previewImage.onload = resetCanvas;
}

function resetAssessment() {
  selectedFile = null;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  elements.fileInput.value = "";
  elements.previewImage.src = "/reference-image";
  elements.previewImage.alt = "Reference road damage examples";
  elements.fileName.textContent = "Reference image";
  elements.dropZone.classList.remove("has-upload");
  elements.analyze.disabled = true;
  elements.reportState.textContent = "Awaiting image";
  elements.reportState.dataset.status = "idle";
  elements.total.textContent = "0";
  elements.summary.textContent = "Choose an image to start a new road condition assessment.";
  elements.damageTypes.replaceChildren();
  const empty = document.createElement("p");
  empty.className = "empty-row";
  empty.textContent = "Results will appear here.";
  elements.damageTypes.append(empty);
  resetCanvas();
  setMessage(elements.formMessage);
}

// ─── 11. API Helpers ───
async function readError(response) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : "The server could not process this request.";
  } catch {
    return "The server could not process this request.";
  }
}

// ─── 12. Connect ───
async function connect() {
  const key = elements.apiKey.value.trim();
  if (!key) {
    elements.connectionState.textContent = "Enter an API key to connect.";
    elements.connectionState.dataset.state = "error";
    return;
  }

  elements.connect.disabled = true;
  elements.connect.textContent = "Checking…";
  try {
    const response = await fetch("/auth/me", {
      headers: { "X-API-Key": key },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(await readError(response));
    const client = await response.json();
    sessionStorage.setItem(STORAGE_KEYS.apiKey, key);
    elements.connectionState.textContent = `Connected as ${client.name}`;
    elements.connectionState.dataset.state = "connected";
    elements.clientName.textContent = client.name;

    const guideWelcome = document.querySelector("#guide-welcome-msg");
    if (guideWelcome) {
      guideWelcome.textContent = `Welcome back, ${client.name}!`;
    }
    const guideBadge = document.querySelector("#guide-client-badge");
    if (guideBadge) {
      guideBadge.textContent = client.name;
    }
    hideAuthErrorBanner();
  } catch (error) {
    sessionStorage.removeItem(STORAGE_KEYS.apiKey);
    elements.connectionState.textContent = error.message || "Connection unavailable.";
    elements.connectionState.dataset.state = "error";
    elements.clientName.textContent = "Local session";
  } finally {
    elements.connect.disabled = false;
    elements.connect.textContent = "Connect";
  }
}


// ─── 13. Analyze (Single Image) ───
async function analyze() {
  if (!selectedFile) return;
  const apiKey = elements.apiKey.value.trim();
  if (!apiKey) {
    setMessage(elements.formMessage, "Connect an API key before analyzing an image.", "error");
    return;
  }

  elements.analyze.disabled = true;
  elements.analyze.textContent = "Analyzing…";
  elements.reportState.textContent = "Processing";
  elements.reportState.dataset.status = "idle";
  setMessage(elements.formMessage, "Running road-damage detection…");
  const formData = new FormData();
  formData.append("file", selectedFile);

  const saveToRegister = elements.saveReport.checked;

  try {
    const endpoint = saveToRegister ? "/images" : "/predict";
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "X-API-Key": apiKey },
      body: formData,
    });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    const prediction = data.prediction || data;
    const report = data.report || prediction.report;
    renderReport(report);
    drawDetections(prediction.detections, prediction.image_width, prediction.image_height);

    // Activity log entry
    const isDamage = report.status === "damage_detected";
    const resultText = isDamage ? `${report.total_detections} found` : "No damage";
    const resultClass = isDamage ? "damage" : "clear";
    addActivity("analyze", selectedFile.name, resultText, resultClass);

    if (saveToRegister) {
      addToRegister(data, selectedFile.name);
      setMessage(elements.formMessage, "Assessment saved to the image register.", "success");
    } else {
      setMessage(elements.formMessage, "Assessment complete.", "success");
    }
  } catch (error) {
    elements.reportState.textContent = "Request failed";
    elements.reportState.dataset.status = "error";
    setMessage(elements.formMessage, error.message, "error");
  } finally {
    elements.analyze.disabled = false;
    elements.analyze.textContent = "Analyze image";
  }
}

// ─── 14. Dataset Labeling (ZIP) ───
function selectZipFile(file) {
  if (!file) return;
  const name = file.name || "";
  if (!name.toLowerCase().endsWith(".zip")) {
    setMessage(elements.zipFormMessage, "Please select a .zip file.", "error");
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    setMessage(elements.zipFormMessage, "ZIP exceeds the 50 MB limit.", "error");
    return;
  }

  selectedZipFile = file;
  elements.zipFileLabel.textContent = `${file.name} (${formatFileSize(file.size)})`;
  elements.zipDropZone.classList.add("has-file");
  elements.zipLabel.disabled = false;
  if (elements.zipReview) elements.zipReview.disabled = false;
  setMessage(elements.zipFormMessage);
}

function resetZipUpload() {
  selectedZipFile = null;
  elements.zipFileInput.value = "";
  elements.zipFileLabel.textContent = "Drop a ZIP archive here or click to browse";
  elements.zipDropZone.classList.remove("has-file");
  elements.zipLabel.disabled = true;
  if (elements.zipReview) elements.zipReview.disabled = true;
  elements.zipLabel.style.display = "block";
  elements.zipDownload.style.display = "none";
  if (window.currentZipUrl) {
    URL.revokeObjectURL(window.currentZipUrl);
    window.currentZipUrl = null;
  }
  elements.zipProgressArea.classList.add("hidden");
  elements.zipProgressFill.style.width = "0%";
  elements.zipProgressFill.classList.remove("indeterminate");
  setMessage(elements.zipFormMessage);
}

async function labelDataset() {
  if (!selectedZipFile) return;
  const apiKey = elements.apiKey.value.trim();
  if (!apiKey) {
    setMessage(elements.zipFormMessage, "Connect an API key before labeling.", "error");
    return;
  }

  elements.zipLabel.disabled = true;
  elements.zipClear.disabled = true;
  elements.zipProgressArea.classList.remove("hidden");
  elements.zipProgressFill.style.width = "0%";
  elements.zipProgressText.textContent = "Uploading ZIP archive…";
  setMessage(elements.zipFormMessage);

  const formData = new FormData();
  formData.append("file", selectedZipFile);
  const fileName = selectedZipFile.name;

  try {
    // Use XMLHttpRequest for upload progress tracking
    const result = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/datasets/label");
      xhr.setRequestHeader("X-API-Key", apiKey);
      xhr.responseType = "blob";

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 50);
          elements.zipProgressFill.style.width = `${pct}%`;
          elements.zipProgressText.textContent = `Uploading… ${Math.round((e.loaded / e.total) * 100)}%`;
        }
      });

      xhr.upload.addEventListener("loadend", () => {
        // Upload complete, now server is processing
        elements.zipProgressFill.style.width = "50%";
        elements.zipProgressFill.classList.add("indeterminate");
        elements.zipProgressText.textContent = "Processing images — this may take a while…";
      });

      xhr.addEventListener("load", () => {
        elements.zipProgressFill.classList.remove("indeterminate");
        if (xhr.status >= 200 && xhr.status < 300) {
          elements.zipProgressFill.style.width = "100%";
          elements.zipProgressText.textContent = "Complete! Preparing download…";
          resolve(xhr.response);
        } else {
          // Try to read error from blob
          const reader = new FileReader();
          reader.onload = () => {
            try {
              const body = JSON.parse(reader.result);
              reject(new Error(body.detail || "Dataset labeling failed."));
            } catch {
              reject(new Error(`Server returned status ${xhr.status}.`));
            }
          };
          reader.onerror = () => reject(new Error("Failed to read error response."));
          reader.readAsText(xhr.response);
        }
      });

      xhr.addEventListener("error", () => reject(new Error("Network error during upload.")));
      xhr.addEventListener("timeout", () => reject(new Error("Request timed out.")));
      xhr.timeout = 600000; // 10 minutes

      xhr.send(formData);
    });

    // Show download button instead of auto-downloading
    const blob = new Blob([result], { type: "application/zip" });
    window.currentZipUrl = URL.createObjectURL(blob);
    elements.zipDownload.setAttribute("href", window.currentZipUrl);
    elements.zipDownload.setAttribute("download", "annotation-wizard-labeled.zip");
    elements.zipDownload.style.display = "block";
    elements.zipLabel.style.display = "none";

    setMessage(elements.zipFormMessage, "Labeled dataset ready for download!", "success");
    addActivity("dataset", fileName, "Labeled", "success");

  } catch (error) {
    elements.zipProgressFill.classList.remove("indeterminate");
    elements.zipProgressFill.style.width = "0%";
    elements.zipProgressArea.classList.add("hidden");
    setMessage(elements.zipFormMessage, error.message, "error");
    addActivity("dataset", fileName, "Failed", "damage");
  } finally {
    elements.zipLabel.disabled = false;
    elements.zipClear.disabled = false;
  }
}

// ─── 15. Health Polling ───
async function checkHealth() {
  try {
    const response = await fetch("/health");
    const health = await response.json();
    const ready = response.ok && health.model === "ready";
    elements.healthDot.className = `status-dot ${ready ? "ready" : "degraded"}`;
    elements.healthState.textContent = ready ? "Service ready" : "Service degraded";
  } catch {
    elements.healthDot.className = "status-dot degraded";
    elements.healthState.textContent = "Service unavailable";
  }
}

// ─── 16. Event Listeners ───

// Single-image drag & drop
elements.fileInput.addEventListener("change", (e) => selectFile(e.target.files[0]));
elements.dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  elements.dropZone.classList.add("dragging");
});
elements.dropZone.addEventListener("dragleave", () => elements.dropZone.classList.remove("dragging"));
elements.dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  elements.dropZone.classList.remove("dragging");
  selectFile(e.dataTransfer.files[0]);
});
elements.connect.addEventListener("click", connect);
elements.clear.addEventListener("click", resetAssessment);
elements.analyze.addEventListener("click", analyze);
elements.previewImage.addEventListener("load", resetCanvas);

// ZIP drag & drop
elements.zipDropZone.addEventListener("click", () => elements.zipFileInput.click());
elements.zipFileInput.addEventListener("change", (e) => selectZipFile(e.target.files[0]));
elements.zipDropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  elements.zipDropZone.classList.add("dragging");
});
elements.zipDropZone.addEventListener("dragleave", () => elements.zipDropZone.classList.remove("dragging"));
elements.zipDropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  elements.zipDropZone.classList.remove("dragging");
  selectZipFile(e.dataTransfer.files[0]);
});
elements.zipClear.addEventListener("click", resetZipUpload);
elements.zipLabel.addEventListener("click", labelDataset);

// Activity log
elements.clearActivity.addEventListener("click", clearActivity);

// Disconnect button
const disconnectBtn = document.querySelector("#disconnect-button");
if (disconnectBtn) {
  disconnectBtn.addEventListener("click", () => {
    sessionStorage.removeItem(STORAGE_KEYS.apiKey);
    window.location.href = "/";
  });
}

// Retry verification button
const authRetryBtn = document.querySelector("#auth-retry-btn");
if (authRetryBtn) {
  authRetryBtn.addEventListener("click", () => {
    initWorkspaceSession();
  });
}

// Dismiss guide button
const dismissGuideBtn = document.querySelector("#dismiss-guide-btn");
if (dismissGuideBtn) {
  dismissGuideBtn.addEventListener("click", () => {
    const guide = document.querySelector("#workspace-guide");
    if (guide) guide.style.display = "none";
  });
}

// ─── 17. Workspace Session & Auth Handling ───
function showAuthErrorBanner(msg) {
  const banner = document.querySelector("#auth-error-banner");
  const text = document.querySelector("#auth-error-text");
  if (banner && text) {
    text.textContent = msg;
    banner.classList.remove("hidden");
  }
}

function hideAuthErrorBanner() {
  const banner = document.querySelector("#auth-error-banner");
  if (banner) banner.classList.add("hidden");
}

async function initWorkspaceSession() {
  const storedKey = sessionStorage.getItem(STORAGE_KEYS.apiKey);
  if (!storedKey) {
    // If someone opens /workspace without a stored key, redirect them to /
    window.location.replace("/");
    return;
  }

  elements.apiKey.value = storedKey;
  elements.connect.disabled = true;
  elements.connect.textContent = "Checking…";
  elements.connectionState.textContent = "Verifying session…";
  elements.connectionState.dataset.state = "idle";
  hideAuthErrorBanner();

  try {
    const response = await fetch("/auth/me", {
      method: "GET",
      headers: { "X-API-Key": storedKey },
      cache: "no-store",
    });

    if (response.status === 401 || response.status === 403) {
      // Key invalid or revoked: remove stored key and redirect to landing page
      sessionStorage.removeItem(STORAGE_KEYS.apiKey);
      window.location.replace("/?error=auth_failed");
      return;
    }

    if (!response.ok) {
      const errDetail = await readError(response);
      showAuthErrorBanner(`Temporary service error: ${errDetail}. Please retry.`);
      elements.connectionState.textContent = "Service temporarily unavailable.";
      elements.connectionState.dataset.state = "error";
      return;
    }

    const client = await response.json();
    elements.connectionState.textContent = `Connected as ${client.name}`;
    elements.connectionState.dataset.state = "connected";
    elements.clientName.textContent = client.name;

    const guideWelcome = document.querySelector("#guide-welcome-msg");
    if (guideWelcome) {
      guideWelcome.textContent = `Welcome back, ${client.name}!`;
    }
    const guideBadge = document.querySelector("#guide-client-badge");
    if (guideBadge) {
      guideBadge.textContent = client.name;
    }
  } catch (error) {
    // Service or network error: do not display false auth success
    showAuthErrorBanner("Temporary service error: Unable to verify API key session with server.");
    elements.connectionState.textContent = "Service unavailable.";
    elements.connectionState.dataset.state = "error";
  } finally {
    elements.connect.disabled = false;
    elements.connect.textContent = "Connect";
  }
}

// ─── 18. Boot ───
checkHealth();
setInterval(checkHealth, 30000);
renderActivityList();
renderRegisterList();
initWorkspaceSession();


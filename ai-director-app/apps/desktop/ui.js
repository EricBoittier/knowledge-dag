const storageKey = "ai-director-project";
const state = { nodes: [], edges: [] };
const positions = new Map();
let selectedNodeId = "";
let draggingNodeId = "";
let connectMode = false;
let connectSourceNodeId = "";
/** Last node in shift-click chain (sequential edges: A→B→C). */
let shiftChainLastId = "";

const nodeTitle = document.getElementById("nodeTitle");
const nodeList = document.getElementById("nodeList");
const edgeFrom = document.getElementById("edgeFrom");
const edgeTo = document.getElementById("edgeTo");
const edgeList = document.getElementById("edgeList");
const graphSvg = document.getElementById("graphSvg");
const metaNodeId = document.getElementById("metaNodeId");
const metaImportance = document.getElementById("metaImportance");
const metaTags = document.getElementById("metaTags");
const metaDuration = document.getElementById("metaDuration");
const finderSummary = document.getElementById("finderSummary");
const finderList = document.getElementById("finderList");
const finderMaxSizeMbInput = document.getElementById("finderMaxSizeMb");
const finderClearSizeFilterBtn = document.getElementById("finderClearSizeFilterBtn");
const finderProgressLog = document.getElementById("finderProgressLog");
const wikiInput = document.getElementById("wikiInput");
const clipSelect = document.getElementById("clipSelect");
const clipPreview = document.getElementById("clipPreview");
const clipIn = document.getElementById("clipIn");
const clipOut = document.getElementById("clipOut");
const cropX = document.getElementById("cropX");
const cropY = document.getElementById("cropY");
const cropW = document.getElementById("cropW");
const cropH = document.getElementById("cropH");
const scriptInput = document.getElementById("scriptInput");
const voiceoverEngineSelect = document.getElementById("voiceoverEngineSelect");
const VOICEOVER_ENGINE_KEY = "ai-director-voiceover-engine";
const topicInput = document.getElementById("topicInput");
const targetDurationInput = document.getElementById("targetDurationInput");
const connectModeBtn = document.getElementById("connectModeBtn");
const stageList = document.getElementById("stageList");
const projectHealth = document.getElementById("projectHealth");
const exportValidationSummary = document.getElementById("exportValidationSummary");
const exportValidationList = document.getElementById("exportValidationList");
let mediaEntries = [];
let finderSamplesCache = [];
let finderSummaryBase = "No run yet.";
let activeVariantId = "default";

const variantSelect = document.getElementById("variantSelect");
const variantReloadBtn = document.getElementById("variantReloadBtn");
const newVariantIdInput = document.getElementById("newVariantId");
const newVariantLabelInput = document.getElementById("newVariantLabel");
const duplicateFromVariant = document.getElementById("duplicateFromVariant");
const createVariantBtn = document.getElementById("createVariantBtn");
const syncMediaFromRootBtn = document.getElementById("syncMediaFromRootBtn");
const timelineMetaSummary = document.getElementById("timelineMetaSummary");
const mediaLibSegmentFilter = document.getElementById("mediaLibSegmentFilter");
const mediaLibraryGrid = document.getElementById("mediaLibraryGrid");
const mediaLibStartSec = document.getElementById("mediaLibStartSec");
const timelineStudioJson = document.getElementById("timelineStudioJson");
const loadTimelineStudioBtn = document.getElementById("loadTimelineStudioBtn");
const saveTimelineStudioBtn = document.getElementById("saveTimelineStudioBtn");
const loadTimelineIndexBtn = document.getElementById("loadTimelineIndexBtn");
const timelineIndexTbody = document.getElementById("timelineIndexTbody");
const timelineIndexEmpty = document.getElementById("timelineIndexEmpty");
const flowStages = ["source", "planner", "discovery", "select", "normalize", "annotations", "subtitles", "export", "validate"];
let activeStage = "source";

document.getElementById("addNodeBtn").addEventListener("click", () => {
  const title = nodeTitle.value.trim();
  if (!title) return;
  const id = "n" + String(Date.now());
  state.nodes.push({ id, title, importance: 0.5, tags: [], duration_intent_sec: 10 });
  ensureNodePosition(id);
  nodeTitle.value = "";
  render();
});

document.getElementById("addEdgeBtn").addEventListener("click", () => {
  const from = edgeFrom.value;
  const to = edgeTo.value;
  if (!from || !to || from === to) return;
  if (wouldCreateCycle(from, to)) {
    finderSummary.textContent = "Edge rejected: would create a cycle.";
    return;
  }
  if (!state.edges.some(e => e.from === from && e.to === to)) {
    state.edges.push({ from, to });
  }
  render();
});

document.getElementById("removeEdgeBtn").addEventListener("click", () => {
  const from = edgeFrom.value;
  const to = edgeTo.value;
  if (!from || !to || from === to) return;
  const before = state.edges.length;
  state.edges = state.edges.filter(e => !(e.from === from && e.to === to));
  finderSummary.textContent =
    state.edges.length < before
      ? `Removed edge ${label(from)} -> ${label(to)}`
      : `No edge found for ${label(from)} -> ${label(to)}`;
  render();
});

connectModeBtn.addEventListener("click", () => {
  connectMode = !connectMode;
  connectSourceNodeId = "";
  shiftChainLastId = "";
  connectModeBtn.textContent = `Click-Connect: ${connectMode ? "ON" : "OFF"}`;
  finderSummary.textContent = connectMode
    ? "Click-connect enabled. Click source node, then target node."
    : "Click-connect disabled.";
  drawGraph();
});

document.getElementById("applyMetaBtn").addEventListener("click", () => {
  const id = selectedNodeId || metaNodeId.value;
  const node = state.nodes.find(n => n.id === id);
  if (!node) return;
  node.importance = Number(metaImportance.value || 0.5);
  node.tags = (metaTags.value || "").split(",").map(s => s.trim()).filter(Boolean);
  node.duration_intent_sec = Number(metaDuration.value || 10);
  render();
});

function removeNodeById(id) {
  const node = state.nodes.find(n => n.id === id);
  if (!node) return;
  const titleLabel = node.title || id;
  state.nodes = state.nodes.filter(n => n.id !== id);
  state.edges = state.edges.filter(e => e.from !== id && e.to !== id);
  positions.delete(id);
  if (selectedNodeId === id) selectedNodeId = "";
  if (connectSourceNodeId === id) connectSourceNodeId = "";
  if (shiftChainLastId === id) shiftChainLastId = "";
  finderSummary.textContent = `Removed node ${titleLabel}`;
  render();
}

document.getElementById("removeNodeBtn").addEventListener("click", () => {
  if (!selectedNodeId) return;
  removeNodeById(selectedNodeId);
});

document.getElementById("saveBtn").addEventListener("click", () => {
  localStorage.setItem(storageKey, JSON.stringify(state, null, 2));
  fetch("/api/project", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(state),
  })
    .then(r => r.json())
    .then(() => alert("Saved to local storage + project file"))
    .catch(() => alert("Saved locally; failed to save project file"));
});

document.getElementById("resetProjectBtn").addEventListener("click", async () => {
  const ok = window.confirm("This will clear generated files/output and reset the DAG to starter defaults. Continue?");
  if (!ok) return;
  finderSummary.textContent = "Resetting project...";
  finderList.innerHTML = "";
  try {
    const res = await fetch("/api/reset-project", { method: "POST" });
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Project reset failed";
      finderList.innerHTML = `<li>${escapeHtml(payload.error || payload.detail || "Unknown error")}</li>`;
      return;
    }
    localStorage.removeItem(storageKey);
    state.nodes = payload.project.nodes || [];
    state.edges = payload.project.edges || [];
    selectedNodeId = "";
    positions.clear();
    for (const n of state.nodes) ensureNodePosition(n.id);
    mediaEntries = [];
    clipSelect.innerHTML = "";
    clipPreview.removeAttribute("src");
    clipPreview.load();
    scriptInput.value = "";
    exportValidationSummary.textContent = "No crop validation yet.";
    exportValidationList.innerHTML = "";
    render();
    setActiveStage("source");
    refreshProjectHealth();
    finderSummary.textContent = "Project reset complete. Ready to start again.";
  } catch (err) {
    finderSummary.textContent = "Project reset request failed";
  }
});

const finderLogLines = [];
const finderLogMax = 200;
function appendFinderProgressLine(text) {
  finderLogLines.push(text);
  if (finderLogLines.length > finderLogMax) finderLogLines.splice(0, finderLogLines.length - finderLogMax);
  if (finderProgressLog) {
    finderProgressLog.textContent = finderLogLines.join("\n");
    finderProgressLog.scrollTop = finderProgressLog.scrollHeight;
  }
}

function formatDurationSec(totalSec) {
  const sec = Math.max(0, Math.round(Number(totalSec) || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (!Number.isFinite(n) || n <= 0) return "Unknown size";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = n;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  const precision = idx >= 2 ? 1 : 0;
  return `${value.toFixed(precision)} ${units[idx]}`;
}

function renderFinderSamples(samples) {
  finderList.innerHTML = "";
  const list = Array.isArray(samples) ? samples : [];
  if (list.length === 0) {
    finderList.innerHTML = "<li>No preview candidates returned.</li>";
    return;
  }
  for (const c of list) {
    const li = document.createElement("li");
    li.className = "finder-candidate";
    const sizeLabel = formatBytes(c.filesize_bytes);
    const isLarge = Number(c.filesize_bytes || 0) >= 500 * 1024 * 1024;
    const thumbHtml = c.thumbnail_url
      ? `<img class="finder-thumb" src="${escapeHtml(c.thumbnail_url)}" alt="Preview thumbnail" loading="lazy" />`
      : `<div class="finder-thumb finder-thumb-empty">No thumbnail</div>`;
    li.innerHTML = `
      <div class="finder-thumb-wrap">${thumbHtml}</div>
      <div class="finder-meta">
        <div class="finder-title-row">
          <strong>${escapeHtml(c.title || "(untitled)")}</strong>
          <span class="finder-source">${escapeHtml(c.source || "unknown")}</span>
        </div>
        <div class="finder-subline">${escapeHtml(c.creator || "Unknown creator")}</div>
        <div class="finder-stats">
          <span>Duration: ${escapeHtml(formatDurationSec(c.duration_sec))}</span>
          <span class="${isLarge ? "finder-size-large" : ""}">Size: ${escapeHtml(sizeLabel)}</span>
        </div>
        <div class="finder-links">
          <a href="${escapeHtml(c.url || "#")}" target="_blank" rel="noopener noreferrer">Open source</a>
        </div>
      </div>
    `;
    finderList.appendChild(li);
  }
}

function applyFinderFilters() {
  if (!Array.isArray(finderSamplesCache) || finderSamplesCache.length === 0) return;
  const raw = finderMaxSizeMbInput ? Number(finderMaxSizeMbInput.value || 0) : 0;
  const maxBytes = Number.isFinite(raw) && raw > 0 ? raw * 1024 * 1024 : 0;
  const filtered = maxBytes > 0
    ? finderSamplesCache.filter((c) => {
        const size = Number(c.filesize_bytes || 0);
        if (!Number.isFinite(size) || size <= 0) return true;
        return size <= maxBytes;
      })
    : finderSamplesCache.slice();
  renderFinderSamples(filtered);
  if (finderSummary) {
    const suffix =
      maxBytes > 0
        ? ` | showing ${filtered.length}/${finderSamplesCache.length} under ${Math.round(raw)}MB`
        : "";
    finderSummary.textContent = `${finderSummaryBase}${suffix}`;
  }
}

/** Reads `application/x-ndjson` from long-running POST jobs (video finder, download). */
async function readNdjsonProgressStream(res) {
  if (!res.body) return null;
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let finalPayload = null;
  while (true) {
    const { done, value } = await reader.read();
    if (value) buf += dec.decode(value, { stream: true });
    for (;;) {
      const nl = buf.indexOf("\n");
      if (nl < 0) break;
      const raw = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!raw) continue;
      let msg;
      try {
        msg = JSON.parse(raw);
      } catch {
        continue;
      }
      if (msg.type === "phase" && msg.message) {
        appendFinderProgressLine(`— ${msg.message}`);
      } else if (msg.type === "log" && msg.line) {
        const tag = msg.stream === "stderr" ? "err" : "out";
        appendFinderProgressLine(`[${tag}] ${msg.line}`);
      } else if (msg.type === "result") {
        finalPayload = msg;
      }
    }
    if (done) break;
  }
  const tail = buf.trim();
  if (tail) {
    try {
      const msg = JSON.parse(tail);
      if (msg.type === "result") finalPayload = msg;
    } catch {
      /* ignore */
    }
  }
  return finalPayload;
}

async function saveProjectRemote() {
  await fetch("/api/project", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(state),
  });
}

document.getElementById("discoverDownloadLoadBtn").addEventListener("click", async () => {
  const btn = document.getElementById("discoverDownloadLoadBtn");
  if (!btn) return;
  btn.disabled = true;
  finderLogLines.length = 0;
  if (finderProgressLog) {
    finderProgressLog.textContent = "";
    finderProgressLog.classList.add("visible");
  }
  finderList.innerHTML = "";
  const t0 = Date.now();
  let phase = "Starting…";
  let tick = null;
  const refreshSummary = () => {
    const secs = Math.round((Date.now() - t0) / 1000);
    finderSummary.textContent = `${phase} (${secs}s)`;
  };
  try {
    tick = setInterval(refreshSummary, 1000);

    setActiveStage("discovery");
    phase = "Step 1/3: discovery";
    refreshSummary();
    appendFinderProgressLine("— Step 1/3: discovery (video finder)…");

    await saveProjectRemote();
    appendFinderProgressLine("(project saved)");

    const finderRes = await fetch("/api/run-video-finder", { method: "POST" });
    if (!finderRes.ok || !finderRes.body) {
      finderSummary.textContent = `Discovery failed (HTTP ${finderRes.status})`;
      finderList.innerHTML = `<li>${escapeHtml(await finderRes.text())}</li>`;
      return;
    }

    const finderPayload = await readNdjsonProgressStream(finderRes);
    const elapsed1 = Math.round((Date.now() - t0) / 1000);

    if (!finderPayload || !finderPayload.ok) {
      finderSummary.textContent = `Discovery failed after ${elapsed1}s`;
      const detail = [
        finderPayload?.error,
        finderPayload?.detail,
        finderPayload?.signal,
        finderPayload?.exitCode,
      ]
        .filter((x) => x !== undefined && x !== null && x !== "")
        .join(" | ");
      finderList.innerHTML = `<li>${escapeHtml(detail || "Unknown error")}</li>`;
      return;
    }

    const sampleList = finderPayload.samples || [];
    const knownSizes = sampleList.filter((c) => Number(c.filesize_bytes || 0) > 0);
    const largeCount = knownSizes.filter((c) => Number(c.filesize_bytes || 0) >= 500 * 1024 * 1024).length;
    const sizeHint =
      knownSizes.length > 0 ? ` | size-known ${knownSizes.length}/${sampleList.length}, large ${largeCount}` : "";
    finderSummaryBase = `Found ${finderPayload.candidateCount} candidates in ${elapsed1}s (${JSON.stringify(finderPayload.bySource)})${sizeHint}`;
    finderSamplesCache = Array.isArray(sampleList) ? sampleList : [];
    applyFinderFilters();

    setActiveStage("normalize");
    phase = "Step 2/3: download & normalize";
    refreshSummary();
    appendFinderProgressLine("— Step 2/3: download & normalize…");

    await saveProjectRemote();
    appendFinderProgressLine("(project saved)");

    const refreshRes = await fetch("/api/refresh-media", { method: "POST" });
    if (!refreshRes.ok || !refreshRes.body) {
      finderSummary.textContent = `Download failed (HTTP ${refreshRes.status})`;
      const errLi = document.createElement("li");
      errLi.textContent = await refreshRes.text();
      finderList.appendChild(errLi);
      return;
    }

    const refreshPayload = await readNdjsonProgressStream(refreshRes);
    const elapsed2 = Math.round((Date.now() - t0) / 1000);

    if (!refreshPayload || !refreshPayload.ok) {
      finderSummary.textContent = `Download failed after ${elapsed2}s`;
      const detail = [
        refreshPayload?.error,
        refreshPayload?.detail,
        refreshPayload?.signal,
        refreshPayload?.exitCode,
      ]
        .filter((x) => x !== undefined && x !== null && x !== "")
        .join(" | ");
      const errLi = document.createElement("li");
      errLi.textContent = detail || "Unknown error";
      finderList.appendChild(errLi);
      return;
    }

    phase = "Step 3/3: load preview";
    refreshSummary();
    appendFinderProgressLine("— Step 3/3: load media preview…");

    await loadVariants();
    try {
      await fetch("/api/variants/sync-media", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ variant_id: activeVariantId }),
      });
    } catch {}

    await loadMediaManifest();
    await loadMediaLibrary();

    const total = Math.round((Date.now() - t0) / 1000);
    const manifestSummary = finderSummary.textContent || "";
    finderSummary.textContent = `Pipeline complete in ${total}s — ${manifestSummary}`;
    appendFinderProgressLine(`— Finished in ${total}s.`);
  } catch (err) {
    finderSummary.textContent = "Discover / download / load pipeline failed";
  } finally {
    if (tick) clearInterval(tick);
    btn.disabled = false;
  }
});

if (finderMaxSizeMbInput) {
  finderMaxSizeMbInput.addEventListener("input", () => {
    applyFinderFilters();
  });
}
if (finderClearSizeFilterBtn) {
  finderClearSizeFilterBtn.addEventListener("click", () => {
    if (finderMaxSizeMbInput) finderMaxSizeMbInput.value = "";
    applyFinderFilters();
  });
}

document.getElementById("generateScriptBtn").addEventListener("click", async () => {
  setActiveStage("planner");
  const btn = document.getElementById("generateScriptBtn");
  btn.disabled = true;
  finderSummary.textContent = "Generating script and style annotations...";
  finderList.innerHTML = "";
  const startedAt = Date.now();
  const addLine = (text) => {
    const li = document.createElement("li");
    li.textContent = text;
    finderList.appendChild(li);
    return li;
  };
  const s1 = addLine("1) Saving DAG state...");
  const s2 = addLine("2) Running planner...");
  const s3 = addLine("3) Running Gemini/local writer...");
  const timerLine = addLine("Elapsed: 0s");
  const timer = setInterval(() => {
    const secs = Math.round((Date.now() - startedAt) / 1000);
    timerLine.textContent = `Elapsed: ${secs}s`;
  }, 1000);
  try {
    await fetch("/api/project", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(state),
    });
    s1.textContent = "1) Saving DAG state... done";
    s2.textContent = "2) Running planner... in progress";
    const res = await fetch("/api/generate-script", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        topic: (topicInput?.value || "").trim(),
        target_duration_sec: Number(targetDurationInput?.value || 0),
      }),
    });
    const payload = await res.json();
    clearInterval(timer);
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Script/style generation failed";
      s2.textContent = "2) Running planner... failed";
      s3.textContent = "3) Running Gemini/local writer... not completed";
      const err = document.createElement("li");
      err.textContent = payload.error || payload.signal || "Unknown error";
      finderList.appendChild(err);
      btn.disabled = false;
      return;
    }
    s2.textContent = "2) Running planner... done";
    if (payload.project?.nodes && payload.project?.edges) {
      const oldPositions = new Map(positions);
      state.nodes = payload.project.nodes;
      state.edges = payload.project.edges;
      positions.clear();
      for (const n of state.nodes) {
        const prev = oldPositions.get(n.id);
        if (prev) positions.set(n.id, prev);
        else ensureNodePosition(n.id);
      }
      if (selectedNodeId && !state.nodes.some((x) => x.id === selectedNodeId)) selectedNodeId = "";
      render();
    }
    scriptInput.value = payload.text || "";
    if (payload.ai?.used) {
      finderSummary.textContent = "Generated script/style with Gemini from current DAG.";
      s3.textContent = "3) Running Gemini/local writer... Gemini done";
    } else {
      finderSummary.textContent = "Gemini script generation failed.";
      s3.textContent = "3) Running Gemini/local writer... failed";
      const warn = document.createElement("li");
      warn.textContent = payload.ai?.error || "gemini_failed";
      finderList.appendChild(warn);
    }
    const tm = payload.timings_ms || {};
    const timing = document.createElement("li");
    timing.textContent = `Timing: total ${Math.round((tm.total || 0) / 1000)}s | build ${Math.round((tm.build || 0) / 1000)}s | planner ${Math.round((tm.planner || 0) / 1000)}s | ai ${Math.round((tm.ai || 0) / 1000)}s`;
    finderList.appendChild(timing);
    timerLine.textContent = `Elapsed: ${Math.round((Date.now() - startedAt) / 1000)}s`;
    btn.disabled = false;
  } catch (err) {
    clearInterval(timer);
    finderSummary.textContent = "Script/style generation request failed";
    s2.textContent = "2) Running planner... failed";
    s3.textContent = "3) Running Gemini/local writer... not completed";
    timerLine.textContent = `Elapsed: ${Math.round((Date.now() - startedAt) / 1000)}s`;
    btn.disabled = false;
  }
});

document.getElementById("exportDavinciBtn").addEventListener("click", async () => {
  setActiveStage("export");
  finderSummary.textContent = "Exporting DaVinci bundle...";
  try {
    const res = await fetch("/api/export-davinci", { method: "POST" });
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "DaVinci export failed";
      finderList.innerHTML = `<li>${escapeHtml(payload.error || payload.signal || "Unknown export error")}</li>`;
      return;
    }
    finderSummary.textContent = "DaVinci export complete";
    finderList.innerHTML = "";
    const li0 = document.createElement("li");
    li0.textContent = `Output folder: ${payload.outputDir || "(see paths below)"}`;
    finderList.appendChild(li0);
    if (payload.mirroredProjectOutput) {
      const liM = document.createElement("li");
      liM.textContent = `Also copied to project root: ${payload.mirroredProjectOutput} (FCPXML + reports)`;
      finderList.appendChild(liM);
    }
    if (payload.timelineIndexMd) {
      const liT = document.createElement("li");
      liT.textContent = `Timeline index: ${payload.timelineIndexJson} (table + ${payload.timelineIndexMd})`;
      finderList.appendChild(liT);
    }
    await loadTimelineIndex();
    const liProc = document.createElement("li");
    const pc = Number(payload.processedClipCount ?? 0);
    liProc.textContent =
      pc > 0
        ? `Processed clips (crop/fx/LUT): ${pc} file(s) in ${payload.processedDir}`
        : `Processed clips folder: ${payload.processedDir || "—"} (empty if no crop/effects/LUT — timeline uses normalized sources)`;
    finderList.appendChild(liProc);
    const li1 = document.createElement("li");
    li1.textContent = `FCPXML: ${payload.fcpxml}`;
    finderList.appendChild(li1);
    const li2 = document.createElement("li");
    li2.textContent = `Report: ${payload.report}`;
    finderList.appendChild(li2);
    if (payload.exportManifest) {
      const liM = document.createElement("li");
      liM.textContent = `Export manifest: ${payload.exportManifest}`;
      finderList.appendChild(liM);
    }
    if (payload.narrationWav) {
      const liN = document.createElement("li");
      liN.textContent = `Narration: ${payload.narrationWav}`;
      finderList.appendChild(liN);
    }
    const li4 = document.createElement("li");
    li4.textContent = `Crop Validation: ${payload.cropValidation}`;
    finderList.appendChild(li4);
    const li3 = document.createElement("li");
    li3.textContent = "Clip audio is muted in timeline; narration is the only audio track.";
    finderList.appendChild(li3);
    setActiveStage("validate");
    await loadCropValidation();
  } catch (err) {
    finderSummary.textContent = "DaVinci export request failed";
  }
});

document.getElementById("loadScriptBtn").addEventListener("click", async () => {
  await loadScript();
});

async function refreshTimelineMeta() {
  if (!timelineMetaSummary) return;
  try {
    const res = await fetch(`/api/timeline-meta?variant=${encodeURIComponent(activeVariantId)}`);
    const p = await res.json();
    if (p.ok) {
      timelineMetaSummary.textContent = `Sequence ~${Number(p.sequence_duration_sec || 0).toFixed(1)}s (trimmed manifest)`;
    } else {
      timelineMetaSummary.textContent = "";
    }
  } catch {
    timelineMetaSummary.textContent = "";
  }
}

function truncateCell(s, max) {
  const t = String(s || "");
  if (t.length <= max) return t;
  return t.slice(0, max - 1) + "…";
}

async function loadTimelineIndex() {
  if (!timelineIndexTbody) return;
  try {
    const res = await fetch(`/api/timeline-index?variant=${encodeURIComponent(activeVariantId)}`);
    const p = await res.json();
    if (!res.ok || !p.ok || !p.doc || !Array.isArray(p.doc.rows)) {
      timelineIndexTbody.innerHTML = "";
      if (timelineIndexEmpty) timelineIndexEmpty.classList.remove("hidden");
      return;
    }
    if (timelineIndexEmpty) timelineIndexEmpty.classList.add("hidden");
    timelineIndexTbody.innerHTML = "";
    for (const r of p.doc.rows) {
      const tr = document.createElement("tr");
      const cells = [
        r.order,
        r.start_sec.toFixed(3),
        r.end_sec.toFixed(3),
        r.lane,
        r.category,
        r.label,
        r.detail || "",
        r.source || "",
      ];
      for (let i = 0; i < cells.length; i++) {
        const td = document.createElement("td");
        if (i === 0 || i === 1 || i === 2 || i === 3) td.className = "num";
        td.textContent = i >= 5 ? truncateCell(cells[i], 120) : String(cells[i]);
        tr.appendChild(td);
      }
      timelineIndexTbody.appendChild(tr);
    }
  } catch {
    timelineIndexTbody.innerHTML = "";
    if (timelineIndexEmpty) timelineIndexEmpty.classList.remove("hidden");
  }
}

if (loadTimelineIndexBtn) {
  loadTimelineIndexBtn.addEventListener("click", () => loadTimelineIndex());
}

async function loadVariants() {
  if (!variantSelect || !duplicateFromVariant) return;
  try {
    const res = await fetch("/api/variants");
    const p = await res.json();
    if (!p.ok && !p.variants) return;
    activeVariantId = p.active_variant_id || "default";
    variantSelect.innerHTML = "";
    duplicateFromVariant.innerHTML = "";
    for (const v of p.variants || []) {
      const o1 = document.createElement("option");
      o1.value = v.id;
      o1.textContent = v.label ? `${v.label} (${v.id})` : v.id;
      variantSelect.appendChild(o1);
      const o2 = document.createElement("option");
      o2.value = v.id;
      o2.textContent = o1.textContent;
      duplicateFromVariant.appendChild(o2);
    }
    variantSelect.value = activeVariantId;
    await refreshTimelineMeta();
  } catch {
    finderSummary.textContent = "Could not load variants index";
  }
}

async function activateVariantSelection() {
  if (!variantSelect) return;
  const id = variantSelect.value;
  try {
    const res = await fetch("/api/variants/active", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ variant_id: id }),
    });
    const p = await res.json();
    if (!res.ok || !p.ok) {
      finderSummary.textContent = "Failed to switch variant";
      return;
    }
    activeVariantId = p.active_variant_id || id;
    finderSummary.textContent = `Active variant: ${activeVariantId}`;
    await refreshTimelineMeta();
    await loadMediaManifest();
    await loadScript();
    await loadTimelineStudio();
    await loadTimelineIndex();
  } catch {
    finderSummary.textContent = "Variant switch request failed";
  }
}

if (variantSelect) {
  variantSelect.addEventListener("change", () => {
    activateVariantSelection();
  });
}
if (variantReloadBtn) {
  variantReloadBtn.addEventListener("click", async () => {
    await loadVariants();
    await loadMediaManifest();
    await loadTimelineStudio();
    await loadMediaLibrary();
    await loadTimelineIndex();
  });
}
if (createVariantBtn) {
  createVariantBtn.addEventListener("click", async () => {
    const id = (newVariantIdInput?.value || "").trim();
    const label = (newVariantLabelInput?.value || "").trim() || id;
    const fromId = duplicateFromVariant?.value || "default";
    if (!id) {
      finderSummary.textContent = "Enter a new variant id";
      return;
    }
    try {
      const res = await fetch("/api/variants/create", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id, label, from_variant_id: fromId, activate: true }),
      });
      const p = await res.json();
      if (!res.ok || !p.ok) {
        finderSummary.textContent = p.detail || "Create variant failed";
        return;
      }
      await loadVariants();
      variantSelect.value = id;
      await activateVariantSelection();
      finderSummary.textContent = `Created variant ${id}`;
    } catch {
      finderSummary.textContent = "Create variant request failed";
    }
  });
}
if (syncMediaFromRootBtn) {
  syncMediaFromRootBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/variants/sync-media", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ variant_id: activeVariantId }),
      });
      const p = await res.json();
      if (!res.ok || !p.ok) {
        finderSummary.textContent = p.detail || "Sync failed";
        return;
      }
      finderSummary.textContent = "Synced media manifest from project root";
      await loadMediaManifest();
      await refreshTimelineMeta();
    } catch {
      finderSummary.textContent = "Sync request failed";
    }
  });
}

async function loadTimelineStudio() {
  if (!timelineStudioJson) return;
  try {
    const res = await fetch(`/api/timeline-annotations?variant=${encodeURIComponent(activeVariantId)}`);
    const p = await res.json();
    if (!res.ok || !p.ok) {
      timelineStudioJson.value = "";
      return;
    }
    timelineStudioJson.value = JSON.stringify(p.doc, null, 2);
  } catch {
    timelineStudioJson.value = "";
  }
}

if (loadTimelineStudioBtn) {
  loadTimelineStudioBtn.addEventListener("click", () => loadTimelineStudio());
}
if (saveTimelineStudioBtn) {
  saveTimelineStudioBtn.addEventListener("click", async () => {
    if (!timelineStudioJson) return;
    let doc;
    try {
      doc = JSON.parse(timelineStudioJson.value || "{}");
    } catch {
      finderSummary.textContent = "Invalid JSON in timeline studio";
      return;
    }
    try {
      const res = await fetch("/api/timeline-annotations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ variant_id: activeVariantId, doc }),
      });
      const p = await res.json();
      if (!res.ok || !p.ok) {
        finderSummary.textContent = p.error || "Save timeline studio failed";
        return;
      }
      finderSummary.textContent = "Timeline annotations saved";
    } catch {
      finderSummary.textContent = "Save timeline studio request failed";
    }
  });
}

let mediaLibCandidatesCache = [];

async function loadMediaLibrary() {
  if (!mediaLibraryGrid || !mediaLibSegmentFilter) return;
  try {
    const res = await fetch("/api/candidates");
    if (!res.ok) {
      mediaLibraryGrid.innerHTML = "<p class='muted'>Run discovery to populate candidates.</p>";
      return;
    }
    const p = await res.json();
    mediaLibCandidatesCache = Array.isArray(p.candidates) ? p.candidates : [];
    const prev = mediaLibSegmentFilter.value;
    mediaLibSegmentFilter.innerHTML = '<option value="">All segments</option>';
    const segIds = new Set((p.segments || []).map((s) => s.segment_id));
    for (const c of mediaLibCandidatesCache) {
      if (c.segment_id) segIds.add(c.segment_id);
    }
    for (const sid of Array.from(segIds).sort()) {
      const o = document.createElement("option");
      o.value = sid;
      o.textContent = sid;
      mediaLibSegmentFilter.appendChild(o);
    }
    if (prev && Array.from(mediaLibSegmentFilter.options).some((o) => o.value === prev)) {
      mediaLibSegmentFilter.value = prev;
    }
    renderMediaLibraryGrid();
  } catch {
    mediaLibraryGrid.innerHTML = "<p class='muted'>Could not load candidates.</p>";
  }
}

const MEDIA_LIB_MIN_SLOTS = 12;
const MEDIA_LIB_MAX_PADDING = 16;

function picsumPaddingUrl(index) {
  const seed = `pad-${index}-${Math.random().toString(36).slice(2, 10)}-${Date.now()}`;
  return `https://picsum.photos/seed/${encodeURIComponent(seed)}/200/300?grayscale`;
}

function appendMediaLibraryPadding(startIndex, count) {
  if (!mediaLibraryGrid || count <= 0) return;
  for (let i = 0; i < count; i++) {
    const url = picsumPaddingUrl(startIndex + i);
    const card = document.createElement("div");
    card.className = "media-lib-card media-lib-card--padding";
    const img = document.createElement("img");
    img.alt = "";
    img.loading = "lazy";
    img.src = url;
    img.referrerPolicy = "no-referrer";
    card.appendChild(img);
    const title = document.createElement("div");
    title.textContent = "Random placeholder";
    card.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "muted";
    meta.textContent = "picsum · grayscale";
    card.appendChild(meta);
    const row = document.createElement("div");
    row.className = "row";
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.textContent = "Add overlay";
    addBtn.addEventListener("click", async () => {
      const start = Number(mediaLibStartSec?.value || 0);
      try {
        const res = await fetch("/api/media-library/add-overlay", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            variant_id: activeVariantId,
            url,
            kind: "image",
            start,
            duration: 5,
            label: "Picsum placeholder",
          }),
        });
        const payload = await res.json();
        if (!res.ok || !payload.ok) {
          finderSummary.textContent = payload.detail || "Add overlay failed";
          return;
        }
        finderSummary.textContent = `Added overlay ${payload.overlay_id}`;
        await loadTimelineStudio();
      } catch {
        finderSummary.textContent = "Add overlay request failed";
      }
    });
    row.appendChild(addBtn);
    card.appendChild(row);
    mediaLibraryGrid.appendChild(card);
  }
}

function renderMediaLibraryGrid() {
  if (!mediaLibraryGrid || !mediaLibSegmentFilter) return;
  const filterSeg = mediaLibSegmentFilter.value || "";
  mediaLibraryGrid.innerHTML = "";
  let visible = 0;
  for (const c of mediaLibCandidatesCache) {
    if (filterSeg && c.segment_id !== filterSeg) continue;
    visible += 1;
    const thumb = c.thumbnail_url || "";
    const isImg = Boolean(c.is_image);
    const card = document.createElement("div");
    card.className = "media-lib-card";
    if (thumb) {
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.src = thumb;
      img.referrerPolicy = "no-referrer";
      card.appendChild(img);
    }
    const title = document.createElement("div");
    title.textContent = `${c.segment_id || "?"} · ${(c.title || "").slice(0, 42)}${(c.title || "").length > 42 ? "…" : ""}`;
    card.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "muted";
    meta.textContent = `${c.source || ""}${isImg ? " · image" : ""}`;
    card.appendChild(meta);
    const row = document.createElement("div");
    row.className = "row";
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.textContent = "Add overlay";
    const urlToFetch = isImg ? c.url : c.thumbnail_url || "";
    if (!urlToFetch) {
      addBtn.disabled = true;
      addBtn.title = "No downloadable URL";
    }
    addBtn.addEventListener("click", async () => {
      const start = Number(mediaLibStartSec?.value || 0);
      try {
        const res = await fetch("/api/media-library/add-overlay", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            variant_id: activeVariantId,
            url: urlToFetch,
            kind: "image",
            start,
            duration: 5,
            label: (c.title || "Still").slice(0, 40),
          }),
        });
        const payload = await res.json();
        if (!res.ok || !payload.ok) {
          finderSummary.textContent = payload.detail || "Add overlay failed";
          return;
        }
        finderSummary.textContent = `Added overlay ${payload.overlay_id}`;
        await loadTimelineStudio();
      } catch {
        finderSummary.textContent = "Add overlay request failed";
      }
    });
    row.appendChild(addBtn);
    card.appendChild(row);
    mediaLibraryGrid.appendChild(card);
  }
  if (visible === 0 && mediaLibCandidatesCache.length > 0) {
    const note = document.createElement("div");
    note.className = "media-lib-grid-note muted";
    note.textContent = "No items for this filter — placeholders below.";
    mediaLibraryGrid.appendChild(note);
  } else if (!mediaLibraryGrid.children.length) {
    mediaLibraryGrid.innerHTML = "<p class='muted'>No items for this filter.</p>";
    return;
  }
  if (mediaLibCandidatesCache.length > 0) {
    const currentCards = mediaLibraryGrid.querySelectorAll(".media-lib-card:not(.media-lib-card--padding)").length;
    const padCount = Math.min(MEDIA_LIB_MAX_PADDING, Math.max(0, MEDIA_LIB_MIN_SLOTS - currentCards));
    appendMediaLibraryPadding(0, padCount);
  }
}

if (mediaLibSegmentFilter) {
  mediaLibSegmentFilter.addEventListener("change", () => renderMediaLibraryGrid());
}

async function loadScript() {
  finderSummary.textContent = "Loading script...";
  try {
    const res = await fetch(`/api/script?variant=${encodeURIComponent(activeVariantId)}`);
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Script not found yet";
      return;
    }
    scriptInput.value = payload.text || "";
    finderSummary.textContent = "Script loaded";
  } catch (err) {
    finderSummary.textContent = "Failed to load script";
  }
}

document.getElementById("saveScriptBtn").addEventListener("click", async () => {
  const text = (scriptInput.value || "").trim();
  if (!text) {
    finderSummary.textContent = "Enter script text first";
    return;
  }
  finderSummary.textContent = "Saving script...";
  try {
    const res = await fetch("/api/script", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, variant_id: activeVariantId }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Failed to save script";
      return;
    }
    finderSummary.textContent = "Script saved. Export DaVinci will generate voiceover + subtitles.";
  } catch (err) {
    finderSummary.textContent = "Script save request failed";
  }
});

if (voiceoverEngineSelect) {
  try {
    const saved = localStorage.getItem(VOICEOVER_ENGINE_KEY);
    if (saved === "" || saved === "espeak" || saved === "sesame_csm") voiceoverEngineSelect.value = saved;
  } catch {
    /* ignore */
  }
  voiceoverEngineSelect.addEventListener("change", () => {
    try {
      localStorage.setItem(VOICEOVER_ENGINE_KEY, voiceoverEngineSelect.value);
    } catch {
      /* ignore */
    }
  });
}

document.getElementById("generateVoiceoverBtn").addEventListener("click", async () => {
  setActiveStage("subtitles");
  finderSummary.textContent = "Generating voiceover from current script...";
  finderList.innerHTML = "";
  try {
    const engine = voiceoverEngineSelect ? voiceoverEngineSelect.value : "";
    const res = await fetch("/api/generate-voiceover", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ engine }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Voiceover generation failed";
      finderList.innerHTML = `<li>${escapeHtml(payload.error || payload.signal || "Unknown error")}</li>`;
      return;
    }
    finderSummary.textContent = "Voiceover generated from current script";
    const p2 = document.createElement("li");
    p2.textContent = `Voiceover: ${payload.narrationPath}`;
    finderList.appendChild(p2);
  } catch (err) {
    finderSummary.textContent = "Voiceover request failed";
  }
});

clipSelect.addEventListener("change", () => {
  const idx = Number(clipSelect.value);
  if (!Number.isFinite(idx) || idx < 0 || idx >= mediaEntries.length) return;
  const e = mediaEntries[idx];
  clipPreview.src = e.preview_url || "";
  clipIn.value = String(Number(e.timeline?.in_seconds ?? 0));
  clipOut.value = String(Number(e.timeline?.out_seconds ?? e.duration_seconds ?? 0));
  cropX.value = String(Number(e.crop?.x ?? 0));
  cropY.value = String(Number(e.crop?.y ?? 0));
  cropW.value = String(Number(e.crop?.width ?? 0));
  cropH.value = String(Number(e.crop?.height ?? 0));
});

document.getElementById("saveClipEditBtn").addEventListener("click", async () => {
  const idx = Number(clipSelect.value);
  if (!Number.isFinite(idx) || idx < 0 || idx >= mediaEntries.length) return;
  const entry = mediaEntries[idx];
  finderSummary.textContent = `Saving clip edit for ${entry.segment_id}...`;
  try {
    const res = await fetch("/api/media-manifest/update", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        segment_id: entry.segment_id,
        variant_id: activeVariantId,
        in_seconds: Number(clipIn.value || 0),
        out_seconds: Number(clipOut.value || 0),
        crop_x: Number(cropX.value || 0),
        crop_y: Number(cropY.value || 0),
        crop_w: Number(cropW.value || 0),
        crop_h: Number(cropH.value || 0),
      }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Failed to save clip edit";
      return;
    }
    finderSummary.textContent = `Saved edit for ${entry.segment_id}`;
    await loadMediaManifest();
    clipSelect.value = String(idx);
    clipSelect.dispatchEvent(new Event("change"));
  } catch (err) {
    finderSummary.textContent = "Clip edit save request failed";
  }
});

document.getElementById("buildWikiBtn").addEventListener("click", async () => {
  const title = (wikiInput.value || "").trim();
  if (!title) {
    finderSummary.textContent = "Enter a Wikipedia title or URL first.";
    return;
  }
  finderSummary.textContent = "Building graph from Wikipedia...";
  finderList.innerHTML = "";
  try {
    const res = await fetch("/api/build-from-wiki", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Wikipedia graph build failed";
      finderList.innerHTML = `<li>${escapeHtml(payload.error || payload.detail || "Unknown error")}</li>`;
      return;
    }
    state.nodes = payload.project.nodes || [];
    state.edges = payload.project.edges || [];
    positions.clear();
    for (const n of state.nodes) ensureNodePosition(n.id);
    selectedNodeId = "";
    render();
    const summary = payload.meta?.summary_extract ? ` — ${payload.meta.summary_extract.slice(0, 220)}...` : "";
    finderSummary.textContent = `Graph created from "${payload.meta?.seed_title || title}" with ${state.nodes.length} nodes.${summary}`;
    if (payload.warning) {
      const warn = document.createElement("li");
      warn.textContent = `Note: ${payload.warning}`;
      finderList.appendChild(warn);
    }
  } catch (err) {
    finderSummary.textContent = "Wikipedia graph request failed";
  }
});

document.getElementById("expandDagGeminiBtn").addEventListener("click", async () => {
  setActiveStage("planner");
  const title = (topicInput?.value || wikiInput?.value || "").trim();
  finderSummary.textContent = "Expanding DAG with Gemini...";
  finderList.innerHTML = "";
  try {
    await fetch("/api/project", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(state),
    });
    const res = await fetch("/api/expand-dag-gemini", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title }),
    });
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "Gemini DAG expansion failed";
      finderList.innerHTML = `<li>${escapeHtml(payload.error || payload.detail || "Unknown error")}</li>`;
      return;
    }
    state.nodes = payload.project.nodes || [];
    state.edges = payload.project.edges || [];
    positions.clear();
    for (const n of state.nodes) ensureNodePosition(n.id);
    selectedNodeId = "";
    render();
    finderSummary.textContent = `Gemini expanded DAG to ${state.nodes.length} nodes and ${state.edges.length} edges.`;
  } catch (err) {
    finderSummary.textContent = "Gemini DAG expansion request failed";
  }
});

function loadProjectLocal() {
  const fallback = {
    nodes: [
      { id: "n1", title: "Eukaryota", importance: 0.95, tags: ["walrus"], duration_intent_sec: 10 },
      { id: "n2", title: "Animalia", importance: 0.93, tags: ["walrus"], duration_intent_sec: 10 }
    ],
    edges: [{ from: "n1", to: "n2" }]
  };
  const raw = localStorage.getItem(storageKey);
  if (!raw) return fallback;
  try { return JSON.parse(raw); } catch { return fallback; }
}

async function loadProject() {
  const local = loadProjectLocal();
  state.nodes = local.nodes || [];
  state.edges = local.edges || [];
  try {
    const res = await fetch("/api/project");
    if (res.ok) {
      const remote = await res.json();
      if (Array.isArray(remote.nodes) && Array.isArray(remote.edges)) {
        state.nodes = remote.nodes;
        state.edges = remote.edges;
      }
    }
  } catch {}
  for (const n of state.nodes) ensureNodePosition(n.id);
  render();
}

async function loadMediaManifest() {
  try {
    const res = await fetch("/api/media-manifest");
    const payload = await res.json();
    if (!res.ok || !payload.ok) {
      finderSummary.textContent = "No media manifest yet. Run media stage first.";
      return;
    }
    mediaEntries = payload.entries || [];
    clipSelect.innerHTML = "";
    for (let i = 0; i < mediaEntries.length; i++) {
      const e = mediaEntries[i];
      const o = document.createElement("option");
      o.value = String(i);
      o.textContent = `${e.segment_id}: ${e.source_title || e.concept}`;
      clipSelect.appendChild(o);
    }
    if (mediaEntries.length > 0) {
      clipSelect.value = "0";
      clipSelect.dispatchEvent(new Event("change"));
    } else {
      clipPreview.removeAttribute("src");
      clipPreview.load();
    }
    const missing = Number(payload.missing_preview_count || 0);
    finderSummary.textContent =
      missing > 0
        ? `Loaded ${mediaEntries.length} clips (${missing} missing local preview files)`
        : `Loaded ${mediaEntries.length} clips from media manifest`;
    refreshProjectHealth();
  } catch (err) {
    finderSummary.textContent = "Failed to load media manifest";
  }
}

async function loadCropValidation() {
  try {
    const res = await fetch(`/api/crop-validation?variant=${encodeURIComponent(activeVariantId)}`);
    if (!res.ok) {
      exportValidationSummary.textContent = "No crop validation yet.";
      exportValidationList.innerHTML = "";
      refreshProjectHealth();
      return;
    }
    const payload = await res.json();
    const total = Number(payload.checked_segments || 0);
    const passed = Number(payload.passed_checks || 0);
    exportValidationSummary.textContent = `Crop checks: ${passed}/${total}`;
    exportValidationList.innerHTML = "";
    for (const c of payload.checks || []) {
      const li = document.createElement("li");
      const notes = Array.isArray(c.notes) && c.notes.length ? ` - ${c.notes.join("; ")}` : "";
      li.textContent = `${c.segment_id}: ${c.passed ? "PASS" : "FAIL"}${notes}`;
      exportValidationList.appendChild(li);
    }
  } catch {
    exportValidationSummary.textContent = "Failed to read crop validation.";
  }
  refreshProjectHealth();
}

function refreshProjectHealth() {
  const clips = mediaEntries.length;
  const validation = exportValidationSummary.textContent || "No validation";
  projectHealth.textContent = `Project Health: ${clips} clips loaded | ${validation}`;
}

function setActiveStage(stage) {
  activeStage = stage;
  const lis = stageList ? stageList.querySelectorAll("li[data-stage]") : [];
  for (const li of lis) {
    if (li.dataset.stage === activeStage) li.classList.add("active");
    else li.classList.remove("active");
  }
}

function ensureNodePosition(id) {
  if (positions.has(id)) return;
  const idx = state.nodes.findIndex(n => n.id === id);
  const col = idx % 4;
  const row = Math.floor(idx / 4);
  positions.set(id, { x: 120 + col * 220, y: 120 + row * 140 });
}

function render() {
  nodeList.innerHTML = "";
  edgeList.innerHTML = "";
  edgeFrom.innerHTML = "";
  edgeTo.innerHTML = "";
  graphSvg.innerHTML = "";

  for (const n of state.nodes) {
    ensureNodePosition(n.id);
    const li = document.createElement("li");
    li.textContent = `${n.title} (${n.id})`;
    li.onclick = () => selectNode(n.id);
    nodeList.appendChild(li);

    const o1 = document.createElement("option");
    o1.value = n.id; o1.textContent = n.title;
    edgeFrom.appendChild(o1);
    const o2 = document.createElement("option");
    o2.value = n.id; o2.textContent = n.title;
    edgeTo.appendChild(o2);
  }

  for (const e of state.edges) {
    const li = document.createElement("li");
    li.textContent = `${label(e.from)} -> ${label(e.to)}`;
    li.onclick = () => {
      state.edges = state.edges.filter(x => !(x.from === e.from && x.to === e.to));
      render();
    };
    edgeList.appendChild(li);
  }

  drawGraph();
}

function selectNode(id) {
  if (id !== shiftChainLastId) shiftChainLastId = "";
  selectedNodeId = id;
  const n = state.nodes.find(x => x.id === id);
  if (!n) return;
  metaNodeId.value = n.id;
  metaImportance.value = String(n.importance ?? 0.5);
  metaTags.value = (n.tags || []).join(", ");
  metaDuration.value = String(n.duration_intent_sec ?? 10);
  drawGraph();
}

function drawGraph() {
  graphSvg.innerHTML = "";
  const ns = "http://www.w3.org/2000/svg";
  for (const e of state.edges) {
    const p1 = positions.get(e.from);
    const p2 = positions.get(e.to);
    if (!p1 || !p2) continue;
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", String(p1.x));
    line.setAttribute("y1", String(p1.y));
    line.setAttribute("x2", String(p2.x));
    line.setAttribute("y2", String(p2.y));
    line.setAttribute("class", "edge-line");
    graphSvg.appendChild(line);
  }
  for (const n of state.nodes) {
    const p = positions.get(n.id);
    if (!p) continue;
    const g = document.createElementNS(ns, "g");
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", String(p.x));
    c.setAttribute("cy", String(p.y));
    c.setAttribute("r", "42");
    const selected =
      selectedNodeId === n.id || connectSourceNodeId === n.id || shiftChainLastId === n.id;
    c.setAttribute("class", selected ? "node-circle selected" : "node-circle");
    c.addEventListener("mousedown", (ev) => {
      if (ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
      draggingNodeId = n.id;
      selectNode(n.id);
    });
    c.addEventListener("click", (ev) => {
      if (ev.ctrlKey || ev.metaKey) {
        ev.preventDefault();
        removeNodeById(n.id);
        return;
      }
      if (ev.shiftKey) {
        handleShiftChainClick(n.id);
        return;
      }
      if (!connectMode) {
        shiftChainLastId = "";
        selectNode(n.id);
        return;
      }
      shiftChainLastId = "";
      if (!connectSourceNodeId) {
        connectSourceNodeId = n.id;
        finderSummary.textContent = `Connect mode: source selected (${label(n.id)}). Click target node.`;
        drawGraph();
        return;
      }
      if (connectSourceNodeId === n.id) {
        connectSourceNodeId = "";
        finderSummary.textContent = "Connect mode: source cleared.";
        drawGraph();
        return;
      }
      toggleEdge(connectSourceNodeId, n.id);
    });
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", String(p.x));
    t.setAttribute("y", String(p.y));
    t.setAttribute("class", "node-label");
    t.textContent = truncate(n.title, 16);
    g.appendChild(c);
    g.appendChild(t);
    graphSvg.appendChild(g);
  }
}

/** Add edge from→to if missing; returns false if cycle (summary set) or from===to. */
function addEdgeIfValid(from, to) {
  if (from === to) return false;
  if (state.edges.some(e => e.from === from && e.to === to)) return true;
  if (wouldCreateCycle(from, to)) {
    finderSummary.textContent = "Edge rejected: would create a cycle.";
    return false;
  }
  state.edges.push({ from, to });
  return true;
}

function handleShiftChainClick(id) {
  connectSourceNodeId = "";
  if (!shiftChainLastId) {
    shiftChainLastId = id;
    selectNode(id);
    finderSummary.textContent = `Shift-chain: ${label(id)} — shift-click next node to connect in sequence.`;
    drawGraph();
    return;
  }
  if (shiftChainLastId === id) {
    shiftChainLastId = "";
    selectNode(id);
    finderSummary.textContent = "Shift-chain cleared.";
    drawGraph();
    return;
  }
  const from = shiftChainLastId;
  if (!addEdgeIfValid(from, id)) return;
  shiftChainLastId = id;
  selectNode(id);
  finderSummary.textContent = `Chained ${label(from)} → ${label(id)}. Shift-click to extend.`;
  render();
}

function toggleEdge(from, to) {
  const existing = state.edges.find(e => e.from === from && e.to === to);
  if (existing) {
    state.edges = state.edges.filter(e => !(e.from === from && e.to === to));
    finderSummary.textContent = `Removed edge ${label(from)} -> ${label(to)}`;
  } else {
    if (wouldCreateCycle(from, to)) {
      finderSummary.textContent = "Edge rejected: would create a cycle.";
      return;
    }
    state.edges.push({ from, to });
    finderSummary.textContent = `Added edge ${label(from)} -> ${label(to)}`;
  }
  connectSourceNodeId = "";
  render();
}

function wouldCreateCycle(from, to) {
  if (from === to) return true;
  const adj = new Map();
  for (const n of state.nodes) adj.set(n.id, []);
  for (const e of state.edges) {
    if (!adj.has(e.from)) adj.set(e.from, []);
    adj.get(e.from).push(e.to);
  }
  if (!adj.has(from)) adj.set(from, []);
  adj.get(from).push(to);
  const seen = new Set();
  const stack = new Set();
  const visit = (id) => {
    if (stack.has(id)) return true;
    if (seen.has(id)) return false;
    seen.add(id);
    stack.add(id);
    const next = adj.get(id) || [];
    for (const n of next) {
      if (visit(n)) return true;
    }
    stack.delete(id);
    return false;
  };
  for (const n of state.nodes) {
    if (visit(n.id)) return true;
  }
  return false;
}

function label(id) {
  return state.nodes.find(n => n.id === id)?.title || id;
}

function truncate(s, n) {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

graphSvg.addEventListener("mousemove", (ev) => {
  if (!draggingNodeId) return;
  const pt = graphSvg.createSVGPoint();
  pt.x = ev.clientX;
  pt.y = ev.clientY;
  const ctm = graphSvg.getScreenCTM();
  if (!ctm) return;
  const p = pt.matrixTransform(ctm.inverse());
  positions.set(draggingNodeId, { x: p.x, y: p.y });
  drawGraph();
});
window.addEventListener("mouseup", () => {
  draggingNodeId = "";
});

(async () => {
  await loadVariants();
  loadProject();
  await loadScript();
  await loadMediaLibrary();
  await loadTimelineStudio();
  await loadTimelineIndex();
})();
setActiveStage("source");
refreshProjectHealth();

/**
 * Phrase list + per-row recording → 16 kHz mono WAV + metadata.csv for voice_ft/scripts/train.py
 */

const TARGET_SR = 16000;

/**
 * Harvard-style and other classic English speech sentences (public-domain test lines).
 * Good phonetic variety for recording a compact ASR / voice-adaptation set.
 */
const COMMON_VOICE_PHRASES = [
  "The birch canoe slid on the smooth planks.",
  "Glue the sheet to the dark blue background.",
  "It's easy to tell the depth of a well.",
  "These days a chicken leg is a rare dish.",
  "Rice is often served in round bowls.",
  "The juice of lemons makes fine punch.",
  "The box was thrown beside the parked truck.",
  "The hogs were fed chopped corn and garbage.",
  "Four hours of steady work faced us.",
  "Large size in stockings is hard to sell.",
  "The boy was there when the sun rose.",
  "A rod is used to catch pink salmon.",
  "The source of the huge river is the clear spring.",
  "Kick the ball straight and follow through.",
  "Help celebrate your brother's success.",
  "The fish began to leap frantically on the surface.",
  "A big wet stain was on the round carpet.",
  "The view along the creek shocked the rich camper.",
  "The mirror cracked in a thousand pieces.",
  "The empty tin can floated in the salty water.",
  "The sleepy cat crept quietly past the dog.",
  "The stale smell of old beer lingers.",
  "Read verse out loud to sharpen your diction.",
  "Wipe the grease off his dirty face.",
  "We find joy in the simplest things.",
  "Hurdle the pit with the aid of a long pole.",
  "A gold ring will please most any girl.",
  "The drip of the rain made a pleasant sound.",
  "Smoke poured out of every crack.",
  "Serve the hot rum to the tired heroes.",
  "The lazy cow lay in the cool grass.",
  "The friendly gang left the drug store.",
  "Mesh wire keeps chicks inside.",
];

const el = {
  phraseList: document.getElementById("phrase-list"),
  empty: document.getElementById("empty"),
  status: document.getElementById("status"),
  btnAdd: document.getElementById("btn-add-phrase"),
  btnLoadCommon: document.getElementById("btn-load-common"),
  btnLoadLines: document.getElementById("btn-load-lines"),
  bulkText: document.getElementById("bulk-text"),
  btnSaveDir: document.getElementById("btn-save-dir"),
  btnZip: document.getElementById("btn-download-zip"),
  recordHint: document.getElementById("record-hint"),
};

/**
 * @typedef {{ id: number, text: string, wavBlob: Blob | null, playbackUrl: string, savedPath?: string }} Phrase
 */

/** @type {Phrase[]} */
let phrases = [];
let nextPhraseId = 1;
let mediaRecorder = null;
/** @type {MediaStream | null} */
let mediaStream = null;
/** @type {BlobPart[]} */
let recordChunks = [];
/** @type {number | null} */
let recordingPhraseId = null;
/** @type {FileSystemDirectoryHandle | null} */
let lastDirHandle = null;

function setStatus(msg) {
  el.status.textContent = msg || "";
}

function revokePlayback(p) {
  if (p.playbackUrl) {
    URL.revokeObjectURL(p.playbackUrl);
    p.playbackUrl = "";
  }
}

function revokeAllPlayback() {
  for (const p of phrases) revokePlayback(p);
}

function addPhrase(text = "") {
  phrases.push({
    id: nextPhraseId++,
    text,
    wavBlob: null,
    playbackUrl: "",
  });
}

function applyPhraseLines(lines) {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    setStatus("Stop recording before loading a new list.");
    return;
  }
  revokeAllPlayback();
  phrases = [];
  nextPhraseId = 1;
  for (const line of lines) {
    addPhrase(line);
  }
  setStatus(`Loaded ${lines.length} phrase(s).`);
  renderPhrases();
}

function loadPhrasesFromBulkText() {
  const raw = el.bulkText.value;
  const lines = raw
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  if (lines.length === 0) {
    setStatus("Paste at least one non-empty line, or use Add phrase.");
    return;
  }
  applyPhraseLines(lines);
}

function loadCommonPhrases() {
  applyPhraseLines([...COMMON_VOICE_PHRASES]);
  el.bulkText.value = COMMON_VOICE_PHRASES.join("\n");
}

function renderPhrases() {
  revokeAllPlayback();
  el.phraseList.innerHTML = "";
  el.empty.classList.toggle("hidden", phrases.length > 0);

  for (const p of phrases) {
    if (p.wavBlob) {
      p.playbackUrl = URL.createObjectURL(p.wavBlob);
    }

    const li = document.createElement("li");
    li.className = "phrase-row";
    li.dataset.id = String(p.id);
    if (recordingPhraseId === p.id) li.classList.add("recording");

    const hasAudio = !!p.wavBlob;
    const recActive = recordingPhraseId === p.id;
    const recLabel = recActive ? "Stop" : "Rec";

    li.innerHTML = `
      <div class="phrase-main">
        <input type="text" class="phrase-text-input" value="${escapeAttr(p.text)}" aria-label="Phrase text" />
        <span class="phrase-meta">…</span>
        ${hasAudio ? `<audio controls src="${p.playbackUrl}"></audio>` : ""}
      </div>
      <div class="phrase-side">
        <div class="phrase-actions">
          <button type="button" class="btn btn-small btn-record ${recActive ? "active" : ""}" data-action="toggle-rec">${recLabel}</button>
          <button type="button" class="btn btn-small btn-remove" data-action="remove">Remove</button>
        </div>
      </div>
    `;

    const input = li.querySelector(".phrase-text-input");
    input.addEventListener("input", () => {
      p.text = input.value;
      if (p.savedPath) delete p.savedPath;
      if (p.wavBlob) {
        p.wavBlob = null;
        revokePlayback(p);
        renderPhrases();
      }
    });

    li.querySelector('[data-action="toggle-rec"]').addEventListener("click", () => {
      toggleRecordForPhrase(p.id);
    });

    li.querySelector('[data-action="remove"]').addEventListener("click", () => {
      if (recordingPhraseId === p.id && mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
      }
      revokePlayback(p);
      phrases = phrases.filter((x) => x.id !== p.id);
      renderPhrases();
    });

    el.phraseList.appendChild(li);
  }

  for (const p of phrases) {
    const row = el.phraseList.querySelector(`[data-id="${p.id}"]`);
    if (!row) continue;
    const meta = row.querySelector(".phrase-meta");
    if (!p.wavBlob) {
      if (meta) {
        const saved = p.savedPath ? `Saved: ${p.savedPath}` : "No recording yet.";
        meta.textContent = saved;
      }
      continue;
    }
    estimateWavDurationSeconds(p.wavBlob).then((sec) => {
      if (!meta) return;
      const dur = sec != null ? `${sec.toFixed(1)} s` : "";
      const saved = p.savedPath ? ` · ${p.savedPath}` : "";
      meta.textContent = `${dur}${saved}`;
    });
  }
}

function escapeAttr(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function estimateWavDurationSeconds(blob) {
  if (blob.size < 44) return Promise.resolve(null);
  return blob.slice(0, 44).arrayBuffer().then((ab) => {
    const v = new DataView(ab);
    const riff = String.fromCharCode(v.getUint8(0), v.getUint8(1), v.getUint8(2), v.getUint8(3));
    if (riff !== "RIFF") return null;
    const sr = v.getUint32(24, true);
    const bits = v.getUint16(34, true);
    const ch = v.getUint16(22, true);
    const dataSize = v.getUint32(40, true);
    const bps = (sr * ch * bits) / 8;
    return bps > 0 ? dataSize / bps : null;
  });
}

function encodeWavPCM16Mono(samples) {
  const n = samples.length;
  const buffer = new ArrayBuffer(44 + n * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, s) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + n * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_SR, true);
  view.setUint32(28, TARGET_SR * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, n * 2, true);
  let o = 44;
  for (let i = 0; i < n; i++) {
    const x = Math.max(-1, Math.min(1, samples[i]));
    const s16 = Math.round(x < 0 ? x * 32768 : x * 32767);
    view.setInt16(o, Math.max(-32768, Math.min(32767, s16)), true);
    o += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function offlineResampleMono(audioBuffer) {
  const ch = audioBuffer.numberOfChannels;
  const sr = audioBuffer.sampleRate;
  const len = audioBuffer.length;
  let mono;
  if (ch === 1) {
    mono = audioBuffer.getChannelData(0);
  } else {
    mono = new Float32Array(len);
    for (let c = 0; c < ch; c++) {
      const data = audioBuffer.getChannelData(c);
      for (let i = 0; i < len; i++) mono[i] += data[i];
    }
    for (let i = 0; i < len; i++) mono[i] /= ch;
  }

  const outLen = Math.max(1, Math.round((len * TARGET_SR) / sr));
  const offline = new OfflineAudioContext(1, outLen, TARGET_SR);
  const tmp = offline.createBuffer(1, len, sr);
  tmp.copyToChannel(mono.slice(), 0);
  const src = offline.createBufferSource();
  src.buffer = tmp;
  src.connect(offline.destination);
  src.start(0);
  return offline.startRendering().then((rendered) => rendered.getChannelData(0).slice());
}

async function decodeTo16kWavBlob(arrayBuffer) {
  const ctx = new AudioContext();
  let audioBuffer;
  try {
    audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));
  } finally {
    await ctx.close();
  }
  const samples = await offlineResampleMono(audioBuffer);
  return encodeWavPCM16Mono(samples);
}

async function blobTo16kWav(blob) {
  const ab = await blob.arrayBuffer();
  return decodeTo16kWavBlob(ab);
}

function pickRecorderMime() {
  const cands = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  for (const c of cands) {
    if (MediaRecorder.isTypeSupported(c)) return c;
  }
  return "";
}

function cleanupStream() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
}

async function toggleRecordForPhrase(phraseId) {
  if (recordingPhraseId === phraseId && mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    return;
  }

  if (recordingPhraseId !== null && recordingPhraseId !== phraseId) {
    setStatus("Stop the current recording first.");
    return;
  }

  const phrase = phrases.find((x) => x.id === phraseId);
  if (!phrase) return;

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setStatus(`Microphone: ${e.message || e}`);
    return;
  }

  recordChunks = [];
  const mime = pickRecorderMime();
  try {
    mediaRecorder = mime
      ? new MediaRecorder(mediaStream, { mimeType: mime })
      : new MediaRecorder(mediaStream);
  } catch {
    mediaRecorder = new MediaRecorder(mediaStream);
  }

  recordingPhraseId = phraseId;
  el.recordHint.classList.remove("hidden");
  renderPhrases();
  setStatus(`Recording phrase ${phraseId}…`);

  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size) recordChunks.push(e.data);
  };

  mediaRecorder.onstop = async () => {
    const rec = mediaRecorder;
    const mimeType = rec && rec.mimeType ? rec.mimeType : "audio/webm";
    const pid = recordingPhraseId;
    recordingPhraseId = null;
    cleanupStream();
    mediaRecorder = null;
    el.recordHint.classList.add("hidden");
    renderPhrases();

    const blob = new Blob(recordChunks, { type: mimeType });
    recordChunks = [];
    if (!blob.size) {
      setStatus("Recording empty.");
      return;
    }
    const target = phrases.find((x) => x.id === pid);
    if (!target) {
      setStatus("Phrase removed while recording.");
      return;
    }
    setStatus("Processing…");
    try {
      const wav = await blobTo16kWav(blob);
      revokePlayback(target);
      target.wavBlob = wav;
      delete target.savedPath;
      setStatus(`Captured phrase ${pid}.`);
    } catch (e) {
      setStatus(`Decode failed: ${e.message || e}`);
    }
    renderPhrases();
  };

  mediaRecorder.start(250);
  renderPhrases();
}

// —— CSV / export (same layout as before) ——

function parseCsvRecords(text) {
  const rows = [];
  let row = [];
  let field = "";
  let i = 0;
  let inQuotes = false;
  while (i < text.length) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      field += c;
      i++;
      continue;
    }
    if (c === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (c === ",") {
      row.push(field);
      field = "";
      i++;
      continue;
    }
    if (c === "\r") {
      i++;
      continue;
    }
    if (c === "\n") {
      row.push(field);
      if (row.some((cell) => cell.length)) rows.push(row);
      row = [];
      field = "";
      i++;
      continue;
    }
    field += c;
    i++;
  }
  row.push(field);
  if (row.some((cell) => cell.length)) rows.push(row);
  return rows;
}

function parseMetadataCsv(text) {
  const records = parseCsvRecords(text.trim());
  if (records.length === 0) return { header: ["file_name", "text"], dataRows: [] };
  const header = records[0].map((h) => h.trim().toLowerCase());
  const fi = header.indexOf("file_name");
  const ti = header.indexOf("text");
  if (fi === -1 || ti === -1) {
    throw new Error("metadata.csv must have file_name and text columns");
  }
  const dataRows = records
    .slice(1)
    .filter((r) => r[fi] && r[ti])
    .map((r) => [r[fi].trim(), r[ti].trim()]);
  return { header: ["file_name", "text"], dataRows };
}

function csvEscapeCell(s) {
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function buildMetadataCsv(header, dataRows) {
  const lines = [header.join(",")];
  for (const r of dataRows) {
    lines.push(r.map(csvEscapeCell).join(","));
  }
  return lines.join("\r\n") + "\r\n";
}

async function maxClipIndexFromAudioDir(audioDir) {
  let max = 0;
  try {
    for await (const [name] of audioDir.entries()) {
      const m = /^clip_(\d+)\.wav$/i.exec(name);
      if (m) max = Math.max(max, parseInt(m[1], 10));
    }
  } catch {
    /* empty */
  }
  return max;
}

async function readMetadataFromDir(rootDir) {
  try {
    const fh = await rootDir.getFileHandle("metadata.csv");
    const file = await fh.getFile();
    const text = await file.text();
    try {
      return parseMetadataCsv(text);
    } catch {
      return { header: ["file_name", "text"], dataRows: [] };
    }
  } catch {
    return { header: ["file_name", "text"], dataRows: [] };
  }
}

async function savePhrasesToDirectory(rootDir) {
  const audioDir = await rootDir.getDirectoryHandle("audio", { create: true });
  const { dataRows: existingData } = await readMetadataFromDir(rootDir);
  let start = await maxClipIndexFromAudioDir(audioDir);
  for (const row of existingData) {
    const fn = row[0] || "";
    const m = /clip_(\d+)\.wav/i.exec(fn);
    if (m) start = Math.max(start, parseInt(m[1], 10));
  }

  const newRows = [];

  for (const p of phrases) {
    const t = p.text.trim();
    if (!t || !p.wavBlob) continue;
    if (p.savedPath) continue;

    start += 1;
    const base = `clip_${String(start).padStart(6, "0")}.wav`;
    const rel = `audio/${base}`;
    const fileHandle = await audioDir.getFileHandle(base, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(p.wavBlob);
    await writable.close();
    p.savedPath = rel;
    newRows.push([rel, t]);
  }

  if (newRows.length === 0) {
    setStatus("Nothing new to save (record audio for phrases, or all rows already saved).");
    return;
  }

  const merged = existingData.concat(newRows);
  const csvText = buildMetadataCsv(["file_name", "text"], merged);
  const metaHandle = await rootDir.getFileHandle("metadata.csv", { create: true });
  const w = await metaHandle.createWritable();
  await w.write(csvText);
  await w.close();

  lastDirHandle = rootDir;
  setStatus(`Saved ${newRows.length} clip(s) to folder.`);
  renderPhrases();
}

async function pickDirectoryAndSave() {
  if (!window.showDirectoryPicker) {
    setStatus("Folder save needs Chromium, or use Download ZIP.");
    return;
  }
  let dir;
  try {
    dir = await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (e) {
    if (e.name === "AbortError") return;
    setStatus(String(e.message || e));
    return;
  }
  await savePhrasesToDirectory(dir);
}

async function downloadZip() {
  if (typeof JSZip === "undefined") {
    setStatus("JSZip failed to load.");
    return;
  }
  const toZip = phrases.filter((p) => p.text.trim() && p.wavBlob);
  if (toZip.length === 0) {
    setStatus("Record at least one phrase with text before exporting.");
    return;
  }

  setStatus("Building ZIP…");
  const zip = new JSZip();
  const rows = [];
  let i = 0;
  for (const p of toZip) {
    i += 1;
    const base = `clip_${String(i).padStart(6, "0")}.wav`;
    const rel = `audio/${base}`;
    rows.push([rel, p.text.trim()]);
    zip.file(rel, p.wavBlob);
  }
  const csvText = buildMetadataCsv(["file_name", "text"], rows);
  zip.file("metadata.csv", csvText);

  const blob = await zip.generateAsync({ type: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "whisper_dataset.zip";
  a.click();
  URL.revokeObjectURL(a.href);
  setStatus(`Downloaded whisper_dataset.zip (${toZip.length} clips).`);
}

el.btnAdd.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    setStatus("Stop recording first.");
    return;
  }
  addPhrase("");
  renderPhrases();
});

el.btnLoadCommon.addEventListener("click", loadCommonPhrases);

el.btnLoadLines.addEventListener("click", loadPhrasesFromBulkText);

el.btnSaveDir.addEventListener("click", () => {
  pickDirectoryAndSave();
});

el.btnZip.addEventListener("click", () => {
  downloadZip();
});

renderPhrases();

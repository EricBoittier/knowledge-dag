#!/usr/bin/env node
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync, spawn } = require("node:child_process");

const root = __dirname;
const repoRoot = path.resolve(root, "../..");
const projectPath = path.resolve(repoRoot, "projects/walrus-dfs/dag.project.json");
const projectDir = path.resolve(repoRoot, "projects/walrus-dfs");

let variantsLib = null;
try {
  variantsLib = require(path.join(repoRoot, "dist/core/src/variants.js"));
} catch {
  variantsLib = null;
}

function ensureVariantBootstrap() {
  if (variantsLib) variantsLib.ensureVariantsBootstrapped(projectDir);
}

function variantContextFromRequest(req, bodyVariantId) {
  ensureVariantBootstrap();
  let qv = "";
  try {
    const u = new URL(req.url || "/", "http://127.0.0.1");
    qv = u.searchParams.get("variant") || "";
  } catch {
    qv = "";
  }
  const override = String(bodyVariantId || qv || "").trim();
  if (!variantsLib) {
    return { variantId: "default", workDir: projectDir };
  }
  return variantsLib.resolveActiveVariantWorkDir(projectDir, override || undefined);
}

function resolveManifestPath(workDir) {
  const vPath = path.resolve(workDir, "media-manifest.json");
  if (fs.existsSync(vPath)) return vPath;
  const rootPath = path.resolve(projectDir, "media-manifest.json");
  return rootPath;
}

function sequenceDurationSeconds(manifestPath) {
  try {
    const parsed = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    const entries = Array.isArray(parsed.entries) ? parsed.entries : [];
    let sum = 0;
    for (const e of entries) {
      const dur = Number(e.duration_seconds || 1);
      const tin = Number(e.timeline?.in_seconds || 0);
      const tout = Number(e.timeline?.out_seconds || dur);
      sum += Math.max(0.1, Math.min(dur, tout) - tin);
    }
    return sum;
  } catch {
    return 0;
  }
}
const port = 4317;
const VIDEO_FINDER_TIMEOUT_MS = Number(process.env.VIDEO_FINDER_TIMEOUT_MS || 180000);
const DEFAULT_PROJECT = {
  nodes: [
    { id: "n1", title: "Eukaryota", importance: 0.95, tags: ["walrus"], duration_intent_sec: 10 },
    { id: "n2", title: "Animalia", importance: 0.93, tags: ["walrus"], duration_intent_sec: 10 },
  ],
  edges: [{ from: "n1", to: "n2" }],
};

function resolvePreviewPath(entry) {
  const review = entry && entry.review ? path.resolve(String(entry.review)) : "";
  const normalized = entry && entry.normalized ? path.resolve(String(entry.normalized)) : "";
  const downloaded = entry && entry.downloaded ? path.resolve(String(entry.downloaded)) : "";
  // Browser preview prefers web-native containers/codecs first.
  const candidates = [review, downloaded, normalized].filter(Boolean);
  const prefer = candidates.find((p) =>
    fs.existsSync(p) && [".mp4", ".webm", ".ogg", ".m4v"].includes(path.extname(p).toLowerCase())
  );
  if (prefer) return prefer;
  // If no web-native option exists, prefer normalized mezzanine over original downloads.
  if (normalized && fs.existsSync(normalized)) return normalized;
  const any = candidates.find((p) => fs.existsSync(p));
  if (any) return any;
  return "";
}

const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8"
};

/** Buffers stdout/stderr chunks into lines for live NDJSON progress. */
function createLineBuffer(onLine) {
  let buf = "";
  return {
    push(chunk) {
      buf += chunk.toString("utf8");
      for (;;) {
        const i = buf.indexOf("\n");
        if (i < 0) break;
        const line = buf.slice(0, i).replace(/\r$/, "");
        buf = buf.slice(i + 1);
        if (line.length) onLine(line);
      }
    },
    flush() {
      const t = buf.trim();
      buf = "";
      if (t.length) onLine(t);
    },
  };
}

/**
 * Runs a command, forwarding each output line as NDJSON `{ type: "log", stream, line }`.
 * Resolves with exit code / signal when the process closes.
 */
function spawnWithLineLogs(cmd, args, opts) {
  const { cwd, timeoutMs, onEvent } = opts;
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, FORCE_COLOR: "0", PYTHONUNBUFFERED: "1" },
    });
    let settled = false;
    let killed = false;
    const timer =
      timeoutMs > 0
        ? setTimeout(() => {
            killed = true;
            child.kill("SIGTERM");
          }, timeoutMs)
        : null;

    const finish = (outcome) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      outBuf.flush();
      errBuf.flush();
      resolve(outcome);
    };

    const outBuf = createLineBuffer((line) => onEvent({ type: "log", stream: "stdout", line: line.slice(0, 1200) }));
    const errBuf = createLineBuffer((line) => onEvent({ type: "log", stream: "stderr", line: line.slice(0, 1200) }));

    child.stdout.on("data", (c) => outBuf.push(c));
    child.stderr.on("data", (c) => errBuf.push(c));
    child.on("error", (err) => {
      finish({ code: 1, signal: null, spawnError: String(err && err.message ? err.message : err) });
    });
    child.on("close", (code, signal) => {
      finish({
        code: code ?? 1,
        signal: signal || (killed ? "SIGTERM" : null),
        killed,
      });
    });
  });
}

function normalizeWikiTitle(input) {
  let s = String(input || "").trim();
  if (!s) return "";
  const wikiPrefix = "https://en.wikipedia.org/wiki/";
  if (s.startsWith(wikiPrefix)) {
    s = decodeURIComponent(s.slice(wikiPrefix.length));
  }
  s = s.replace(/ /g, "_");
  return s;
}

function fallbackGraphForTitle(title) {
  const rootLabel = String(title || "Topic").replace(/_/g, " ").trim() || "Topic";
  const nodes = [
    { id: "n1", title: rootLabel, importance: 0.98, tags: ["wikipedia", "seed", "fallback"], duration_intent_sec: 15 },
    { id: "n2", title: `${rootLabel} overview`, importance: 0.8, tags: ["fallback"], duration_intent_sec: 10 },
    { id: "n3", title: `${rootLabel} key facts`, importance: 0.78, tags: ["fallback"], duration_intent_sec: 10 },
  ];
  const edges = [
    { from: "n1", to: "n2" },
    { from: "n1", to: "n3" },
  ];
  return {
    nodes,
    edges,
    meta: {
      source: "fallback",
      seed_title: rootLabel,
      summary_extract: "Wikipedia fetch failed; built a starter graph from your topic title.",
    },
  };
}

function buildGraphFromWikiTitle(title) {
  const summaryUrl = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`;
  const linksUrl =
    `https://en.wikipedia.org/w/api.php?action=query&format=json&prop=links&titles=${encodeURIComponent(title)}` +
    `&pllimit=30&plnamespace=0`;

  const pyFetch = (url) =>
    spawnSync(
      "python3",
      [
        "-c",
        [
          "import urllib.request,urllib.error,sys",
          "u=sys.argv[1]",
          "req=urllib.request.Request(u, headers={'User-Agent':'AI-Director-Desktop/0.1 (+local)','Accept':'application/json'})",
          "try:",
          "  print(urllib.request.urlopen(req, timeout=12).read().decode('utf-8'))",
          "except urllib.error.HTTPError as e:",
          "  print(f'HTTP_{e.code}')",
          "  sys.exit(2)",
          "except urllib.error.URLError:",
          "  print('NETWORK_UNREACHABLE')",
          "  sys.exit(3)",
          "except Exception:",
          "  print('REQUEST_FAILED')",
          "  sys.exit(4)",
        ].join("\n"),
        url,
      ],
      { encoding: "utf8", timeout: 12000 }
    );

  const s = pyFetch(summaryUrl);
  if (s.status !== 0 || !String(s.stdout || "").trim()) {
    const reason = String(s.stdout || s.stderr || "").trim() || "REQUEST_FAILED";
    throw new Error(`failed_wiki_summary_fetch:${reason.slice(0, 80)}`);
  }
  const l = pyFetch(linksUrl);
  if (l.status !== 0 || !String(l.stdout || "").trim()) {
    const reason = String(l.stdout || l.stderr || "").trim() || "REQUEST_FAILED";
    throw new Error(`failed_wiki_links_fetch:${reason.slice(0, 80)}`);
  }

  let summary = {};
  let linksPayload = {};
  try {
    summary = JSON.parse(s.stdout);
  } catch {
    throw new Error("wiki_summary_parse_failed");
  }
  try {
    linksPayload = JSON.parse(l.stdout);
  } catch {
    throw new Error("wiki_links_parse_failed");
  }
  const pages = linksPayload?.query?.pages || {};
  const page = Object.values(pages)[0] || {};
  const links = (page.links || [])
    .map((x) => String(x.title || "").trim())
    .filter((x) => x && !x.includes("(disambiguation)"))
    .slice(0, 12);

  const rootLabel = String(summary?.title || title).replace(/_/g, " ");
  const rootNode = {
    id: "n1",
    title: rootLabel,
    importance: 0.98,
    tags: ["wikipedia", "seed"],
    duration_intent_sec: 15,
  };
  const nodes = [rootNode];
  const edges = [];
  let idx = 2;
  for (const link of links) {
    const id = `n${idx++}`;
    nodes.push({
      id,
      title: link,
      importance: 0.75,
      tags: ["wikipedia", "related"],
      duration_intent_sec: 10,
    });
    edges.push({ from: "n1", to: id });
  }

  if (!rootLabel.trim()) {
    throw new Error("wiki_empty_root_label");
  }

  return {
    nodes,
    edges,
    meta: {
      source: "wikipedia",
      seed_title: rootLabel,
      summary_extract: String(summary?.extract || ""),
    },
  };
}

function applyTargetDuration(project, targetDurationSec) {
  const total = Number(targetDurationSec || 0);
  if (!Number.isFinite(total) || total <= 0) return project;
  const count = Math.max(1, (project.nodes || []).length);
  const perNode = Math.max(3, total / count);
  return {
    ...project,
    nodes: (project.nodes || []).map((n) => ({
      ...n,
      duration_intent_sec: Number(perNode.toFixed(2)),
    })),
  };
}

function buildScriptLinesFromText(projectDirPath, scriptText) {
  const shotPlanPath = path.resolve(projectDirPath, "shot-plan.json");
  const shotPlan = JSON.parse(fs.readFileSync(shotPlanPath, "utf8"));
  const segments = Array.isArray(shotPlan.segments) ? shotPlan.segments : [];
  const lines = String(scriptText || "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
  const mapped = segments.map((seg, idx) => {
    const txt = lines[idx] || `${seg.concept} explains a key part of this topic.`;
    return {
      segment_id: seg.segment_id,
      text: txt,
      subtitle_text: txt,
    };
  });
  return { generated_at: new Date().toISOString(), lines: mapped };
}

function readEnvFileVar(filePath, key) {
  try {
    if (!fs.existsSync(filePath)) return "";
    const raw = fs.readFileSync(filePath, "utf8");
    const line = raw
      .split(/\r?\n/)
      .map((x) => x.trim())
      .find((x) => x.startsWith(`${key}=`));
    if (!line) return "";
    const val = line.slice(key.length + 1).trim();
    return val.replace(/^"(.*)"$/, "$1").replace(/^'(.*)'$/, "$1");
  } catch {
    return "";
  }
}

function getGeminiApiKey() {
  return (
    process.env.GEMINI_API_KEY ||
    process.env.GOOGLE_API_KEY ||
    readEnvFileVar(path.resolve(repoRoot, "../development.env"), "GEMINI_API_KEY") ||
    readEnvFileVar(path.resolve(repoRoot, "../development.env"), "GOOGLE_API_KEY") ||
    ""
  );
}

http
  .createServer((req, res) => {
    if (req.method === "GET" && req.url === "/api/project") {
      fs.readFile(projectPath, "utf8", (err, data) => {
        if (err) {
          res.statusCode = 500;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "failed_to_read_project" }));
          return;
        }
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(data);
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/project") {
      let body = "";
      req.on("data", (chunk) => (body += chunk.toString("utf8")));
      req.on("end", () => {
        try {
          const parsed = JSON.parse(body);
          if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
            throw new Error("invalid_shape");
          }
          fs.mkdirSync(path.dirname(projectPath), { recursive: true });
          fs.writeFileSync(projectPath, JSON.stringify(parsed, null, 2) + "\n", "utf8");
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, projectPath }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "invalid_project_payload" }));
        }
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/reset-project") {
      try {
        const filesToDelete = [
          "shot-plan.json",
          "candidates.json",
          "selected-clips.json",
          "media-manifest.json",
          "script-lines.json",
          "script.md",
          "edit-annotations.json",
          "subtitles.srt",
          "subtitle-cues.json",
          "subtitle-style.json",
          "resolve-subtitle-styling.md",
          "transcript.txt",
        ];
        for (const rel of filesToDelete) {
          const abs = path.resolve(projectDir, rel);
          if (fs.existsSync(abs)) fs.rmSync(abs, { force: true });
        }
        const outputDir = path.resolve(projectDir, "output");
        if (fs.existsSync(outputDir)) fs.rmSync(outputDir, { recursive: true, force: true });
        fs.mkdirSync(outputDir, { recursive: true });

        const variantsRoot = path.resolve(projectDir, "variants");
        if (fs.existsSync(variantsRoot)) fs.rmSync(variantsRoot, { recursive: true, force: true });
        const variantsIdx = path.resolve(projectDir, "variants.json");
        if (fs.existsSync(variantsIdx)) fs.rmSync(variantsIdx, { force: true });

        fs.mkdirSync(path.dirname(projectPath), { recursive: true });
        fs.writeFileSync(projectPath, JSON.stringify(DEFAULT_PROJECT, null, 2) + "\n", "utf8");
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: true, project: DEFAULT_PROJECT }));
      } catch (err) {
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "reset_project_failed", detail: String(err && err.message ? err.message : err) }));
      }
      return;
    }

    if (req.method === "GET" && req.url.startsWith("/api/variants")) {
      try {
        ensureVariantBootstrap();
        if (!variantsLib) {
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(
            JSON.stringify({
              ok: true,
              schema_version: 1,
              active_variant_id: "default",
              variants: [{ id: "default", label: "Default cut" }],
              legacy: true,
            })
          );
          return;
        }
        const idx = variantsLib.readVariantsIndex(projectDir);
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: true, ...idx }));
      } catch (err) {
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: false, error: String(err && err.message ? err.message : err) }));
      }
      return;
    }

    if (req.method === "POST" && req.url === "/api/variants/active") {
      let body = "";
      req.on("data", (c) => (body += c.toString("utf8")));
      req.on("end", () => {
        try {
          ensureVariantBootstrap();
          if (!variantsLib) throw new Error("variants_module_unavailable");
          const payload = JSON.parse(body || "{}");
          const id = String(payload.variant_id || "").trim();
          if (!id) throw new Error("missing_variant_id");
          const idx = variantsLib.setActiveVariant(projectDir, id);
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, ...idx }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: false, detail: String(err && err.message ? err.message : err) }));
        }
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/variants/create") {
      let body = "";
      req.on("data", (c) => (body += c.toString("utf8")));
      req.on("end", () => {
        try {
          ensureVariantBootstrap();
          if (!variantsLib) throw new Error("variants_module_unavailable");
          const payload = JSON.parse(body || "{}");
          const id = String(payload.id || "").trim();
          if (!id) throw new Error("missing_id");
          const fromId = String(payload.from_variant_id || "default").trim() || "default";
          const label = String(payload.label || id).trim();
          variantsLib.duplicateVariant(projectDir, fromId, id, label);
          if (payload.activate) variantsLib.setActiveVariant(projectDir, id);
          const idx = variantsLib.readVariantsIndex(projectDir);
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, ...idx }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: false, detail: String(err && err.message ? err.message : err) }));
        }
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/variants/sync-media") {
      let body = "";
      req.on("data", (c) => (body += c.toString("utf8")));
      req.on("end", () => {
        try {
          ensureVariantBootstrap();
          if (!variantsLib) throw new Error("variants_module_unavailable");
          const payload = JSON.parse(body || "{}");
          const { variantId } = variantContextFromRequest(req, payload.variant_id);
          variantsLib.syncVariantMediaFromRoot(projectDir, variantId);
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, variant_id: variantId }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: false, detail: String(err && err.message ? err.message : err) }));
        }
      });
      return;
    }

    if (req.method === "GET" && req.url.startsWith("/api/timeline-meta")) {
      try {
        const { workDir } = variantContextFromRequest(req, "");
        const mp = resolveManifestPath(workDir);
        const seconds = sequenceDurationSeconds(mp);
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: true, manifest_path: mp, sequence_duration_sec: seconds }));
      } catch (err) {
        res.statusCode = 400;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: false, detail: String(err && err.message ? err.message : err) }));
      }
      return;
    }

    if (req.method === "GET" && req.url.startsWith("/api/timeline-index")) {
      try {
        const { workDir, variantId } = variantContextFromRequest(req, "");
        const rootOut = path.resolve(projectDir, "output", "timeline-index.json");
        const vOut = path.resolve(workDir, "output", "timeline-index.json");
        const pick = fs.existsSync(vOut) ? vOut : fs.existsSync(rootOut) ? rootOut : null;
        if (!pick) {
          res.statusCode = 404;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: false, error: "timeline_index_not_found" }));
          return;
        }
        const doc = JSON.parse(fs.readFileSync(pick, "utf8"));
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: true, variant_id: variantId, path: pick, doc }));
      } catch (err) {
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: false, error: String(err && err.message ? err.message : err) }));
      }
      return;
    }

    if (req.method === "GET" && req.url.startsWith("/api/timeline-annotations")) {
      try {
        const { workDir } = variantContextFromRequest(req, "");
        const p = path.resolve(workDir, "timeline-annotations.json");
        if (!fs.existsSync(p)) {
          if (!variantsLib) {
            res.statusCode = 404;
            res.end(JSON.stringify({ error: "not_found" }));
            return;
          }
          const empty = variantsLib.emptyTimelineAnnotations();
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, doc: empty }));
          return;
        }
        const doc = JSON.parse(fs.readFileSync(p, "utf8"));
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: true, doc }));
      } catch (err) {
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: String(err && err.message ? err.message : err) }));
      }
      return;
    }

    if (req.method === "POST" && req.url === "/api/timeline-annotations") {
      let body = "";
      req.on("data", (c) => (body += c.toString("utf8")));
      req.on("end", () => {
        try {
          ensureVariantBootstrap();
          const payload = JSON.parse(body || "{}");
          const { workDir } = variantContextFromRequest(req, payload.variant_id);
          const doc = payload.doc;
          if (!doc || typeof doc !== "object") throw new Error("missing_doc");
          doc.generated_at = new Date().toISOString();
          const p = path.resolve(workDir, "timeline-annotations.json");
          fs.mkdirSync(workDir, { recursive: true });
          fs.writeFileSync(p, JSON.stringify(doc, null, 2) + "\n", "utf8");
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: String(err && err.message ? err.message : err) }));
        }
      });
      return;
    }

    if (req.method === "GET" && req.url.startsWith("/api/candidates")) {
      try {
        const cPath = path.resolve(projectDir, "candidates.json");
        const shotPath = path.resolve(projectDir, "shot-plan.json");
        const raw = fs.readFileSync(cPath, "utf8");
        const parsed = JSON.parse(raw);
        let segments = [];
        try {
          const sp = JSON.parse(fs.readFileSync(shotPath, "utf8"));
          segments = Array.isArray(sp.segments) ? sp.segments : [];
        } catch {}
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(
          JSON.stringify({
            ok: true,
            candidates: parsed.candidates || [],
            segments,
            generated_at: parsed.generated_at,
          })
        );
      } catch (err) {
        res.statusCode = 404;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: false, error: "candidates_not_found" }));
      }
      return;
    }

    if (req.method === "POST" && req.url === "/api/media-library/add-overlay") {
      let body = "";
      req.on("data", (c) => (body += c.toString("utf8")));
      req.on("end", async () => {
        try {
          ensureVariantBootstrap();
          const payload = JSON.parse(body || "{}");
          const { workDir, variantId } = variantContextFromRequest(req, payload.variant_id);
          const url = String(payload.url || "").trim();
          const start = Number(payload.start || 0);
          const duration = Number(payload.duration || 5);
          const kind = String(payload.kind || "image");
          if (!url) throw new Error("missing_url");
          const stillsDir = path.resolve(projectDir, "output", "stills");
          fs.mkdirSync(stillsDir, { recursive: true });
          const hash = crypto.createHash("sha1").update(url).digest("hex").slice(0, 14);
          let ext = path.extname(new URL(url).pathname || "");
          if (!ext || ext.length > 5) ext = kind === "image" ? ".jpg" : ".bin";
          const dest = path.resolve(stillsDir, `lib_${hash}${ext}`);
          if (!fs.existsSync(dest)) {
            const r = await fetch(url, { redirect: "follow" });
            if (!r.ok) throw new Error(`download_failed:${r.status}`);
            const buf = Buffer.from(await r.arrayBuffer());
            fs.writeFileSync(dest, buf);
          }
          const taPath = path.resolve(workDir, "timeline-annotations.json");
          let doc = variantsLib ? variantsLib.emptyTimelineAnnotations() : { schema_version: 1, mode: "studio", markers: [], text_overlays: [], media_overlays: [] };
          if (fs.existsSync(taPath)) {
            try {
              doc = JSON.parse(fs.readFileSync(taPath, "utf8"));
            } catch {}
          }
          doc.mode = "studio";
          doc.media_overlays = Array.isArray(doc.media_overlays) ? doc.media_overlays : [];
          const id = `ml_${Date.now()}`;
          doc.media_overlays.push({
            id,
            kind: kind === "audio" ? "audio" : "image",
            path: path.relative(projectDir, dest),
            start,
            duration,
            label: String(payload.label || "Media library"),
          });
          doc.generated_at = new Date().toISOString();
          fs.mkdirSync(workDir, { recursive: true });
          fs.writeFileSync(taPath, JSON.stringify(doc, null, 2) + "\n", "utf8");
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, variant_id: variantId, overlay_id: id, local_path: dest }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: false, detail: String(err && err.message ? err.message : err) }));
        }
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/refresh-media") {
      res.writeHead(200, {
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });
      const writeEvt = (obj) => {
        try {
          res.write(`${JSON.stringify(obj)}\n`);
        } catch (_) {}
      };

      (async () => {
        try {
          writeEvt({ type: "phase", phase: "npm_build", message: "Compiling (npm run build)…" });
          const build = await spawnWithLineLogs("npm", ["run", "build"], {
            cwd: repoRoot,
            timeoutMs: 180000,
            onEvent: writeEvt,
          });
          if (build.code !== 0) {
            writeEvt({
              type: "result",
              ok: false,
              error: "build_failed",
              exitCode: build.code,
              signal: build.signal,
              detail: build.spawnError || "npm run build failed",
            });
            res.end();
            return;
          }

          writeEvt({
            type: "phase",
            phase: "normalize",
            message:
              "Downloading + normalizing clips (yt-dlp, ffmpeg). Progress lines from Python start with [download]…",
          });
          const run = await spawnWithLineLogs(
            "node",
            [
              "./dist/core/src/cli/build-project.js",
              "--project",
              "./projects/walrus-dfs",
              "--from-stage",
              "normalize",
              "--to-stage",
              "media",
              "--skip-upload",
            ],
            { cwd: repoRoot, timeoutMs: 600000, onEvent: writeEvt }
          );
          if (run.code !== 0) {
            writeEvt({
              type: "result",
              ok: false,
              error: "refresh_media_failed",
              exitCode: run.code,
              signal: run.signal,
              detail: run.killed ? "download pipeline timed out or was stopped" : "normalize / validate step failed",
            });
            res.end();
            return;
          }
          writeEvt({ type: "result", ok: true });
        } catch (err) {
          writeEvt({
            type: "result",
            ok: false,
            error: "server_error",
            detail: String(err && err.message ? err.message : err),
          });
        }
        res.end();
      })();

      return;
    }

    if (req.method === "POST" && req.url === "/api/run-video-finder") {
      res.writeHead(200, {
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });
      const writeEvt = (obj) => {
        try {
          res.write(`${JSON.stringify(obj)}\n`);
        } catch (_) {}
      };

      (async () => {
        try {
          writeEvt({
            type: "phase",
            phase: "npm_build",
            message: "Compiling TypeScript (npm run build). This may take a minute the first time…",
          });
          const build = await spawnWithLineLogs("npm", ["run", "build"], {
            cwd: repoRoot,
            timeoutMs: 180000,
            onEvent: writeEvt,
          });
          if (build.code !== 0) {
            writeEvt({
              type: "result",
              ok: false,
              error: "build_failed",
              exitCode: build.code,
              signal: build.signal,
              detail: build.spawnError || "npm run build exited with a non-zero code",
            });
            res.end();
            return;
          }

          writeEvt({
            type: "phase",
            phase: "pipeline",
            message: "Running pipeline stages source → discovery (dry run). Watch log for segment progress…",
          });
          const run = await spawnWithLineLogs(
            "node",
            [
              "./dist/core/src/cli/build-project.js",
              "--project",
              "./projects/walrus-dfs",
              "--from-stage",
              "source",
              "--to-stage",
              "discovery",
              "--dry-run",
              "--skip-upload",
            ],
            { cwd: repoRoot, timeoutMs: VIDEO_FINDER_TIMEOUT_MS, onEvent: writeEvt }
          );
          if (run.code !== 0) {
            writeEvt({
              type: "result",
              ok: false,
              error: "video_finder_failed",
              exitCode: run.code,
              signal: run.signal,
              timeout_ms: VIDEO_FINDER_TIMEOUT_MS,
              detail:
                run.signal === "SIGTERM" || run.killed
                  ? "video finder timed out or was stopped"
                  : "video finder process failed",
            });
            res.end();
            return;
          }

          let candidates = [];
          try {
            const raw = fs.readFileSync(path.resolve(repoRoot, "projects/walrus-dfs/candidates.json"), "utf8");
            candidates = JSON.parse(raw).candidates || [];
          } catch {}
          const bySource = {};
          for (const c of candidates) {
            bySource[c.source] = (bySource[c.source] || 0) + 1;
          }
          writeEvt({
            type: "result",
            ok: true,
            candidateCount: candidates.length,
            bySource,
            samples: candidates.slice(0, 24),
          });
        } catch (err) {
          writeEvt({
            type: "result",
            ok: false,
            error: "server_error",
            detail: String(err && err.message ? err.message : err),
          });
        }
        res.end();
      })();

      return;
    }

    if (req.method === "POST" && req.url === "/api/generate-script") {
      let body = "";
      req.on("data", (chunk) => (body += chunk.toString("utf8")));
      req.on("end", () => {
        let payload = {};
        try {
          payload = body ? JSON.parse(body) : {};
        } catch {
          payload = {};
        }
        const targetDurationSec = Number(payload.target_duration_sec || 0);
      const startedAt = Date.now();
      const scriptPath = path.resolve(projectDir, "script.md");
      const scriptLinesPath = path.resolve(projectDir, "script-lines.json");
      const annotationsPath = path.resolve(projectDir, "edit-annotations.json");
      const prevScript = fs.existsSync(scriptPath) ? fs.readFileSync(scriptPath, "utf8") : "";
      const prevScriptLines = fs.existsSync(scriptLinesPath) ? fs.readFileSync(scriptLinesPath, "utf8") : "";
      const prevAnnotations = fs.existsSync(annotationsPath) ? fs.readFileSync(annotationsPath, "utf8") : "";
      const build = spawnSync("npm", ["run", "build"], { cwd: repoRoot, encoding: "utf8" });
      if (build.status !== 0) {
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "build_failed", stderr: build.stderr, stdout: build.stdout }));
        return;
      }
      // Client POSTs /api/project immediately before this call. Do not replace the DAG from
      // Wikipedia here — that wiped manual graph edits whenever the topic field was filled.
      // Use "Build from Wiki" / expand DAG in the UI to change structure.
      if (targetDurationSec > 0) {
        try {
          const current = JSON.parse(fs.readFileSync(projectPath, "utf8"));
          const tuned = applyTargetDuration(current, targetDurationSec);
          fs.writeFileSync(projectPath, JSON.stringify(tuned, null, 2) + "\n", "utf8");
        } catch {
          // Keep existing project if duration-only update fails.
        }
      }
      const afterBuildMs = Date.now() - startedAt;
      const run = spawnSync(
        "node",
        [
          "./dist/core/src/cli/build-project.js",
          "--project",
          "./projects/walrus-dfs",
          "--from-stage",
          "planner",
          "--to-stage",
          "planner",
          "--skip-upload",
        ],
        { cwd: repoRoot, encoding: "utf8", timeout: 120000 }
      );
      if (run.status !== 0) {
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "generate_script_failed", stderr: run.stderr, stdout: run.stdout, signal: run.signal }));
        return;
      }
      const apiKey = String(getGeminiApiKey() || "").trim();
      if (!apiKey) {
        if (prevScript) fs.writeFileSync(scriptPath, prevScript, "utf8");
        if (prevScriptLines) fs.writeFileSync(scriptLinesPath, prevScriptLines, "utf8");
        if (prevAnnotations) fs.writeFileSync(annotationsPath, prevAnnotations, "utf8");
        res.statusCode = 400;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "missing_gemini_api_key" }));
        return;
      }
      const afterPlannerMs = Date.now() - startedAt;
      let ai = { used: false, error: "" };
      const aiRun = spawnSync(
        "node",
        ["./dist/planner/src/gemini-script-cli.js", "--project", "./projects/walrus-dfs", "--api-key", apiKey],
        { cwd: repoRoot, encoding: "utf8", timeout: 120000 }
      );
      if (aiRun.status === 0) {
        ai.used = true;
      } else {
        ai.error = aiRun.stderr || aiRun.stdout || "gemini_failed";
        if (prevScript) fs.writeFileSync(scriptPath, prevScript, "utf8");
        if (prevScriptLines) fs.writeFileSync(scriptLinesPath, prevScriptLines, "utf8");
        if (prevAnnotations) fs.writeFileSync(annotationsPath, prevAnnotations, "utf8");
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "gemini_script_failed", detail: ai.error }));
        return;
      }
      const afterAiMs = Date.now() - startedAt;
      const text = fs.existsSync(scriptPath) ? fs.readFileSync(scriptPath, "utf8") : "";
      let project = { nodes: [], edges: [] };
      try {
        project = JSON.parse(fs.readFileSync(projectPath, "utf8"));
      } catch {}
      try {
        ensureVariantBootstrap();
        if (variantsLib) {
          const { workDir } = variantsLib.resolveActiveVariantWorkDir(projectDir);
          for (const name of ["script.md", "script-lines.json", "edit-annotations.json"]) {
            const src = path.resolve(projectDir, name);
            const dst = path.resolve(workDir, name);
            if (fs.existsSync(src)) fs.copyFileSync(src, dst);
          }
        }
      } catch {}
      res.setHeader("content-type", "application/json; charset=utf-8");
      res.end(
        JSON.stringify({
          ok: true,
          scriptPath,
          text,
          project,
          ai,
          timings_ms: {
            total: afterAiMs,
            build: afterBuildMs,
            planner: Math.max(0, afterPlannerMs - afterBuildMs),
            ai: Math.max(0, afterAiMs - afterPlannerMs),
          },
        })
      );
      return;
      });
    }

    if (req.method === "GET" && req.url === "/api/media-manifest") {
      try {
        ensureVariantBootstrap();
        const { workDir, variantId } = variantContextFromRequest(req, "");
        const manifestPath = resolveManifestPath(workDir);
        const raw = fs.readFileSync(manifestPath, "utf8");
        const parsed = JSON.parse(raw);
        const entries = Array.isArray(parsed.entries) ? parsed.entries : [];
        let missingCount = 0;
        const withPreview = entries.map((e, i) => ({
          ...e,
          _index: i,
          _preview_path: resolvePreviewPath(e),
          preview_url: `/api/media-file?i=${i}&variant=${encodeURIComponent(variantId)}`,
        }));
        for (const e of withPreview) {
          if (!e._preview_path) missingCount += 1;
        }
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(
          JSON.stringify({
            ok: true,
            variant_id: variantId,
            generated_at: parsed.generated_at,
            entries: withPreview,
            failures: parsed.failures || [],
            missing_preview_count: missingCount,
          })
        );
      } catch (err) {
        res.statusCode = 404;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "media_manifest_not_found" }));
      }
      return;
    }

    if (req.method === "GET" && req.url.startsWith("/api/media-file")) {
      try {
        const u = new URL(req.url, "http://localhost");
        const idx = Number(u.searchParams.get("i"));
        if (!Number.isFinite(idx) || idx < 0) {
          res.statusCode = 400;
          res.end("invalid index");
          return;
        }
        ensureVariantBootstrap();
        const { workDir } = variantContextFromRequest(req, u.searchParams.get("variant") || "");
        const manifestPath = resolveManifestPath(workDir);
        const raw = fs.readFileSync(manifestPath, "utf8");
        const parsed = JSON.parse(raw);
        const entries = Array.isArray(parsed.entries) ? parsed.entries : [];
        const entry = entries[idx];
        if (!entry) {
          res.statusCode = 404;
          res.end("media entry not found");
          return;
        }
        const filePath = resolvePreviewPath(entry);
        if (!filePath) {
          res.statusCode = 404;
          res.end("media file not found");
          return;
        }
        if (!filePath.startsWith(path.resolve(repoRoot))) {
          res.statusCode = 403;
          res.end("forbidden");
          return;
        }
        if (!fs.existsSync(filePath)) {
          res.statusCode = 404;
          res.end("file not found");
          return;
        }
        const stat = fs.statSync(filePath);
        const fileSize = stat.size;
        const ext = path.extname(filePath).toLowerCase();
        const contentTypeByExt = {
          ".mp4": "video/mp4",
          ".m4v": "video/mp4",
          ".webm": "video/webm",
          ".ogg": "video/ogg",
          ".mov": "video/quicktime",
          ".mkv": "video/x-matroska",
        };
        const contentType = contentTypeByExt[ext] || "application/octet-stream";
        const range = req.headers.range;
        if (range) {
          const m = /^bytes=(\d*)-(\d*)$/.exec(String(range).trim());
          if (!m) {
            res.statusCode = 416;
            res.setHeader("content-range", `bytes */${fileSize}`);
            res.end();
            return;
          }
          const start = m[1] ? Number(m[1]) : 0;
          const end = m[2] ? Number(m[2]) : fileSize - 1;
          if (!Number.isFinite(start) || !Number.isFinite(end) || start > end || start >= fileSize) {
            res.statusCode = 416;
            res.setHeader("content-range", `bytes */${fileSize}`);
            res.end();
            return;
          }
          res.statusCode = 206;
          res.setHeader("content-type", contentType);
          res.setHeader("accept-ranges", "bytes");
          res.setHeader("content-range", `bytes ${start}-${end}/${fileSize}`);
          res.setHeader("content-length", String(end - start + 1));
          fs.createReadStream(filePath, { start, end }).pipe(res);
          return;
        }
        res.statusCode = 200;
        res.setHeader("content-type", contentType);
        res.setHeader("accept-ranges", "bytes");
        res.setHeader("content-length", String(fileSize));
        fs.createReadStream(filePath).pipe(res);
      } catch (err) {
        res.statusCode = 500;
        res.end("failed to read media file");
      }
      return;
    }

    if (req.method === "POST" && req.url === "/api/media-manifest/update") {
      let body = "";
      req.on("data", (chunk) => (body += chunk.toString("utf8")));
      req.on("end", () => {
        try {
          ensureVariantBootstrap();
          const patch = JSON.parse(body || "{}");
          const segmentId = String(patch.segment_id || "").trim();
          if (!segmentId) throw new Error("missing_segment_id");
          const { workDir } = variantContextFromRequest(req, patch.variant_id);
          let manifestPath = path.resolve(workDir, "media-manifest.json");
          if (!fs.existsSync(manifestPath)) {
            const rootM = path.resolve(projectDir, "media-manifest.json");
            if (fs.existsSync(rootM) && workDir !== projectDir) {
              fs.mkdirSync(workDir, { recursive: true });
              fs.copyFileSync(rootM, manifestPath);
            } else {
              manifestPath = rootM;
            }
          }
          const raw = fs.readFileSync(manifestPath, "utf8");
          const parsed = JSON.parse(raw);
          const entries = Array.isArray(parsed.entries) ? parsed.entries : [];
          const entry = entries.find((e) => e.segment_id === segmentId);
          if (!entry) throw new Error("segment_not_found");

          const inSec = Number(patch.in_seconds);
          const outSec = Number(patch.out_seconds);
          const dur = Number(entry.duration_seconds || 0);
          const nextIn = Number.isFinite(inSec) ? Math.max(0, inSec) : Number(entry.timeline?.in_seconds || 0);
          const nextOut =
            Number.isFinite(outSec) && outSec > 0 ? Math.min(dur || outSec, outSec) : Number(entry.timeline?.out_seconds || dur);
          entry.timeline = {
            ...(entry.timeline || {}),
            enabled: true,
            label: entry.concept,
            in_seconds: nextIn,
            out_seconds: Math.max(nextIn + 0.1, nextOut),
          };
          entry.crop = {
            x: Number(patch.crop_x || 0),
            y: Number(patch.crop_y || 0),
            width: Number(patch.crop_w || 0),
            height: Number(patch.crop_h || 0),
          };
          fs.writeFileSync(manifestPath, JSON.stringify(parsed, null, 2) + "\n", "utf8");
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, entry }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "media_manifest_update_failed", detail: String(err && err.message ? err.message : err) }));
        }
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/export-davinci") {
      ensureVariantBootstrap();
      const { variantId, workDir } = variantContextFromRequest(req, "");
      const args = [
        "./dist/core/src/cli/build-project.js",
        "--project",
        "./projects/walrus-dfs",
        "--from-stage",
        "subtitles",
        "--to-stage",
        "validate",
        "--skip-upload",
      ];
      if (variantsLib) args.push("--variant", variantId);
      const run = spawnSync("node", args, { cwd: repoRoot, encoding: "utf8", timeout: 300000 });
      if (run.status !== 0) {
        res.statusCode = 500;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "export_failed", stderr: run.stderr, stdout: run.stdout, signal: run.signal }));
        return;
      }
      const outDir = path.resolve(workDir, "output");
      const processedDir = path.resolve(outDir, "processed");
      const fcpxml = path.resolve(outDir, "timeline_davinci_resolve.fcpxml");
      const report = path.resolve(outDir, "import-report.md");
      const cropValidation = path.resolve(outDir, "crop-validation.json");
      const exportManifest = path.resolve(outDir, "export-manifest.json");
      const timelineIndexJson = path.resolve(outDir, "timeline-index.json");
      const timelineIndexMd = path.resolve(outDir, "timeline-index.md");
      const narrationPath = path.resolve(outDir, "narration.wav");
      let processedClipCount = 0;
      try {
        if (fs.existsSync(processedDir)) {
          processedClipCount = fs.readdirSync(processedDir).filter((f) => /\.mov$/i.test(f)).length;
        }
      } catch (_) {}
      const mirroredProjectOutput = path.resolve(projectDir, "output");
      res.setHeader("content-type", "application/json; charset=utf-8");
      res.end(
        JSON.stringify({
          ok: true,
          variant_id: variantId,
          fcpxml,
          report,
          cropValidation,
          exportManifest,
          timelineIndexJson,
          timelineIndexMd,
          outputDir: outDir,
          mirroredProjectOutput:
            path.resolve(outDir) !== path.resolve(mirroredProjectOutput) ? mirroredProjectOutput : null,
          processedDir,
          processedClipCount,
          narrationWav: fs.existsSync(narrationPath) ? narrationPath : null,
          stdout: run.stdout,
        })
      );
      return;
    }

    if (req.method === "POST" && req.url === "/api/generate-voiceover") {
      let body = "";
      req.on("data", (chunk) => (body += chunk.toString("utf8")));
      req.on("end", () => {
        let engine = "";
        try {
          const j = body ? JSON.parse(body) : {};
          engine = String(j.engine || "").trim();
        } catch {
          engine = "";
        }
        ensureVariantBootstrap();
        const { workDir } = variantContextFromRequest(req, "");
        try {
          const scriptPath = path.resolve(workDir, "script.md");
          const fallbackScript = path.resolve(projectDir, "script.md");
          const spath = fs.existsSync(scriptPath) ? scriptPath : fallbackScript;
          if (fs.existsSync(spath)) {
            const text = fs.readFileSync(spath, "utf8");
            const linesPayload = buildScriptLinesFromText(projectDir, text);
            fs.mkdirSync(workDir, { recursive: true });
            fs.writeFileSync(path.resolve(workDir, "script-lines.json"), JSON.stringify(linesPayload, null, 2) + "\n", "utf8");
            if (!fs.existsSync(scriptPath)) {
              fs.writeFileSync(scriptPath, text + (text.endsWith("\n") ? "" : "\n"), "utf8");
            }
          }
        } catch {
          // Keep existing script-lines.json if sync step fails.
        }
        const configPath = path.resolve(repoRoot, "config/pipeline.config.json");
        const pyArgs = [
          path.resolve(repoRoot, "packages/pipeline/src-py/generate_voiceover.py"),
          "--project-dir",
          workDir,
          "--config",
          configPath,
        ];
        if (engine) pyArgs.push("--engine", engine);
        // Sesame CSM (model load + generate) can exceed a few minutes; espeak is fast either way.
        const run = spawnSync("python3", pyArgs, { cwd: repoRoot, encoding: "utf8", timeout: 900000 });
        if (run.status !== 0) {
          res.statusCode = 500;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "voiceover_failed", stderr: run.stderr, stdout: run.stdout, signal: run.signal }));
          return;
        }
        const narrationPath = path.resolve(workDir, "output", "narration.wav");
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: true, narrationPath, engine: engine || "config" }));
      });
      return;
    }

    if (req.method === "GET" && req.url === "/api/script") {
      try {
        ensureVariantBootstrap();
        const { workDir } = variantContextFromRequest(req, "");
        let scriptPath = path.resolve(workDir, "script.md");
        if (!fs.existsSync(scriptPath)) scriptPath = path.resolve(projectDir, "script.md");
        const text = fs.readFileSync(scriptPath, "utf8");
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ ok: true, text }));
      } catch (err) {
        res.statusCode = 404;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "script_not_found" }));
      }
      return;
    }

    if (req.method === "GET" && req.url === "/api/crop-validation") {
      try {
        ensureVariantBootstrap();
        const { workDir } = variantContextFromRequest(req, "");
        const cropValidationPath = path.resolve(workDir, "output/crop-validation.json");
        const raw = fs.readFileSync(cropValidationPath, "utf8");
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(raw);
      } catch {
        res.statusCode = 404;
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(JSON.stringify({ error: "crop_validation_not_found" }));
      }
      return;
    }

    if (req.method === "POST" && req.url === "/api/script") {
      let body = "";
      req.on("data", (chunk) => (body += chunk.toString("utf8")));
      req.on("end", () => {
        try {
          ensureVariantBootstrap();
          const payload = JSON.parse(body || "{}");
          const text = String(payload.text || "").trim();
          if (!text) throw new Error("missing_script_text");
          const { workDir } = variantContextFromRequest(req, payload.variant_id);
          const scriptPath = path.resolve(workDir, "script.md");
          fs.mkdirSync(workDir, { recursive: true });
          fs.writeFileSync(scriptPath, text + "\n", "utf8");
          const linesPayload = buildScriptLinesFromText(projectDir, text);
          fs.writeFileSync(path.resolve(workDir, "script-lines.json"), JSON.stringify(linesPayload, null, 2) + "\n", "utf8");
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, scriptPath }));
        } catch (err) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "script_save_failed", detail: String(err && err.message ? err.message : err) }));
        }
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/build-from-wiki") {
      let body = "";
      req.on("data", (chunk) => (body += chunk.toString("utf8")));
      req.on("end", () => {
        try {
          const parsed = JSON.parse(body || "{}");
          const title = normalizeWikiTitle(parsed.title || "");
          if (!title) {
            throw new Error("missing_title");
          }
          let graph;
          let warning = "";
          try {
            graph = buildGraphFromWikiTitle(title);
          } catch (err) {
            warning = `wikipedia_unavailable:${String(err && err.message ? err.message : err)}`;
            graph = fallbackGraphForTitle(title);
          }
          fs.mkdirSync(path.dirname(projectPath), { recursive: true });
          fs.writeFileSync(projectPath, JSON.stringify({ nodes: graph.nodes, edges: graph.edges }, null, 2) + "\n", "utf8");
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, project: { nodes: graph.nodes, edges: graph.edges }, meta: graph.meta, warning }));
        } catch (err) {
          res.statusCode = 500;
          res.setHeader("content-type", "application/json; charset=utf-8");
          const detail = String(err && err.message ? err.message : err);
          res.end(JSON.stringify({ error: "wiki_build_failed", detail }));
        }
      });
      return;
    }

    if (req.method === "POST" && req.url === "/api/expand-dag-gemini") {
      let body = "";
      req.on("data", (chunk) => (body += chunk.toString("utf8")));
      req.on("end", () => {
        let payload = {};
        try {
          payload = body ? JSON.parse(body) : {};
        } catch {
          payload = {};
        }
        const title = String(payload.title || "").trim() || "Untitled topic";
        const apiKey = String(getGeminiApiKey() || "").trim();
        if (!apiKey) {
          res.statusCode = 400;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "missing_gemini_api_key" }));
          return;
        }
        const run = spawnSync(
          "node",
          [
            "./dist/planner/src/gemini-expand-dag-cli.js",
            "--project",
            "./projects/walrus-dfs",
            "--api-key",
            apiKey,
            "--title",
            title,
          ],
          { cwd: repoRoot, encoding: "utf8", timeout: 120000 }
        );
        if (run.status !== 0) {
          res.statusCode = 500;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "gemini_expand_failed", detail: run.stderr || run.stdout || run.signal || "unknown" }));
          return;
        }
        try {
          const project = JSON.parse(fs.readFileSync(projectPath, "utf8"));
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ ok: true, project }));
        } catch (err) {
          res.statusCode = 500;
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: "expanded_project_read_failed" }));
        }
      });
      return;
    }

    let p = req.url === "/" ? "/index.html" : req.url;
    p = p.split("?")[0];
    const abs = path.resolve(root, "." + p);
    if (!abs.startsWith(root)) {
      res.statusCode = 403;
      res.end("forbidden");
      return;
    }
    fs.readFile(abs, (err, data) => {
      if (err) {
        res.statusCode = 404;
        res.end("not found");
        return;
      }
      res.setHeader("content-type", mime[path.extname(abs)] || "application/octet-stream");
      res.end(data);
    });
  })
  .listen(port, () => {
    console.log(`AI Director desktop shell: http://localhost:${port}`);
  });

import path from "node:path";
import { readJson, writeJson } from "../../core/src/fs";

type DagNode = {
  id: string;
  title: string;
  tags?: string[];
  importance?: number;
  duration_intent_sec?: number;
};

type DagEdge = { from: string; to: string };
type DagProject = { nodes: DagNode[]; edges: DagEdge[] };

function arg(flag: string): string | undefined {
  const i = process.argv.indexOf(flag);
  if (i < 0 || i + 1 >= process.argv.length) return undefined;
  return process.argv[i + 1];
}

function extractJson(text: string): any {
  const raw = String(text || "").trim();
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const payload = fenced ? fenced[1] : raw;
  return JSON.parse(payload);
}

function safeId(input: string, fallbackIdx: number): string {
  const base = String(input || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return base ? `n_${base}` : `n_auto_${fallbackIdx}`;
}

function normalizeProject(raw: any, seed: DagProject): DagProject {
  const inNodes = Array.isArray(raw?.nodes) ? raw.nodes : [];
  const inEdges = Array.isArray(raw?.edges) ? raw.edges : [];

  const outNodes: DagNode[] = [];
  const seenNode = new Set<string>();
  inNodes.forEach((n: any, idx: number) => {
    const id = safeId(String(n?.id || n?.title || ""), idx + 1);
    if (seenNode.has(id)) return;
    seenNode.add(id);
    outNodes.push({
      id,
      title: String(n?.title || `Concept ${idx + 1}`).trim() || `Concept ${idx + 1}`,
      tags: Array.isArray(n?.tags) ? n.tags.map((x: any) => String(x)).slice(0, 8) : [],
      importance: Number.isFinite(Number(n?.importance)) ? Number(n.importance) : 0.6,
      duration_intent_sec: Number.isFinite(Number(n?.duration_intent_sec)) ? Number(n.duration_intent_sec) : 10,
    });
  });

  const known = new Set(outNodes.map((n) => n.id));
  const outEdges: DagEdge[] = [];
  const seenEdge = new Set<string>();
  inEdges.forEach((e: any) => {
    const from = safeId(String(e?.from || ""), 1);
    const to = safeId(String(e?.to || ""), 2);
    if (!known.has(from) || !known.has(to) || from === to) return;
    const k = `${from}->${to}`;
    if (seenEdge.has(k)) return;
    seenEdge.add(k);
    outEdges.push({ from, to });
  });

  if (outNodes.length === 0) return seed;
  if (outEdges.length === 0 && outNodes.length > 1) {
    for (let i = 1; i < outNodes.length; i++) {
      outEdges.push({ from: outNodes[0].id, to: outNodes[i].id });
    }
  }
  return { nodes: outNodes, edges: outEdges };
}

async function callGeminiExpand(apiKey: string, title: string, seed: DagProject): Promise<DagProject> {
  const prompt = [
    "You are expanding a directed acyclic graph (DAG) for an educational short video.",
    "Return JSON only with keys: nodes, edges.",
    "Respect and expand the existing concepts; keep it acyclic.",
    "Node schema: {id, title, tags, importance, duration_intent_sec}.",
    "Edge schema: {from, to}.",
    "Rules:",
    "- Keep node titles concise.",
    "- Keep importance in range 0.1..1.0.",
    "- Use 8-20 nodes total.",
    "- Keep a coherent learning path from broad to specific.",
    "",
    `Video title/topic: ${title}`,
    `Current DAG: ${JSON.stringify(seed)}`,
  ].join("\n");

  const modelCandidates = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
  ];
  const apiVersions = ["v1beta", "v1"];
  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { responseMimeType: "application/json", temperature: 0.5 },
  };

  const failures: string[] = [];
  for (const version of apiVersions) {
    for (const model of modelCandidates) {
      const url = `https://generativelanguage.googleapis.com/${version}/models/${model}:generateContent?key=${encodeURIComponent(apiKey)}`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errText = await res.text();
        failures.push(`http_${res.status}@${version}:${model}${errText ? `:${errText.slice(0, 120)}` : ""}`);
        continue;
      }
      const payload = await res.json();
      const text = payload?.candidates?.[0]?.content?.parts?.[0]?.text;
      if (!text) {
        failures.push(`empty_response@${version}:${model}`);
        continue;
      }
      return normalizeProject(extractJson(text), seed);
    }
  }
  throw new Error(`gemini_expand_failed ${failures.slice(-6).join(" | ")}`);
}

async function main() {
  const projectDir = path.resolve(arg("--project") || "./projects/walrus-dfs");
  const title = String(arg("--title") || "Untitled topic").trim();
  const apiKey = String(arg("--api-key") || process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || "").trim();
  if (!apiKey) throw new Error("missing_gemini_api_key");
  const dagPath = path.resolve(projectDir, "dag.project.json");
  const seed = readJson<DagProject>(dagPath);
  const expanded = await callGeminiExpand(apiKey, title, seed);
  writeJson(dagPath, expanded);
  console.log("gemini_dag_expanded");
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : String(e));
  process.exit(1);
});

import path from "node:path";
import { readJson, writeJson, writeText } from "../../core/src/fs";
import { cleanForNarration } from "../../subtitles/src/clean-script-text";

type Segment = { segment_id: string; concept: string; target_duration_sec?: number; keywords?: string[] };
type ScriptLine = { segment_id: string; text: string; subtitle_text: string };
type Annotation = { segment_id: string; transition: string; effects: string[]; lut_hint: string; audio_note: string };

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

async function callGemini(apiKey: string, segments: Segment[]): Promise<{ script_lines: ScriptLine[]; annotations: Annotation[] }> {
  const prompt = [
    "You are writing script and edit guidance for an educational wildlife short video.",
    "Return JSON only with keys: script_lines, annotations.",
    "Each script_lines item must include: segment_id, text, subtitle_text.",
    "Each annotations item must include: segment_id, transition, effects (array), lut_hint, audio_note.",
    "Rules:",
    "- Keep subtitles short and readable.",
    "- Keep narration factual and engaging.",
    "- Use varied transitions and effects suggestions.",
    "- audio_note must be exactly 'mute_source_audio_narration_only'.",
    "",
    `Segments: ${JSON.stringify(segments)}`,
  ].join("\n");

  const modelCandidates = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
  ];
  const apiVersions = ["v1beta", "v1"];
  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { responseMimeType: "application/json", temperature: 0.7 },
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
      return extractJson(text);
    }
  }
  throw new Error(`gemini_all_models_failed ${failures.slice(-6).join(" | ")}`);
}

function normalizeLines(segments: Segment[], lines: any[]): ScriptLine[] {
  const byId = new Map((Array.isArray(lines) ? lines : []).map((l: any) => [String(l.segment_id), l]));
  return segments.map((s) => {
    const line = byId.get(s.segment_id) || {};
    const rawText = String(line.text || `${s.concept} explains a key step in walrus evolution.`).trim();
    const rawSub = String(line.subtitle_text || rawText).trim();
    const text = cleanForNarration(rawText) || rawText;
    const subtitle = cleanForNarration(rawSub) || rawSub;
    return { segment_id: s.segment_id, text, subtitle_text: subtitle };
  });
}

function normalizeAnnotations(segments: Segment[], annotations: any[]): Annotation[] {
  const byId = new Map((Array.isArray(annotations) ? annotations : []).map((a: any) => [String(a.segment_id), a]));
  return segments.map((s, i) => {
    const a = byId.get(s.segment_id) || {};
    const transition = String(a.transition || (i === 0 ? "fade_in_12f" : "cross_dissolve_8f"));
    const effects = Array.isArray(a.effects) ? a.effects.map((x: any) => String(x)) : ["subtle_push_in"];
    const lut = String(a.lut_hint || "neutral_doc_rec709");
    return {
      segment_id: s.segment_id,
      transition,
      effects,
      lut_hint: lut,
      audio_note: "mute_source_audio_narration_only",
    };
  });
}

async function main() {
  const projectDir = path.resolve(arg("--project") || "./projects/walrus-dfs");
  const apiKey = String(arg("--api-key") || process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || "").trim();
  if (!apiKey) throw new Error("missing_gemini_api_key");

  const shotPlan = readJson<{ segments: Segment[] }>(path.resolve(projectDir, "shot-plan.json"));
  const segments = Array.isArray(shotPlan.segments) ? shotPlan.segments : [];
  if (segments.length === 0) throw new Error("empty_shot_plan");

  const ai = await callGemini(apiKey, segments);
  const scriptLines = normalizeLines(segments, ai.script_lines);
  const annotations = normalizeAnnotations(segments, ai.annotations);

  writeJson(path.resolve(projectDir, "script-lines.json"), {
    generated_at: new Date().toISOString(),
    source: "gemini",
    lines: scriptLines,
  });
  writeJson(path.resolve(projectDir, "edit-annotations.json"), {
    generated_at: new Date().toISOString(),
    source: "gemini",
    annotations,
  });
  const scriptMd = ["# Walrus DFS Script", ""].concat(scriptLines.map((s) => `## ${s.segment_id}\n${s.text}\n`)).join("\n");
  writeText(path.resolve(projectDir, "script.md"), scriptMd);
  console.log("gemini_script_generated");
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : String(e));
  process.exit(1);
});

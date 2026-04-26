/**
 * Strip markdown / social-style markers so TTS and on-screen subtitles stay natural.
 * Mirrors `packages/pipeline/src-py/clean_script_text.py` — keep behavior in sync.
 */
export function cleanForNarration(raw: string): string {
  let s = String(raw || "").trim();
  if (!s) return "";

  // Line-leading markdown headings (# … ######)
  s = s.replace(/^#{1,6}\s+/gm, "");
  s = s.replace(/\n#{1,6}\s+/g, "\n");

  // Markdown links [label](url) -> label
  s = s.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");

  // Social-style #word (not hex colors) -> word
  s = s.replace(/(^|[\s([{<'"])#([A-Za-z][A-Za-z0-9_-]*)/g, "$1$2");

  // Spoken filler if models emit it literally
  s = s.replace(/\bhashtag\b/gi, "");

  // Bold / italic / code
  s = s.replace(/\*\*([^*]+)\*\*/g, "$1");
  s = s.replace(/\*([^*]+)\*/g, "$1");
  s = s.replace(/__([^_]+)__/g, "$1");
  s = s.replace(/`([^`]+)`/g, "$1");

  // Horizontal rule lines
  s = s.replace(/^-{3,}\s*$/gm, "");

  s = s.replace(/\s+/g, " ").trim();
  return s;
}

/** Drop script.md scaffolding rows that were accidentally stored as `script-lines` entries. */
export function isSkippableScriptLine(raw: string): boolean {
  const s = String(raw || "").trim();
  if (!s) return true;
  if (/^#{1,6}\s*seg_\d+\s*$/i.test(s)) return true;
  if (/^#{1,6}\s*walrus/i.test(s) && /script/i.test(s)) return true;
  const c = cleanForNarration(s);
  if (/^seg_\d+$/i.test(c)) return true;
  // Short fragments without sentence punctuation (headings, crumbs).
  if (c.length < 22 && !/[.!?]/.test(c)) return true;
  return false;
}

function hardWrapAtWords(s: string, maxChars: number): string[] {
  const t = s.trim();
  if (!t) return [];
  if (t.length <= maxChars) return [t];
  const out: string[] = [];
  let rest = t;
  while (rest.length > maxChars) {
    let cut = rest.lastIndexOf(" ", maxChars);
    if (cut < Math.floor(maxChars * 0.45)) cut = maxChars;
    const piece = rest.slice(0, cut).trim();
    if (piece) out.push(piece);
    rest = rest.slice(cut).trim();
  }
  if (rest) out.push(rest);
  return out;
}

export function splitIntoSubtitleCues(
  paragraph: string,
  opts: { maxChars: number; minChars: number }
): string[] {
  const cleaned = cleanForNarration(paragraph);
  if (!cleaned) return [];

  // Primary split: sentence boundaries
  let parts = cleaned.split(/(?<=[.!?])\s+/).map((p) => p.trim()).filter(Boolean);

  // Secondary: break long chunks on comma/semicolon or hard max length
  const out: string[] = [];
  for (const p of parts) {
    if (p.length <= opts.maxChars) {
      out.push(p);
      continue;
    }
    const soft = p.split(/(?<=[,;:])\s+/).map((x) => x.trim()).filter(Boolean);
    let buf = "";
    for (const chunk of soft) {
      if (!buf) {
        buf = chunk;
        continue;
      }
      if (buf.length + 1 + chunk.length <= opts.maxChars) {
        buf += " " + chunk;
      } else {
        if (buf.length >= opts.minChars) out.push(buf);
        buf = chunk;
      }
    }
    if (buf) {
      if (buf.length <= opts.maxChars) {
        out.push(buf);
      } else {
        out.push(...hardWrapAtWords(buf, opts.maxChars));
      }
    }
  }

  return out.length ? out : [cleaned];
}

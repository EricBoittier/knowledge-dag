import { spawnSync } from "node:child_process";
import { MediaCandidate, MediaSource, SegmentPlan } from "../../core/src/types";

export interface DiscoveryConfig {
  sources: MediaSource[];
  prefer_sources: MediaSource[];
  results_per_segment: number;
  selected_per_segment: number;
  min_duration_sec: number;
  max_duration_sec: number;
  allow_unknown_duration: boolean;
}

export interface DiscoveryContext {
  projectTerms: string[];
  segmentTermsById: Record<string, string[]>;
}

function parseDurationToSec(durationText: string | null | undefined): number {
  if (!durationText) return -1;
  const parts = durationText.split(":").map(Number);
  if (parts.some(Number.isNaN)) return -1;
  let out = 0;
  for (const p of parts) out = out * 60 + p;
  return out;
}

function parseFileSizeBytes(value: unknown): number | undefined {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.round(n);
}

function durationOk(sec: number, cfg: DiscoveryConfig): boolean {
  if (sec < 0) return cfg.allow_unknown_duration;
  return sec >= cfg.min_duration_sec && sec <= cfg.max_duration_sec;
}

function prefWeight(source: MediaSource, cfg: DiscoveryConfig): number {
  const i = cfg.prefer_sources.indexOf(source);
  return i < 0 ? 0 : Math.max(1, cfg.prefer_sources.length - i);
}

function tokenize(text: string): string[] {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 3);
}

function overlapScore(candidateText: string, terms: string[]): number {
  const pool = new Set(tokenize(candidateText));
  if (pool.size === 0 || terms.length === 0) return 0;
  let hits = 0;
  for (const term of terms) {
    const t = String(term || "").toLowerCase().trim();
    if (!t) continue;
    if (pool.has(t)) hits += 1;
  }
  return hits / Math.max(1, Math.min(12, terms.length));
}

/** Keywords derived from segment concept + query + keywords (substring match in title). */
function segmentSearchTerms(seg: SegmentPlan): string[] {
  const out = new Set<string>();
  const add = (s: string) => {
    for (const t of tokenize(s)) {
      if (t.length >= 4) out.add(t);
    }
  };
  add(seg.concept);
  add(seg.query);
  for (const k of seg.keywords || []) add(String(k));
  return Array.from(out);
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Match a search term in a title without substring false positives
 * (e.g. "animal" inside "Animalia", "land" inside "island", "earth" inside "earthquake").
 */
function termMatchesInTitle(term: string, hay: string): boolean {
  const t = term.toLowerCase();
  if (!t) return false;
  if (t.length >= 10) return hay.includes(t);
  try {
    return new RegExp(`\\b${escapeRegExp(t)}\\b`, "i").test(hay);
  } catch {
    return hay.includes(t);
  }
}

/** Count of segment terms matching the candidate title (word-aware for short terms). */
function titleKeywordHits(seg: SegmentPlan, title: string): number {
  const hay = String(title || "").toLowerCase();
  const terms = segmentSearchTerms(seg);
  let n = 0;
  for (const term of terms) {
    if (termMatchesInTitle(term, hay)) n += 1;
  }
  return n;
}

const disasterTitleRe =
  /\b(earthquake|magnitude|richter|epicenter|aftershock|seismic|tsunami|tectonic\b|volcanic\s+eruption|san\s+francisco\s+1906|1906\s+earthquake)\b/i;

function segmentWantsDisasterFootage(seg: SegmentPlan): boolean {
  const blob = [seg.concept, seg.query, ...(seg.keywords || [])].join(" ").toLowerCase();
  return /\b(earthquake|seismic|tsunami|tectonic|volcano|eruption|disaster|aftershock|richter|epicenter)\b/i.test(blob);
}

function finalizeRankedCandidates(
  seg: SegmentPlan,
  cfg: DiscoveryConfig,
  merged: MediaCandidate[],
  context?: DiscoveryContext
): MediaCandidate[] {
  const seen = new Set<string>();
  const unique = merged.filter((c) => {
    const key = `${c.source}|${c.source_id}|${c.title.toLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const hitsList = unique.map((c) => titleKeywordHits(seg, c.title));
  const maxHits = hitsList.length ? Math.max(...hitsList) : 0;
  // Drop off-topic archive/commons hits when we have clearly on-topic matches elsewhere.
  let filtered = unique;
  if (maxHits >= 1) {
    const anyYouTubeWithHits = unique.some((c) => c.source === "youtube" && titleKeywordHits(seg, c.title) > 0);
    filtered = unique.filter((c) => {
      const h = titleKeywordHits(seg, c.title);
      if (h > 0) return true;
      // Keep zero-hit YouTube only when no on-topic YouTube exists (search was noisy for everyone).
      if (c.source === "youtube" && !anyYouTubeWithHits) return true;
      return false;
    });
  }

  if (!segmentWantsDisasterFootage(seg)) {
    const withoutDisaster = filtered.filter((c) => !disasterTitleRe.test(c.title));
    if (withoutDisaster.length > 0) filtered = withoutDisaster;
  }

  const segTerms = context?.segmentTermsById?.[seg.segment_id] || [
    ...tokenize(seg.concept),
    ...(seg.keywords || []).flatMap((k) => tokenize(String(k))),
  ];
  const projectTerms = context?.projectTerms || [];

  return filtered
    .map((c) => {
      const text = `${c.title} ${c.creator} ${c.attribution || ""}`;
      const kwHits = titleKeywordHits(seg, c.title);
      const segmentFit = overlapScore(text, segTerms) * 1.2;
      const projectFit = overlapScore(text, projectTerms) * 0.6;
      const boost = Number((segmentFit + projectFit + kwHits * 0.65).toFixed(4));
      return { ...c, score: score(c, cfg, boost) };
    })
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return titleKeywordHits(seg, b.title) - titleKeywordHits(seg, a.title);
    });
}

function score(c: MediaCandidate, cfg: DiscoveryConfig, termBoost: number): number {
  const durationPenalty = c.duration_sec < 0 ? 0.2 : Math.abs(c.duration_sec - 20) / 100;
  return Number((prefWeight(c.source, cfg) + Math.max(0, 1 - durationPenalty) + termBoost).toFixed(4));
}

function searchYouTube(seg: SegmentPlan, cfg: DiscoveryConfig): MediaCandidate[] {
  const searchSpec = `ytsearch${cfg.results_per_segment}:${seg.query}`;
  const proc = spawnSync("yt-dlp", ["--dump-json", "--flat-playlist", "--no-warnings", searchSpec], {
    encoding: "utf8",
    timeout: 12000,
  });
  if (proc.status !== 0) return [];
  const items = proc.stdout
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    })
    .filter(Boolean);
  return items
    .map((item: any) => {
      const duration = Number(item.duration) || parseDurationToSec(item.duration_string);
      const id = String(item.id || "");
      return {
        segment_id: seg.segment_id,
        source: "youtube" as const,
        source_id: id,
        title: String(item.title || ""),
        url: id ? `https://www.youtube.com/watch?v=${id}` : "",
        creator: String(item.channel || item.uploader || "YouTube"),
        duration_sec: duration,
        thumbnail_url: String(item.thumbnail || ""),
        filesize_bytes: parseFileSizeBytes(item.filesize) ?? parseFileSizeBytes(item.filesize_approx),
        license: "platform",
        attribution: String(item.channel || item.uploader || "YouTube"),
        score: 0,
      };
    })
    .filter((c) => c.source_id && c.title && durationOk(c.duration_sec, cfg));
}

function searchYouTubeFallback(seg: SegmentPlan, cfg: DiscoveryConfig): MediaCandidate[] {
  const queries = [seg.concept, `${seg.concept} documentary`, `${seg.concept} explained`]
    .map((q) => q.trim())
    .filter((q) => q.length > 0);
  const merged: MediaCandidate[] = [];
  const seen = new Set<string>();
  for (const q of queries) {
    const found = searchYouTube({ ...seg, query: q }, cfg);
    for (const c of found) {
      const key = `${c.source}|${c.source_id}|${c.title.toLowerCase()}`;
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(c);
    }
    if (merged.length >= Math.max(cfg.results_per_segment, 4)) {
      break;
    }
  }
  return merged;
}

function searchWikimediaStills(seg: SegmentPlan, cfg: DiscoveryConfig): MediaCandidate[] {
  const query = encodeURIComponent(`${seg.query} filetype:bitmap`);
  const limit = Math.min(Math.max(4, cfg.results_per_segment), 12);
  const url =
    `https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch=${query}` +
    `&gsrnamespace=6&gsrlimit=${limit}&prop=imageinfo&iiprop=url|mime|thumburl|extmetadata&iiurlwidth=320&format=json`;
  const proc = spawnSync(
    "python3",
    ["-c", "import urllib.request,sys;print(urllib.request.urlopen(sys.argv[1], timeout=8).read().decode('utf-8'))", url],
    { encoding: "utf8", timeout: 10000 }
  );
  if ((proc as any).error || proc.signal === "SIGTERM") return [];
  if (proc.status !== 0) return [];
  let payload: any = {};
  try { payload = JSON.parse(proc.stdout); } catch { return []; }
  const pages = Object.values(payload?.query?.pages ?? {}) as any[];
  const out: MediaCandidate[] = [];
  for (const p of pages) {
    const info = p?.imageinfo?.[0] ?? {};
    const meta = info?.extmetadata ?? {};
    const mime = String(info?.mime || "").toLowerCase();
    if (!mime.startsWith("image/") || mime.includes("svg")) continue;
    const c: MediaCandidate = {
      segment_id: seg.segment_id,
      source: "wikimedia",
      source_id: String(p?.pageid ?? ""),
      title: String(p?.title || "").replace(/^File:/, ""),
      url: String(info?.url || ""),
      creator: String(meta?.Artist?.value || "Wikimedia Commons"),
      duration_sec: -1,
      thumbnail_url: String(info?.thumburl || info?.url || ""),
      license: String(meta?.LicenseShortName?.value || "commons"),
      attribution: String(meta?.Attribution?.value || meta?.Artist?.value || "Wikimedia Commons"),
      score: 0,
      is_image: true,
      mime_type: mime,
    };
    if (c.source_id && c.url && c.title && durationOk(c.duration_sec, cfg)) out.push(c);
  }
  return out;
}

function searchWikimedia(seg: SegmentPlan, cfg: DiscoveryConfig): MediaCandidate[] {
  const query = encodeURIComponent(`${seg.query} filetype:video`);
  const url =
    `https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch=${query}` +
    `&gsrnamespace=6&gsrlimit=${cfg.results_per_segment}&prop=imageinfo&iiprop=url|extmetadata&format=json`;
  const proc = spawnSync(
    "python3",
    ["-c", "import urllib.request,sys;print(urllib.request.urlopen(sys.argv[1], timeout=8).read().decode('utf-8'))", url],
    { encoding: "utf8", timeout: 10000 }
  );
  if ((proc as any).error || proc.signal === "SIGTERM") return [];
  if (proc.status !== 0) return [];
  let payload: any = {};
  try { payload = JSON.parse(proc.stdout); } catch { return []; }
  const pages = Object.values(payload?.query?.pages ?? {}) as any[];
  return pages
    .map((p) => {
      const info = p?.imageinfo?.[0] ?? {};
      const meta = info?.extmetadata ?? {};
      const duration = Number(meta?.Duration?.value ?? -1);
      return {
        segment_id: seg.segment_id,
        source: "wikimedia" as const,
        source_id: String(p?.pageid ?? ""),
        title: String(p?.title || "").replace(/^File:/, ""),
        url: String(info?.url || ""),
        creator: String(meta?.Artist?.value || "Wikimedia Commons"),
        duration_sec: Number.isFinite(duration) ? duration : -1,
        license: String(meta?.LicenseShortName?.value || "commons"),
        attribution: String(meta?.Attribution?.value || meta?.Artist?.value || "Wikimedia Commons"),
        score: 0,
      };
    })
    .filter((c) => c.source_id && c.url && c.title && durationOk(c.duration_sec, cfg));
}

function searchArchive(seg: SegmentPlan, cfg: DiscoveryConfig): MediaCandidate[] {
  const query = encodeURIComponent(`${seg.query} AND mediatype:movies`);
  const url =
    `https://archive.org/advancedsearch.php?q=${query}` +
    `&fl[]=identifier,title,creator,licenseurl,length&rows=${cfg.results_per_segment}&page=1&output=json`;
  const proc = spawnSync(
    "python3",
    ["-c", "import urllib.request,sys;print(urllib.request.urlopen(sys.argv[1], timeout=8).read().decode('utf-8'))", url],
    { encoding: "utf8", timeout: 10000 }
  );
  if ((proc as any).error || proc.signal === "SIGTERM") return [];
  if (proc.status !== 0) return [];
  let payload: any = {};
  try { payload = JSON.parse(proc.stdout); } catch { return []; }
  return (payload?.response?.docs ?? [])
    .map((d: any) => {
      const id = String(d?.identifier || "");
      const duration = Number(d?.length || -1);
      return {
        segment_id: seg.segment_id,
        source: "internet_archive" as const,
        source_id: id,
        title: String(d?.title || id),
        url: id ? `https://archive.org/details/${id}` : "",
        creator: String(d?.creator || "Internet Archive"),
        duration_sec: Number.isFinite(duration) ? duration : -1,
        license: String(d?.licenseurl || "archive"),
        attribution: String(d?.creator || "Internet Archive"),
        score: 0,
      };
    })
    .filter((c: MediaCandidate) => c.source_id && c.url && c.title && durationOk(c.duration_sec, cfg));
}

export function discoverForSegment(seg: SegmentPlan, cfg: DiscoveryConfig): MediaCandidate[] {
  const merged: MediaCandidate[] = [];
  if (cfg.sources.includes("youtube")) {
    const yt = searchYouTube(seg, cfg);
    merged.push(...yt);
    if (yt.length === 0) {
      merged.push(...searchYouTubeFallback(seg, cfg));
    }
  }
  if (cfg.sources.includes("wikimedia")) {
    merged.push(...searchWikimedia(seg, cfg));
    merged.push(...searchWikimediaStills(seg, cfg));
  }
  if (cfg.sources.includes("internet_archive")) merged.push(...searchArchive(seg, cfg));

  return finalizeRankedCandidates(seg, cfg, merged, undefined);
}

export function discoverForSegmentWithContext(
  seg: SegmentPlan,
  cfg: DiscoveryConfig,
  context: DiscoveryContext
): MediaCandidate[] {
  const merged: MediaCandidate[] = [];
  if (cfg.sources.includes("youtube")) {
    const yt = searchYouTube(seg, cfg);
    merged.push(...yt);
    if (yt.length === 0) {
      merged.push(...searchYouTubeFallback(seg, cfg));
    }
  }
  if (cfg.sources.includes("wikimedia")) {
    merged.push(...searchWikimedia(seg, cfg));
    merged.push(...searchWikimediaStills(seg, cfg));
  }
  if (cfg.sources.includes("internet_archive")) merged.push(...searchArchive(seg, cfg));

  return finalizeRankedCandidates(seg, cfg, merged, context);
}

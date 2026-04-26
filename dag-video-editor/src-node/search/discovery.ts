import { spawnSync } from "node:child_process";
import { PipelineConfig } from "../config";
import { MediaCandidate, MediaSource, ShotSegment } from "../types";

function parseDurationToSec(durationText: string | null | undefined): number {
  if (!durationText) {
    return -1;
  }
  const parts = durationText.split(":").map((x) => Number(x));
  if (parts.some((n) => Number.isNaN(n))) {
    return -1;
  }
  let sec = 0;
  for (const p of parts) {
    sec = sec * 60 + p;
  }
  return sec;
}

function keepDuration(durationSec: number, cfg: PipelineConfig): boolean {
  if (durationSec < 0) {
    return cfg.discovery.allow_unknown_duration;
  }
  return durationSec <= cfg.youtube.max_duration_sec && durationSec >= cfg.youtube.min_duration_sec;
}

function sourceWeight(source: MediaSource, cfg: PipelineConfig): number {
  const idx = cfg.discovery.prefer_sources.indexOf(source);
  if (idx < 0) {
    return 0;
  }
  return Math.max(1, cfg.discovery.prefer_sources.length - idx);
}

function rankCandidates(cands: MediaCandidate[], cfg: PipelineConfig): MediaCandidate[] {
  return cands
    .map((c) => {
      const durationPenalty = c.duration_sec < 0 ? 0.15 : Math.abs(c.duration_sec - 20) / 100;
      const score = sourceWeight(c.source, cfg) + Math.max(0, 1 - durationPenalty);
      return { ...c, score: Number(score.toFixed(4)) };
    })
    .sort((a, b) => b.score - a.score);
}

function searchYouTube(seg: ShotSegment, cfg: PipelineConfig): MediaCandidate[] {
  if (!cfg.discovery.sources.includes("youtube")) {
    return [];
  }
  const searchSpec = `ytsearch${cfg.youtube.results_per_segment}:${seg.query}`;
  const proc = spawnSync("yt-dlp", ["--dump-json", "--flat-playlist", "--no-warnings", searchSpec], { encoding: "utf8" });
  if (proc.status !== 0) {
    return [];
  }
  const lines = proc.stdout
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const items: any[] = lines
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter((x) => x !== null);

  return items
    .map((item) => {
      const id: string = item.id || item.url || "";
      const durationSec = Number(item.duration) || parseDurationToSec(item.duration_string);
      return {
        segment_id: seg.segment_id,
        concept: seg.concept,
        query: seg.query,
        source: "youtube" as const,
        source_id: id,
        title: item.title || "",
        url: id ? `https://www.youtube.com/watch?v=${id}` : "",
        creator: item.channel || item.uploader || "",
        duration_sec: durationSec,
        license: "platform",
        attribution: item.channel || item.uploader || "",
        score: 0,
      } satisfies MediaCandidate;
    })
    .filter((c) => c.source_id && c.title && keepDuration(c.duration_sec, cfg));
}

function searchYouTubeFallback(seg: ShotSegment, cfg: PipelineConfig): MediaCandidate[] {
  if (!cfg.discovery.sources.includes("youtube")) {
    return [];
  }
  const queries = [seg.concept, `${seg.concept} documentary`, `${seg.concept} explained`]
    .map((q) => q.trim())
    .filter((q) => q.length > 0);
  const merged: MediaCandidate[] = [];
  const seen = new Set<string>();
  for (const q of queries) {
    const tmpSeg: ShotSegment = { ...seg, query: q };
    const found = searchYouTube(tmpSeg, cfg);
    for (const c of found) {
      const key = `${c.source}|${c.source_id}|${c.title.toLowerCase()}`;
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(c);
    }
    if (merged.length >= Math.max(cfg.youtube.results_per_segment, 4)) {
      break;
    }
  }
  return merged;
}

function searchWikimedia(seg: ShotSegment, cfg: PipelineConfig): MediaCandidate[] {
  if (!cfg.discovery.sources.includes("wikimedia")) {
    return [];
  }
  const query = encodeURIComponent(`${seg.query} filetype:video`);
  const url =
    `https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch=${query}` +
    `&gsrnamespace=6&gsrlimit=${cfg.youtube.results_per_segment}&prop=imageinfo&iiprop=url|extmetadata&format=json`;
  const proc = spawnSync("python3", ["-c", "import json,sys,urllib.request;print(urllib.request.urlopen(sys.argv[1]).read().decode('utf-8'))", url], {
    encoding: "utf8",
  });
  if (proc.status !== 0) {
    return [];
  }
  let payload: any = {};
  try {
    payload = JSON.parse(proc.stdout);
  } catch {
    return [];
  }
  const pages = Object.values(payload?.query?.pages ?? {}) as any[];
  return pages
    .map((p) => {
      const info = p?.imageinfo?.[0] ?? {};
      const meta = info?.extmetadata ?? {};
      const title = String(p?.title || "").replace(/^File:/, "");
      const durationSec = parseFloat(String(meta?.Duration?.value || "-1"));
      const fileUrl = info?.url || "";
      return {
        segment_id: seg.segment_id,
        concept: seg.concept,
        query: seg.query,
        source: "wikimedia" as const,
        source_id: String(p?.pageid || ""),
        title,
        url: fileUrl,
        creator: String(meta?.Artist?.value || "Wikimedia Commons"),
        duration_sec: Number.isFinite(durationSec) ? durationSec : -1,
        license: String(meta?.LicenseShortName?.value || "commons"),
        attribution: String(meta?.Attribution?.value || meta?.Artist?.value || "Wikimedia Commons"),
        score: 0,
      } satisfies MediaCandidate;
    })
    .filter((c) => c.url && c.title && keepDuration(c.duration_sec, cfg));
}

function searchInternetArchive(seg: ShotSegment, cfg: PipelineConfig): MediaCandidate[] {
  if (!cfg.discovery.sources.includes("internet_archive")) {
    return [];
  }
  const query = encodeURIComponent(`${seg.query} AND mediatype:movies`);
  const url =
    `https://archive.org/advancedsearch.php?q=${query}` +
    `&fl[]=identifier,title,creator,licenseurl,length&rows=${cfg.youtube.results_per_segment}&page=1&output=json`;
  const proc = spawnSync("python3", ["-c", "import json,sys,urllib.request;print(urllib.request.urlopen(sys.argv[1]).read().decode('utf-8'))", url], {
    encoding: "utf8",
  });
  if (proc.status !== 0) {
    return [];
  }
  let payload: any = {};
  try {
    payload = JSON.parse(proc.stdout);
  } catch {
    return [];
  }
  const docs = payload?.response?.docs ?? [];
  return docs
    .map((d: any) => {
      const id = String(d?.identifier || "");
      const durationSec = Number(d?.length || -1);
      return {
        segment_id: seg.segment_id,
        concept: seg.concept,
        query: seg.query,
        source: "internet_archive" as const,
        source_id: id,
        title: String(d?.title || id),
        url: id ? `https://archive.org/details/${id}` : "",
        creator: String(d?.creator || "Internet Archive"),
        duration_sec: Number.isFinite(durationSec) ? durationSec : -1,
        license: String(d?.licenseurl || "archive"),
        attribution: String(d?.creator || "Internet Archive"),
        score: 0,
      } satisfies MediaCandidate;
    })
    .filter((c: MediaCandidate) => c.url && c.title && keepDuration(c.duration_sec, cfg));
}

export function discoverCandidates(seg: ShotSegment, cfg: PipelineConfig): MediaCandidate[] {
  const ytPrimary = searchYouTube(seg, cfg);
  const ytFallback = ytPrimary.length > 0 ? [] : searchYouTubeFallback(seg, cfg);
  const merged = [...searchWikimedia(seg, cfg), ...searchInternetArchive(seg, cfg), ...ytPrimary, ...ytFallback];
  const dedupe = new Set<string>();
  const unique: MediaCandidate[] = [];
  for (const c of merged) {
    const key = `${c.source}|${c.source_id}|${c.title.toLowerCase()}`;
    if (dedupe.has(key)) {
      continue;
    }
    dedupe.add(key);
    unique.push(c);
  }
  return rankCandidates(unique, cfg);
}

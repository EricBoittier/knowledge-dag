"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.discoverCandidates = discoverCandidates;
const node_child_process_1 = require("node:child_process");
function parseDurationToSec(durationText) {
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
function keepDuration(durationSec, cfg) {
    if (durationSec < 0) {
        return cfg.discovery.allow_unknown_duration;
    }
    return durationSec <= cfg.youtube.max_duration_sec && durationSec >= cfg.youtube.min_duration_sec;
}
function sourceWeight(source, cfg) {
    const idx = cfg.discovery.prefer_sources.indexOf(source);
    if (idx < 0) {
        return 0;
    }
    return Math.max(1, cfg.discovery.prefer_sources.length - idx);
}
function rankCandidates(cands, cfg) {
    return cands
        .map((c) => {
        const durationPenalty = c.duration_sec < 0 ? 0.15 : Math.abs(c.duration_sec - 20) / 100;
        const score = sourceWeight(c.source, cfg) + Math.max(0, 1 - durationPenalty);
        return { ...c, score: Number(score.toFixed(4)) };
    })
        .sort((a, b) => b.score - a.score);
}
function searchYouTube(seg, cfg) {
    if (!cfg.discovery.sources.includes("youtube")) {
        return [];
    }
    const searchSpec = `ytsearch${cfg.youtube.results_per_segment}:${seg.query}`;
    const proc = (0, node_child_process_1.spawnSync)("yt-dlp", ["--dump-json", "--flat-playlist", "--no-warnings", searchSpec], { encoding: "utf8" });
    if (proc.status !== 0) {
        return [];
    }
    const lines = proc.stdout
        .split("\n")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
    const items = lines
        .map((line) => {
        try {
            return JSON.parse(line);
        }
        catch {
            return null;
        }
    })
        .filter((x) => x !== null);
    return items
        .map((item) => {
        const id = item.id || item.url || "";
        const durationSec = Number(item.duration) || parseDurationToSec(item.duration_string);
        return {
            segment_id: seg.segment_id,
            concept: seg.concept,
            query: seg.query,
            source: "youtube",
            source_id: id,
            title: item.title || "",
            url: id ? `https://www.youtube.com/watch?v=${id}` : "",
            creator: item.channel || item.uploader || "",
            duration_sec: durationSec,
            license: "platform",
            attribution: item.channel || item.uploader || "",
            score: 0,
        };
    })
        .filter((c) => c.source_id && c.title && keepDuration(c.duration_sec, cfg));
}
function searchWikimedia(seg, cfg) {
    if (!cfg.discovery.sources.includes("wikimedia")) {
        return [];
    }
    const query = encodeURIComponent(`${seg.query} filetype:video`);
    const url = `https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch=${query}` +
        `&gsrnamespace=6&gsrlimit=${cfg.youtube.results_per_segment}&prop=imageinfo&iiprop=url|extmetadata&format=json`;
    const proc = (0, node_child_process_1.spawnSync)("python3", ["-c", "import json,sys,urllib.request;print(urllib.request.urlopen(sys.argv[1]).read().decode('utf-8'))", url], {
        encoding: "utf8",
    });
    if (proc.status !== 0) {
        return [];
    }
    let payload = {};
    try {
        payload = JSON.parse(proc.stdout);
    }
    catch {
        return [];
    }
    const pages = Object.values(payload?.query?.pages ?? {});
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
            source: "wikimedia",
            source_id: String(p?.pageid || ""),
            title,
            url: fileUrl,
            creator: String(meta?.Artist?.value || "Wikimedia Commons"),
            duration_sec: Number.isFinite(durationSec) ? durationSec : -1,
            license: String(meta?.LicenseShortName?.value || "commons"),
            attribution: String(meta?.Attribution?.value || meta?.Artist?.value || "Wikimedia Commons"),
            score: 0,
        };
    })
        .filter((c) => c.url && c.title && keepDuration(c.duration_sec, cfg));
}
function searchInternetArchive(seg, cfg) {
    if (!cfg.discovery.sources.includes("internet_archive")) {
        return [];
    }
    const query = encodeURIComponent(`${seg.query} AND mediatype:movies`);
    const url = `https://archive.org/advancedsearch.php?q=${query}` +
        `&fl[]=identifier,title,creator,licenseurl,length&rows=${cfg.youtube.results_per_segment}&page=1&output=json`;
    const proc = (0, node_child_process_1.spawnSync)("python3", ["-c", "import json,sys,urllib.request;print(urllib.request.urlopen(sys.argv[1]).read().decode('utf-8'))", url], {
        encoding: "utf8",
    });
    if (proc.status !== 0) {
        return [];
    }
    let payload = {};
    try {
        payload = JSON.parse(proc.stdout);
    }
    catch {
        return [];
    }
    const docs = payload?.response?.docs ?? [];
    return docs
        .map((d) => {
        const id = String(d?.identifier || "");
        const durationSec = Number(d?.length || -1);
        return {
            segment_id: seg.segment_id,
            concept: seg.concept,
            query: seg.query,
            source: "internet_archive",
            source_id: id,
            title: String(d?.title || id),
            url: id ? `https://archive.org/details/${id}` : "",
            creator: String(d?.creator || "Internet Archive"),
            duration_sec: Number.isFinite(durationSec) ? durationSec : -1,
            license: String(d?.licenseurl || "archive"),
            attribution: String(d?.creator || "Internet Archive"),
            score: 0,
        };
    })
        .filter((c) => c.url && c.title && keepDuration(c.duration_sec, cfg));
}
function discoverCandidates(seg, cfg) {
    const merged = [...searchWikimedia(seg, cfg), ...searchInternetArchive(seg, cfg), ...searchYouTube(seg, cfg)];
    const dedupe = new Set();
    const unique = [];
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

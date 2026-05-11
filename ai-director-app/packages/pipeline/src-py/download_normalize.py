#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from broll_analyzer import analyze_video_for_broll, default_analysis, load_analyzer_config

MAX_VIDEO_DURATION_SECONDS = 10 * 60


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def safe_stem(name: str) -> str:
    txt = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    txt = re.sub(r"[^A-Za-z0-9._-]+", "_", txt).strip("._-")
    if not txt:
        txt = "clip"
    return f"{txt[:72]}_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr}")


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return 0.0
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def coerce_duration(value: object) -> float:
    try:
        d = float(value)
    except (TypeError, ValueError):
        return 0.0
    return d if d > 0 else 0.0


def _tokenize(text: str) -> list[str]:
    s = re.sub(r"[^a-z0-9\s]+", " ", str(text or "").lower())
    return [t for t in s.split() if len(t) >= 4]


def _term_matches_in_title(term: str, hay: str) -> bool:
    """Word-aware for short terms so 'animal' does not match inside 'animalia', etc."""
    t = str(term or "").lower()
    if not t:
        return False
    if len(t) >= 10:
        return t in hay
    try:
        return re.search(r"\b" + re.escape(t) + r"\b", hay, flags=re.I) is not None
    except re.error:
        return t in hay


def title_keyword_hits(concept: str, query: str, keywords: list, title: str) -> int:
    hay = str(title or "").lower()
    terms = set(_tokenize(concept) + _tokenize(query))
    for k in keywords or []:
        terms.update(_tokenize(str(k)))
    return sum(1 for term in terms if _term_matches_in_title(term, hay))


_DISASTER_TITLE = re.compile(
    r"\b(earthquake|magnitude|richter|epicenter|aftershock|seismic|tsunami|tectonic\b|volcanic\s+eruption|san\s+francisco\s+1906|1906\s+earthquake)\b",
    re.I,
)


def _segment_wants_disaster(concept: str, query: str, keywords: list) -> bool:
    blob = f"{concept} {query} {' '.join(str(k) for k in (keywords or []))}".lower()
    return bool(
        re.search(
            r"\b(earthquake|seismic|tsunami|tectonic|volcano|eruption|disaster|aftershock|richter|epicenter)\b",
            blob,
        )
    )


def source_priority(src: str) -> int:
    return {"youtube": 0, "wikimedia": 1, "internet_archive": 2}.get(str(src or ""), 3)


def resolve_media_dir(config_value: str, env_name: str) -> Path:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(config_value).expanduser().resolve()


def ensure_min_free_space(target_dir: Path) -> None:
    min_free_gb_raw = os.getenv("VIDEO_MIN_FREE_GB", "25").strip()
    try:
        min_free_gb = float(min_free_gb_raw)
    except ValueError as ex:
        raise RuntimeError(f"Invalid VIDEO_MIN_FREE_GB value: {min_free_gb_raw}") from ex
    if min_free_gb <= 0:
        return
    usage = shutil.disk_usage(target_dir)
    free_gb = usage.free / (1024**3)
    if free_gb < min_free_gb:
        raise RuntimeError(
            f"Not enough free space at {target_dir} "
            f"({free_gb:.1f} GB free, require at least {min_free_gb:.1f} GB). "
            "Set VIDEO_DOWNLOAD_DIR to an external drive with more space."
        )


def download_video_with_fallback(url: str, out_tpl: Path, source: str) -> None:
    base = ["yt-dlp", "--no-playlist", "--socket-timeout", "30", "--retries", "4", "--fragment-retries", "4", "-o", str(out_tpl)]
    attempts: list[list[str]]
    if source == "youtube":
        attempts = [
            [*base, "--force-ipv4", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", url],
            [*base, "--force-ipv4", "-f", "b", url],
            [*base, "--force-ipv4", url],
        ]
    else:
        attempts = [[*base, url]]
    last_err = ""
    for cmd in attempts:
        try:
            run(cmd)
            return
        except RuntimeError as ex:
            last_err = str(ex)
            continue
    raise RuntimeError(f"yt-dlp failed after fallback attempts: {last_err[:220]}")


def sort_clips_for_segment(seg: dict, clips: list, shot_meta: dict) -> list:
    sid = seg.get("segment_id")
    meta = shot_meta.get(sid, {})
    concept = str(meta.get("concept") or seg.get("concept") or "")
    query = str(meta.get("query") or "")
    keywords = meta.get("keywords") or []
    wants_disaster = _segment_wants_disaster(concept, query, keywords)

    def key(c: dict):
        title = str(c.get("title") or "")
        hits = title_keyword_hits(concept, query, keywords, title)
        sc = float(c.get("score") or 0)
        disaster = bool(_DISASTER_TITLE.search(title))
        off_topic_disaster = disaster and not wants_disaster
        return (off_topic_disaster, -hits, source_priority(c.get("source")), -sc)

    return sorted(clips, key=key)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp not found")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found")

    project_dir = Path(args.project_dir).resolve()
    config = load_json(Path(args.config).resolve())
    media_cfg = config["media"]
    broll_cfg = load_analyzer_config(config.get("broll_analyzer"))
    fallback_duration = max(0.25, coerce_duration(config.get("planner", {}).get("default_segment_duration_sec", 12)))
    selected = load_json(project_dir / "selected-clips.json")
    try:
        shot_plan = load_json(project_dir / "shot-plan.json")
    except OSError:
        shot_plan = {"segments": []}
    shot_meta: dict = {}
    for s in shot_plan.get("segments", []):
        shot_meta[str(s.get("segment_id"))] = {
            "concept": s.get("concept", ""),
            "query": s.get("query", ""),
            "keywords": s.get("keywords") or [],
        }

    downloads = resolve_media_dir(media_cfg["download_dir"], "VIDEO_DOWNLOAD_DIR")
    normalized = resolve_media_dir(media_cfg["normalized_dir"], "VIDEO_NORMALIZED_DIR")
    downloads.mkdir(parents=True, exist_ok=True)
    normalized.mkdir(parents=True, exist_ok=True)
    ensure_min_free_space(downloads)
    print(f"[media] download_dir={downloads}", flush=True)
    print(f"[media] normalized_dir={normalized}", flush=True)

    entries = []
    failures = []
    sel_segs = [s for s in selected.get("segments", []) if s.get("selected")]
    n_total = len(sel_segs)
    print(f"[download] {n_total} segment(s) to download/normalize", flush=True)
    for seg_i, seg in enumerate(sel_segs, start=1):
        print(
            f"[download] segment {seg_i}/{n_total}: {seg.get('segment_id')} — {seg.get('concept', '')}",
            flush=True,
        )
        selected_candidates = sort_clips_for_segment(seg, list(seg.get("selected", [])), shot_meta)
        succeeded = False
        last_error = ""
        for clip in selected_candidates:
            clip_duration = coerce_duration(clip.get("duration_sec"))
            if clip_duration > MAX_VIDEO_DURATION_SECONDS:
                print(
                    f"[download]   SKIP [{clip.get('source')}] duration {clip_duration:.1f}s exceeds 10 minute limit",
                    flush=True,
                )
                last_error = f"duration_too_long:{clip_duration:.1f}s"
                continue
            name = safe_stem(f"{seg['segment_id']}_{clip['title']}")
            out_tpl = downloads / f"{name}.%(ext)s"
            norm_out = normalized / f"{name}.normalized.mov"

            try:
                if not args.dry_run:
                    title_short = str(clip.get("title") or "")[:88]
                    print(
                        f"[download]   trying [{clip.get('source')}] {title_short}",
                        flush=True,
                    )
                    dl = sorted(downloads.glob(f"{name}.*"))
                    src = dl[-1] if dl else None
                    if norm_out.exists() and src is not None:
                        print(f"[download]   reusing existing normalized clip: {norm_out.name}", flush=True)
                    else:
                        if src is None:
                            download_video_with_fallback(clip["url"], out_tpl, str(clip.get("source") or ""))
                            dl = sorted(downloads.glob(f"{name}.*"))
                            if not dl:
                                raise RuntimeError("download produced no files")
                            src = dl[-1]
                        else:
                            print(f"[download]   reusing existing download: {src.name}", flush=True)
                        if not norm_out.exists():
                            run(
                                [
                                    "ffmpeg",
                                    "-y",
                                    "-i",
                                    str(src),
                                    "-map",
                                    "0:v:0",
                                    "-map",
                                    "0:a:0",
                                    "-c:v",
                                    media_cfg["video_codec"],
                                    "-profile:v",
                                    media_cfg["video_profile"],
                                    "-pix_fmt",
                                    media_cfg["pixel_format"],
                                    "-c:a",
                                    media_cfg["audio_codec"],
                                    "-ar",
                                    str(media_cfg["audio_rate"]),
                                    "-ac",
                                    str(media_cfg["audio_channels"]),
                                    str(norm_out),
                                ]
                            )
                    duration = coerce_duration(probe_duration(norm_out))
                else:
                    src = Path(str(out_tpl).replace("%(ext)s", "mp4"))
                    duration = coerce_duration(clip.get("duration_sec"))

                if duration > MAX_VIDEO_DURATION_SECONDS:
                    raise RuntimeError(f"duration_too_long:{duration:.1f}s")
                if duration <= 0:
                    duration = fallback_duration

                entries.append(
                    {
                        "segment_id": seg["segment_id"],
                        "concept": seg["concept"],
                        "source": clip.get("source"),
                        "source_url": clip.get("url"),
                        "source_title": clip.get("title"),
                        "downloaded": str(src.resolve()),
                        "normalized": str(norm_out.resolve()),
                        "duration_seconds": duration,
                        "timeline": {"enabled": True, "label": seg["concept"], "in_seconds": 0.0, "out_seconds": duration},
                        "broll_analysis": analyze_video_for_broll(
                            normalized_path=norm_out,
                            duration_seconds=duration,
                            analyzer_cfg=broll_cfg,
                        )
                        if not args.dry_run
                        else default_analysis(duration, reason="dry_run"),
                    }
                )
                entries[-1]["broll_windows"] = list(entries[-1]["broll_analysis"].get("broll_windows", []))
                entries[-1]["broll_top_window"] = entries[-1]["broll_analysis"].get("broll_top_window")
                entries[-1]["broll_markers"] = list(entries[-1]["broll_analysis"].get("broll_markers", []))
                print(
                    f"[download]   OK ({clip.get('source')}) {duration:.1f}s — {norm_out.name}",
                    flush=True,
                )
                succeeded = True
                break
            except Exception as ex:
                last_error = str(ex)
                print(f"[download]   FAIL {last_error[:160]}", flush=True)
                continue

        if not succeeded:
            failures.append(
                {
                    "segment_id": seg.get("segment_id"),
                    "concept": seg.get("concept"),
                    "error": last_error or "all_candidates_failed",
                }
            )
            # Continue pipeline even if one segment fails.
            print(
                f"[download] segment {seg.get('segment_id')} failed after all candidates",
                flush=True,
            )
            continue

    write_json(
        project_dir / "media-manifest.json",
        {"generated_at": datetime.now(UTC).isoformat(), "entries": entries, "failures": failures},
    )
    print(f"[download] wrote media-manifest.json ({len(entries)} entries, {len(failures)} failures)", flush=True)
    print(project_dir / "media-manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

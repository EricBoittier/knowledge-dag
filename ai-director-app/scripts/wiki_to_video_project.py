#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


USER_AGENT = "knowledge-dag-ai-director/0.1 (wiki-to-video example)"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slugify(text: str, fallback: str = "item") -> str:
    s = (
        text.encode("ascii", "ignore")
        .decode("ascii")
        .replace("'", "")
    )
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._-")
    return (s[:72] or fallback)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_json(url: str, timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_file(url: str, out: Path, timeout: int = 30) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out.write_bytes(resp.read())


def title_from_input(raw: str) -> str:
    text = raw.strip()
    if not text:
        return "Penguin"
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urllib.parse.urlparse(text)
        if parsed.path:
            return urllib.parse.unquote(parsed.path.rstrip("/").split("/")[-1]).replace("_", " ")
    return text.replace("_", " ")


def strip_html(text: Any) -> str:
    raw = str(text or "")
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def split_sentences(text: str, limit: int) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return sentences[:limit]


def fetch_summary(title: str) -> dict[str, Any]:
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title.replace(' ', '_'))}"
    return get_json(url)


def fetch_links(title: str, limit: int) -> list[str]:
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&format=json&prop=links"
        f"&titles={urllib.parse.quote(title)}&plnamespace=0&pllimit={max(1, limit)}"
    )
    payload = get_json(url)
    pages = payload.get("query", {}).get("pages", {})
    out: list[str] = []
    for page in pages.values():
        for link in page.get("links", []) or []:
            link_title = str(link.get("title") or "").strip()
            if link_title and not link_title.startswith(("List of", "Outline of")):
                out.append(link_title)
    return out[:limit]


def fetch_sections(title: str, limit: int) -> list[str]:
    url = (
        "https://en.wikipedia.org/w/api.php?action=parse&format=json&prop=sections"
        f"&page={urllib.parse.quote(title)}"
    )
    payload = get_json(url)
    skip = {
        "see also",
        "notes",
        "references",
        "bibliography",
        "further reading",
        "external links",
        "citations",
        "sources",
    }
    out: list[str] = []
    for section in payload.get("parse", {}).get("sections", []) or []:
        line = strip_html(section.get("line") or "")
        if not line or line.lower() in skip:
            continue
        try:
            level = int(section.get("level") or 99)
        except (TypeError, ValueError):
            level = 99
        if level > 2:
            continue
        out.append(line)
        if len(out) >= limit:
            break
    return out


def fetch_page_image_titles(title: str, limit: int) -> list[str]:
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&format=json&prop=images"
        f"&titles={urllib.parse.quote(title)}&imlimit={max(1, limit * 4)}"
    )
    payload = get_json(url)
    pages = payload.get("query", {}).get("pages", {})
    out: list[str] = []
    for page in pages.values():
        for img in page.get("images", []) or []:
            name = str(img.get("title") or "").strip()
            low = name.lower()
            if not name.startswith("File:"):
                continue
            if any(x in low for x in (".svg", ".gif", "icon", "symbol", "map", "range")):
                continue
            out.append(name)
    return out[: limit * 3]


def commons_imageinfo(file_titles: list[str], thumb_width: int) -> list[dict[str, Any]]:
    if not file_titles:
        return []
    titles = "|".join(file_titles[:50])
    url = (
        "https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
        f"&titles={urllib.parse.quote(titles)}"
        "&iiprop=url|mime|size|extmetadata"
        f"&iiurlwidth={thumb_width}"
    )
    payload = get_json(url)
    pages = payload.get("query", {}).get("pages", {})
    out: list[dict[str, Any]] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = str(info.get("mime") or "").lower()
        if not mime.startswith("image/") or "svg" in mime:
            continue
        url_value = str(info.get("url") or "")
        if not url_value:
            continue
        meta = info.get("extmetadata") or {}
        out.append(
            {
                "title": str(page.get("title") or "").replace("File:", ""),
                "url": url_value,
                "thumbnail_url": str(info.get("thumburl") or url_value),
                "mime_type": mime,
                "width": info.get("width"),
                "height": info.get("height"),
                "creator": strip_html((meta.get("Artist") or {}).get("value") or "Wikimedia Commons"),
                "license": strip_html((meta.get("LicenseShortName") or {}).get("value") or "commons"),
                "attribution": strip_html((meta.get("Attribution") or {}).get("value") or (meta.get("Artist") or {}).get("value") or "Wikimedia Commons"),
                "source_page": str((meta.get("ObjectName") or {}).get("value") or page.get("title") or ""),
            }
        )
    return out


def search_commons_images(query: str, limit: int, thumb_width: int) -> list[dict[str, Any]]:
    url = (
        "https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
        f"&gsrsearch={urllib.parse.quote(query + ' filetype:bitmap')}"
        f"&gsrnamespace=6&gsrlimit={max(1, limit)}"
        "&prop=imageinfo&iiprop=url|mime|size|extmetadata"
        f"&iiurlwidth={thumb_width}"
    )
    payload = get_json(url)
    pages = payload.get("query", {}).get("pages", {})
    return commons_imageinfo([str(p.get("title") or "") for p in pages.values()], thumb_width)


def collect_images(title: str, max_images: int, thumb_width: int) -> list[dict[str, Any]]:
    page_images = commons_imageinfo(fetch_page_image_titles(title, max_images), thumb_width)
    search_images = search_commons_images(title, max_images * 2, thumb_width)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in [*page_images, *search_images]:
        key = item["url"]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_images:
            break
    return out


def load_cached_assets(project_dir: Path, max_images: int) -> list[dict[str, Any]]:
    cache_path = project_dir / "wiki-image-assets.json"
    out: list[dict[str, Any]] = []
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        assets = payload.get("assets") or []
        for item in assets:
            local_raw = str(item.get("local_path") or "").strip()
            timeline_raw = str(item.get("timeline_path") or "").strip()
            local_path = Path(local_raw) if local_raw else None
            timeline_path = Path(timeline_raw) if timeline_raw else None
            if not (local_path and local_path.is_file()) and not (timeline_path and timeline_path.is_file()):
                continue
            out.append(dict(item))
            if len(out) >= max_images:
                break
    if out:
        return out

    image_dir = project_dir / "output" / "wiki-assets" / "images"
    still_dir = project_dir / "output" / "wiki-assets" / "stills"
    for image_path in sorted(image_dir.glob("*")):
        if not image_path.is_file():
            continue
        stem = image_path.stem
        clip_path = still_dir / f"{stem}.still.mov"
        out.append(
            {
                "title": stem,
                "url": image_path.resolve().as_uri(),
                "thumbnail_url": image_path.resolve().as_uri(),
                "mime_type": "image/local",
                "creator": "Wikimedia Commons",
                "license": "commons",
                "attribution": "Wikimedia Commons",
                "source_page": stem,
                "local_path": str(image_path.resolve()),
                "timeline_path": str(clip_path.resolve()) if clip_path.is_file() else str(image_path.resolve()),
            }
        )
        if len(out) >= max_images:
            break
    return out


def render_still_clip(image_path: Path, out_path: Path, duration: float, width: int, height: int) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-c:v",
            "dnxhd",
            "-profile:v",
            "dnxhr_hq",
            "-pix_fmt",
            "yuv422p",
            "-an",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and out_path.exists()


def build_project(args: argparse.Namespace) -> None:
    project_dir = Path(args.project_dir).resolve()
    if project_dir.exists() and any(project_dir.iterdir()) and not args.force:
        raise SystemExit(f"Project already exists or is not empty: {project_dir} (pass --force to overwrite files)")
    project_dir.mkdir(parents=True, exist_ok=True)

    title = title_from_input(args.title)
    summary = fetch_summary(title)
    resolved_title = str(summary.get("title") or title)
    extract = str(summary.get("extract") or "")
    source_url = str(((summary.get("content_urls") or {}).get("desktop") or {}).get("page") or "")
    sections = fetch_sections(resolved_title, args.max_segments)
    links = fetch_links(resolved_title, args.max_segments)
    try:
        images = collect_images(resolved_title, args.max_images, args.thumb_width)
    except Exception as exc:
        images = load_cached_assets(project_dir, args.max_images)
        if images:
            print(f"warning: Wikimedia image lookup failed; reusing cached assets: {exc}", file=sys.stderr)
        else:
            raise
    if not images:
        raise SystemExit(f"No usable Commons images found for {resolved_title}")

    sentences = split_sentences(extract, args.max_segments)
    if not sentences:
        sentences = [f"{resolved_title} is the topic for this wiki-to-video example."]

    segment_titles = [resolved_title]
    for section in sections:
        if len(segment_titles) >= min(args.max_segments, len(images)):
            break
        if section.lower() != resolved_title.lower():
            segment_titles.append(section)
    root_terms = {t for t in re.sub(r"[^a-z0-9\s]+", " ", resolved_title.lower()).split() if len(t) >= 4}
    for link in links:
        if len(segment_titles) >= min(args.max_segments, len(images)):
            break
        link_terms = {t for t in re.sub(r"[^a-z0-9\s]+", " ", link.lower()).split() if len(t) >= 4}
        if link.lower() != resolved_title.lower() and (not root_terms or root_terms & link_terms):
            segment_titles.append(link)
    while len(segment_titles) < min(args.max_segments, len(images), len(sentences)):
        segment_titles.append(f"{resolved_title} detail {len(segment_titles) + 1}")

    segment_count = min(args.max_segments, len(images), max(1, len(segment_titles)))
    segment_titles = segment_titles[:segment_count]
    images = images[:segment_count]

    image_dir = project_dir / "output" / "wiki-assets" / "images"
    still_dir = project_dir / "output" / "wiki-assets" / "stills"
    entries: list[dict[str, Any]] = []
    script_lines: list[dict[str, str]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    text_overlays: list[dict[str, Any]] = []
    wiki_assets: list[dict[str, Any]] = []

    offset = 0.0
    for i, (seg_title, image) in enumerate(zip(segment_titles, images), start=1):
        seg_id = f"seg_{len(entries) + 1:03d}"
        stem = f"{seg_id}_{slugify(seg_title)}"
        suffix = Path(urllib.parse.urlparse(image["url"]).path).suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
            suffix = ".jpg"
        image_path = image_dir / f"{stem}{suffix}"
        clip_path = still_dir / f"{stem}.still.mov"

        cached_image_raw = str(image.get("local_path") or "").strip()
        cached_clip_raw = str(image.get("timeline_path") or "").strip()
        cached_image = Path(cached_image_raw) if cached_image_raw else None
        cached_clip = Path(cached_clip_raw) if cached_clip_raw else None
        if cached_image and cached_image.is_file():
            image_path = cached_image
        else:
            download_url = str(image.get("thumbnail_url") or image["url"])
            try:
                download_file(download_url, image_path)
            except Exception as first_exc:
                if download_url != image["url"]:
                    try:
                        download_file(image["url"], image_path)
                    except Exception as second_exc:
                        print(f"warning: skipping image {image.get('title')}: {second_exc}", file=sys.stderr)
                        continue
                else:
                    print(f"warning: skipping image {image.get('title')}: {first_exc}", file=sys.stderr)
                    continue
        if cached_clip and cached_clip.is_file():
            timeline_path = cached_clip
        else:
            rendered = render_still_clip(image_path, clip_path, args.segment_duration_sec, args.width, args.height)
            timeline_path = clip_path if rendered else image_path
        sentence = sentences[(i - 1) % len(sentences)]
        narration = f"{seg_title}: {sentence}"
        node_id = f"n_{len(entries) + 1:03d}"

        nodes.append(
            {
                "id": node_id,
                "title": seg_title,
                "tags": ["wikipedia", "image", resolved_title.lower().replace(" ", "_")],
                "importance": round(max(0.3, 1.0 - (i - 1) * 0.06), 3),
                "duration_intent_sec": args.segment_duration_sec,
            }
        )
        if len(nodes) > 1:
            edges.append({"from": nodes[-2]["id"], "to": node_id})

        script_lines.append({"segment_id": seg_id, "text": narration, "subtitle_text": narration})
        entries.append(
            {
                "segment_id": seg_id,
                "concept": seg_title,
                "source": "wikimedia",
                "source_url": image["url"],
                "source_title": image["title"],
                "downloaded": str(image_path),
                "normalized": str(timeline_path),
                "duration_seconds": args.segment_duration_sec,
                "timeline": {
                    "enabled": True,
                    "label": seg_title,
                    "in_seconds": 0.0,
                    "out_seconds": args.segment_duration_sec,
                },
                "wiki_image": {
                    "creator": image["creator"],
                    "license": image["license"],
                    "attribution": image["attribution"],
                    "mime_type": image["mime_type"],
                },
            }
        )
        text_overlays.append(
            {
                "id": f"title_{seg_id}",
                "start": round(offset + 0.35, 3),
                "end": round(offset + min(args.segment_duration_sec, 3.8), 3),
                "text": seg_title,
                "lane": -3,
                "style": {"placement": "top", "alignment": "center", "fontSize": 58, "fontColor": "#FFFFFF"},
            }
        )
        wiki_assets.append({**image, "local_path": str(image_path), "timeline_path": str(timeline_path), "segment_id": seg_id})
        offset += args.segment_duration_sec
        time.sleep(args.request_pause_sec)

    generated_at = now_iso()
    write_json(project_dir / "wiki-source.json", {"generated_at": generated_at, "title": resolved_title, "url": source_url, "extract": extract})
    write_json(project_dir / "wiki-image-assets.json", {"generated_at": generated_at, "source": "wikimedia_commons", "assets": wiki_assets})
    dag_doc = {"nodes": nodes, "edges": edges}
    shot_plan_doc = {"generated_at": generated_at, "traversal": "wiki_order", "segments": [
        {
            "segment_id": f"seg_{i:03d}",
            "concept": n["title"],
            "keywords": [n["title"], resolved_title, "wikipedia", "wikimedia"],
            "target_duration_sec": args.segment_duration_sec,
            "priority": n["importance"],
            "query": f"{n['title']} {resolved_title}",
        }
        for i, n in enumerate(nodes, start=1)
    ]}
    script_doc = {"generated_at": generated_at, "lines": script_lines}
    script_md = "# Penguins Wiki Script\n\n" + "\n\n".join(f"## {line['segment_id']}\n{line['text']}" for line in script_lines) + "\n"
    edit_annotations_doc = {"generated_at": generated_at, "annotations": []}
    media_manifest_doc = {"generated_at": generated_at, "entries": entries, "failures": []}

    write_json(project_dir / "dag.project.json", dag_doc)
    write_json(project_dir / "shot-plan.json", shot_plan_doc)
    write_json(project_dir / "script-lines.json", script_doc)
    write_text(project_dir / "script.md", script_md)
    write_json(project_dir / "edit-annotations.json", edit_annotations_doc)
    write_json(project_dir / "media-manifest.json", media_manifest_doc)
    timeline_annotations = {
        "schema_version": 1,
        "generated_at": generated_at,
        "mode": "studio",
        "markers": [{"id": "wiki_source", "t_seconds": 0, "label": f"Wikipedia: {resolved_title}"}],
        "text_overlays": text_overlays,
        "media_overlays": [],
    }
    write_json(project_dir / "timeline-annotations.json", timeline_annotations)
    variant_dir = project_dir / "variants" / "default"
    write_json(variant_dir / "media-manifest.json", media_manifest_doc)
    write_json(variant_dir / "script-lines.json", script_doc)
    write_text(variant_dir / "script.md", script_md)
    write_json(variant_dir / "edit-annotations.json", edit_annotations_doc)
    write_json(variant_dir / "timeline-annotations.json", timeline_annotations)

    if not entries:
        raise SystemExit("No images could be downloaded for the timeline")

    print(project_dir)
    print(f"wrote {len(entries)} segment(s), {len(wiki_assets)} image asset(s)")
    if shutil.which("ffmpeg") is None:
        print("warning: ffmpeg not found; timeline will reference still images directly", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Create an AI Director video project from a Wikipedia page and Commons images.")
    ap.add_argument("--title", default="Penguin", help="Wikipedia title or URL. Example: Penguin")
    ap.add_argument("--project-dir", default="./projects/penguins-wiki")
    ap.add_argument("--max-images", type=int, default=8)
    ap.add_argument("--max-segments", type=int, default=8)
    ap.add_argument("--segment-duration-sec", type=float, default=5.0)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--thumb-width", type=int, default=960)
    ap.add_argument("--request-pause-sec", type=float, default=0.2)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    build_project(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

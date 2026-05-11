#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def split_points(concept: str) -> list[str]:
    raw = [x.strip() for x in re.split(r"(?:\n+|;)", concept) if x.strip()]
    if not raw:
        return []
    points: list[str] = []
    for item in raw:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", item) if p.strip()]
        points.extend(parts if parts else [item])
    return [p for p in points if p]


def normalize_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= 64:
        return text
    return text[:61].rstrip() + "..."


def build_dag(concept: str, default_duration_sec: int) -> dict:
    points = split_points(concept)
    if not points:
        points = ["Introduction", "Core concepts", "Key example", "Summary"]
    nodes = []
    edges = []
    for i, point in enumerate(points, start=1):
        nid = f"n_{i:03d}"
        nodes.append(
            {
                "id": nid,
                "title": normalize_title(point),
                "tags": ["concept", "auto"],
                "importance": round(max(0.3, 1.0 - (i - 1) * 0.05), 3),
                "duration_intent_sec": default_duration_sec,
            }
        )
        if i > 1:
            edges.append({"from": f"n_{i-1:03d}", "to": nid})
    return {"nodes": nodes, "edges": edges}


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap dag.project.json from freeform concept text")
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--concept", required=True)
    ap.add_argument("--default-duration-sec", type=int, default=14)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    dag_path = project_dir / "dag.project.json"
    if dag_path.exists() and not args.force:
        print(f"dag exists, skipping: {dag_path}")
        return 0

    payload = build_dag(args.concept, default_duration_sec=max(4, int(args.default_duration_sec)))
    dag_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(dag_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

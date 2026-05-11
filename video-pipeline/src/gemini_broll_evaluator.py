#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


def _safe_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out


def _extract_json_block(text: str) -> Dict[str, Any]:
    body = str(text or "").strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body.replace("json\n", "", 1).strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            return json.loads(body[start : end + 1])
        raise


def _read_project_context(gemini_project_dir: Path | None) -> Dict[str, Any]:
    if gemini_project_dir is None:
        return {}
    out: Dict[str, Any] = {}
    for name in ("dag.project.json", "script-lines.json", "script.md"):
        path = gemini_project_dir / name
        if not path.exists():
            continue
        if name.endswith(".json"):
            try:
                out[name] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
        else:
            out[name] = path.read_text(encoding="utf-8")[:4000]
    return out


def _build_prompt(entry: Dict[str, Any], project_context: Dict[str, Any], max_windows: int) -> str:
    windows = list(entry.get("broll_windows", []))[:max_windows]
    clip_label = str(entry.get("source_label") or entry.get("concept") or "clip")
    duration = _safe_float(entry.get("duration_seconds"), 0.0)
    window_lines = []
    for idx, w in enumerate(windows, start=1):
        window_lines.append(
            f"{idx}. {w.get('start_seconds', 0)}-{w.get('end_seconds', 0)}s | "
            f"caption={w.get('caption', '')} | score={w.get('scores', {}).get('score', 0)}"
        )
    project_blob = json.dumps(project_context, ensure_ascii=True)[:8000]
    return (
        "You are evaluating whether a video clip should be included as project b-roll.\n"
        "Use project context, clip caption windows, and timestamps.\n"
        "Return STRICT JSON only with keys:\n"
        '{"include": bool, "fit_score": number(0..1), "reason": string, '
        '"suggested_window": {"start_seconds": number, "end_seconds": number} | null}\n\n'
        f"Clip label: {clip_label}\n"
        f"Clip duration: {duration}\n"
        f"Candidate windows:\n{chr(10).join(window_lines) if window_lines else 'none'}\n\n"
        f"Project context:\n{project_blob}\n"
    )


def _call_gemini(prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        endpoint,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as ex:
        raise RuntimeError(f"gemini_request_failed:{ex}") from ex
    text = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json_block(text)
    return parsed


def evaluate_manifest_broll_fit(
    manifest_path: Path,
    cfg: Dict[str, Any],
    gemini_project_dir: Path | None = None,
) -> Dict[str, Any]:
    judge_cfg = cfg.get("gemini_broll_judge", {})
    if not judge_cfg.get("enabled", False):
        return {"enabled": False, "reason": "judge_disabled"}

    api_key = str(os.getenv("GEMINI_API_KEY", "")).strip()
    if not api_key:
        return {"enabled": False, "reason": "missing_gemini_api_key"}

    model = str(judge_cfg.get("model", "gemini-1.5-flash"))
    min_fit_score = max(0.0, min(1.0, _safe_float(judge_cfg.get("min_fit_score", 0.55), 0.55)))
    max_windows = max(1, int(judge_cfg.get("max_windows_in_prompt", 8)))
    apply_to_timeline = bool(judge_cfg.get("apply_to_timeline", True))

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(payload.get("entries", []))
    project_context = _read_project_context(gemini_project_dir)
    decisions: List[Dict[str, Any]] = []

    for entry in entries:
        if not entry.get("broll_windows"):
            decision = {
                "include": False,
                "fit_score": 0.0,
                "reason": "no_broll_windows",
                "suggested_window": None,
            }
        else:
            prompt = _build_prompt(entry=entry, project_context=project_context, max_windows=max_windows)
            try:
                decision = _call_gemini(prompt=prompt, model=model, api_key=api_key)
            except Exception as ex:
                decision = {
                    "include": True,
                    "fit_score": 0.5,
                    "reason": f"gemini_error:{ex}",
                    "suggested_window": None,
                }

        include = bool(decision.get("include", True))
        fit_score = max(0.0, min(1.0, _safe_float(decision.get("fit_score"), 0.0)))
        if fit_score < min_fit_score:
            include = False

        suggestion = decision.get("suggested_window")
        if isinstance(suggestion, dict):
            try:
                s_in = float(suggestion.get("start_seconds", 0.0))
                s_out = float(suggestion.get("end_seconds", 0.0))
                if s_out > s_in:
                    entry["broll_top_window"] = {"start_seconds": s_in, "end_seconds": s_out}
            except (TypeError, ValueError):
                pass

        timeline = dict(entry.get("timeline", {}))
        if apply_to_timeline:
            timeline["enabled"] = include
            entry["timeline"] = timeline

        entry["broll_judgement"] = {
            "include": include,
            "fit_score": fit_score,
            "reason": str(decision.get("reason", "")),
            "model": model,
        }
        decisions.append(entry["broll_judgement"])

    payload["entries"] = entries
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "enabled": True,
        "model": model,
        "entries": len(entries),
        "included": sum(1 for d in decisions if d.get("include")),
        "excluded": sum(1 for d in decisions if not d.get("include")),
    }

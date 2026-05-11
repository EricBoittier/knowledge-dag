#!/usr/bin/env python3
from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

import subprocess


DEFAULT_SCHEMA_VERSION = "broll-analysis.v1"
INTEREST_TERMS = {
    "animal",
    "wildlife",
    "nature",
    "action",
    "dramatic",
    "close",
    "aerial",
    "ocean",
    "mountain",
    "forest",
    "city",
    "crowd",
    "sunset",
    "storm",
    "underwater",
}
SAFETY_NEGATIVE_TERMS = {"gore", "blood", "graphic", "injury", "violence", "nsfw"}


@dataclass(frozen=True)
class AnalyzerConfig:
    enabled: bool
    model_name: str
    device: str
    sample_interval_sec: float
    window_duration_sec: float
    max_windows: int
    min_window_score: float
    max_new_tokens: int


def _safe_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _safe_int(value: Any, default: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out


def load_analyzer_config(raw_cfg: Dict[str, Any] | None) -> AnalyzerConfig:
    cfg = raw_cfg or {}
    return AnalyzerConfig(
        enabled=bool(cfg.get("enabled", False)),
        model_name=str(cfg.get("model_name", "Salesforce/blip-image-captioning-base")),
        device=str(cfg.get("device", "cpu")),
        sample_interval_sec=max(0.4, _safe_float(cfg.get("sample_interval_sec", 2.0), 2.0)),
        window_duration_sec=max(1.0, _safe_float(cfg.get("window_duration_sec", 4.0), 4.0)),
        max_windows=max(1, _safe_int(cfg.get("max_windows", 5), 5)),
        min_window_score=max(0.0, min(1.0, _safe_float(cfg.get("min_window_score", 0.35), 0.35))),
        max_new_tokens=max(8, _safe_int(cfg.get("max_new_tokens", 32), 32)),
    )


def _run_ffmpeg_extract_frames(video_path: Path, tmp_dir: Path, sample_interval_sec: float) -> List[Path]:
    output_pattern = tmp_dir / "frame_%06d.jpg"
    fps_filter = f"fps=1/{sample_interval_sec:.4f}"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        fps_filter,
        "-q:v",
        "3",
        str(output_pattern),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg_frame_extract_failed: {proc.stderr.strip()[:240]}")
    frames = sorted(tmp_dir.glob("frame_*.jpg"))
    return frames


def _load_captioner(model_name: str, device: str):
    try:
        from transformers import pipeline  # type: ignore
    except Exception as ex:  # pragma: no cover - optional dependency
        raise RuntimeError(f"transformers_unavailable:{ex.__class__.__name__}") from ex
    device_index = -1
    if device.startswith("cuda"):
        device_index = 0
    task_candidates = ["image-to-text", "image-text-to-text"]
    last_error: Exception | None = None
    for task in task_candidates:
        try:
            return pipeline(task, model=model_name, device=device_index)
        except Exception as ex:  # pragma: no cover - version-dependent behavior
            last_error = ex
            continue
    raise RuntimeError(f"no_supported_image_caption_task:{last_error}")


def _load_manual_captioner(model_name: str, device: str):
    try:
        import torch  # type: ignore
        from PIL import Image  # type: ignore
        import transformers  # type: ignore
    except Exception as ex:  # pragma: no cover - optional dependency
        # Keep message details so environment issues are diagnosable.
        raise RuntimeError(f"manual_captioner_unavailable:{ex.__class__.__name__}:{ex}") from ex

    torch_device = "cpu"
    if device.startswith("cuda") and torch.cuda.is_available():
        torch_device = "cuda"
    processor = None
    model = None
    # Prefer BLIP-specific classes for this project default model.
    blip_error: Exception | None = None
    try:
        BlipProcessor = getattr(transformers, "BlipProcessor")
        BlipForConditionalGeneration = getattr(transformers, "BlipForConditionalGeneration")
        processor = BlipProcessor.from_pretrained(model_name)
        model = BlipForConditionalGeneration.from_pretrained(model_name)
    except Exception as ex:
        blip_error = ex

    if processor is None or model is None:
        generic_error: Exception | None = None
        try:
            AutoProcessor = getattr(transformers, "AutoProcessor")
            AutoModelForVision2Seq = getattr(transformers, "AutoModelForVision2Seq")
            processor = AutoProcessor.from_pretrained(model_name)
            model = AutoModelForVision2Seq.from_pretrained(model_name)
        except Exception as ex:
            generic_error = ex
            raise RuntimeError(
                "manual_captioner_model_load_failed:"
                f"blip={blip_error.__class__.__name__ if blip_error else 'None'}:{blip_error};"
                f"generic={generic_error.__class__.__name__}:{generic_error}"
            ) from ex

    if processor is None or model is None:
        raise RuntimeError("manual_captioner_model_load_failed:processor_or_model_none")
    model.to(torch_device)
    model.eval()

    def _run_single(image_path: Path, max_new_tokens: int) -> str:
        image = Image.open(image_path).convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        inputs = {k: v.to(torch_device) for k, v in inputs.items()}
        generated = model.generate(**inputs, max_new_tokens=max_new_tokens)
        text = processor.batch_decode(generated, skip_special_tokens=True)
        return str(text[0]).strip() if text else ""

    return _run_single


def _caption_frames(frame_paths: Sequence[Path], model_name: str, device: str, max_new_tokens: int) -> List[str]:
    captions: List[str] = []
    try:
        captioner = _load_captioner(model_name=model_name, device=device)
        for frame_path in frame_paths:
            out = captioner(str(frame_path), max_new_tokens=max_new_tokens)
            text = ""
            if isinstance(out, list) and out:
                item = out[0] if isinstance(out[0], dict) else {}
                text = str(item.get("generated_text", "")).strip()
            captions.append(text)
        return captions
    except Exception as ex:
        msg = str(ex)
        # Fallback path for certain transformers/torch combos where pipeline passes unsupported kwargs.
        if "BatchEncoding.to() got an unexpected keyword argument 'dtype'" not in msg:
            raise
        manual_caption = _load_manual_captioner(model_name=model_name, device=device)
        return [manual_caption(frame_path, max_new_tokens=max_new_tokens) for frame_path in frame_paths]


def _score_caption(caption: str) -> Dict[str, float]:
    lowered = str(caption or "").lower()
    if not lowered:
        return {"interest": 0.0, "usability": 0.1, "novelty": 0.0, "safety": 1.0, "score": 0.0}
    tokens = [tok for tok in lowered.replace(",", " ").replace(".", " ").split() if tok]
    hit_count = sum(1 for tok in tokens if tok in INTEREST_TERMS)
    neg_count = sum(1 for tok in tokens if tok in SAFETY_NEGATIVE_TERMS)
    unique_ratio = min(1.0, len(set(tokens)) / max(1.0, len(tokens)))
    interest = min(1.0, 0.2 + 0.2 * hit_count)
    usability = 0.6 if len(tokens) >= 3 else 0.35
    novelty = unique_ratio
    safety = max(0.0, 1.0 - 0.5 * neg_count)
    score = max(0.0, min(1.0, 0.35 * interest + 0.35 * usability + 0.2 * novelty + 0.1 * safety))
    return {
        "interest": round(interest, 4),
        "usability": round(usability, 4),
        "novelty": round(novelty, 4),
        "safety": round(safety, 4),
        "score": round(score, 4),
    }


def _build_windows(
    captions: Sequence[str],
    duration_seconds: float,
    sample_interval_sec: float,
    window_duration_sec: float,
    min_window_score: float,
    max_windows: int,
) -> List[Dict[str, Any]]:
    windows: List[Dict[str, Any]] = []
    if duration_seconds <= 0:
        return windows
    for idx, caption in enumerate(captions):
        start = idx * sample_interval_sec
        if start >= duration_seconds:
            break
        end = min(duration_seconds, start + window_duration_sec)
        metrics = _score_caption(caption)
        if metrics["score"] < min_window_score:
            continue
        caption_tokens = [t for t in str(caption).lower().split() if t]
        tags = sorted({t for t in caption_tokens if t in INTEREST_TERMS})[:6]
        windows.append(
            {
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "caption": caption,
                "tags": tags,
                "confidence": round(min(0.99, 0.45 + 0.5 * metrics["score"]), 4),
                "scores": metrics,
                "rejection_reasons": [],
            }
        )
    windows.sort(key=lambda w: float(w.get("scores", {}).get("score", 0.0)), reverse=True)
    return windows[:max_windows]


def default_analysis(duration_seconds: float, reason: str) -> Dict[str, Any]:
    safe_duration = max(0.0, _safe_float(duration_seconds, 0.0))
    return {
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "enabled": False,
        "reason": reason,
        "model": {"name": None, "device": None},
        "duration_seconds": round(safe_duration, 3),
        "broll_windows": [],
        "broll_top_window": None,
        "broll_markers": [],
    }


def analyze_video_for_broll(
    normalized_path: Path,
    duration_seconds: float,
    analyzer_cfg: AnalyzerConfig,
) -> Dict[str, Any]:
    safe_duration = max(0.0, _safe_float(duration_seconds, 0.0))
    if not analyzer_cfg.enabled:
        return default_analysis(safe_duration, reason="analyzer_disabled")
    if safe_duration <= 0.0:
        return default_analysis(safe_duration, reason="invalid_duration")
    if not normalized_path.exists():
        return default_analysis(safe_duration, reason="missing_normalized_asset")

    try:
        with tempfile.TemporaryDirectory(prefix="broll_frames_") as td:
            tmp_dir = Path(td)
            frames = _run_ffmpeg_extract_frames(
                video_path=normalized_path,
                tmp_dir=tmp_dir,
                sample_interval_sec=analyzer_cfg.sample_interval_sec,
            )
            if not frames:
                return default_analysis(safe_duration, reason="no_sampled_frames")
            captions = _caption_frames(
                frame_paths=frames,
                model_name=analyzer_cfg.model_name,
                device=analyzer_cfg.device,
                max_new_tokens=analyzer_cfg.max_new_tokens,
            )
    except Exception as ex:
        return default_analysis(safe_duration, reason=f"analyzer_error:{ex}")

    windows = _build_windows(
        captions=captions,
        duration_seconds=safe_duration,
        sample_interval_sec=analyzer_cfg.sample_interval_sec,
        window_duration_sec=analyzer_cfg.window_duration_sec,
        min_window_score=analyzer_cfg.min_window_score,
        max_windows=analyzer_cfg.max_windows,
    )
    top_window = windows[0] if windows else None
    markers = [
        {
            "t_seconds": round(float(w["start_seconds"]), 3),
            "label": str(w.get("caption") or "broll-window")[:96],
            "score": float(w.get("scores", {}).get("score", 0.0)),
        }
        for w in windows
    ]
    return {
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "enabled": True,
        "reason": "ok",
        "model": {"name": analyzer_cfg.model_name, "device": analyzer_cfg.device},
        "duration_seconds": round(safe_duration, 3),
        "broll_windows": windows,
        "broll_top_window": top_window,
        "broll_markers": markers,
    }

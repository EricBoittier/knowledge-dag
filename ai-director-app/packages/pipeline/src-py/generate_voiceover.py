#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from clean_script_text import clean_for_narration, is_skippable_script_line


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_path(base: Path, p: str | None) -> Path | None:
    if not p:
        return None
    path = Path(p)
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def pick_engine(args_engine: str | None, voice_cfg: dict) -> str:
    env = (os.environ.get("VOICEOVER_ENGINE") or "").strip().lower()
    if env in ("espeak", "sesame_csm"):
        return env
    if args_engine:
        e = args_engine.strip().lower()
        if e in ("espeak", "sesame_csm"):
            return e
    e = str(voice_cfg.get("engine") or "espeak").strip().lower()
    return e if e in ("espeak", "sesame_csm") else "espeak"


def run_espeak(narration_text: str, out_wav: Path) -> bool:
    tts_bin = shutil.which("espeak-ng") or shutil.which("espeak")
    if not tts_bin:
        print("[voiceover] skipping; espeak-ng/espeak not installed")
        return False
    proc = subprocess.run(
        [tts_bin, "-v", "en-us", "-s", "155", "-w", str(out_wav)],
        input=narration_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"voiceover generation failed: {proc.stderr}")
    return True


def run_sesame_csm(
    narration_text: str,
    out_wav: Path,
    cfg_path: Path,
    voice_cfg: dict,
) -> None:
    """Call voice_tts/scripts/synthesize_sesame_csm.py (GPU + Unsloth + CSM)."""
    sc = voice_cfg.get("sesame_csm") or {}
    base = cfg_path.parent.parent

    python_exe = str(sc.get("python") or shutil.which("python3") or "python3")
    script_rel = sc.get("script")
    if script_rel:
        synth_script = resolve_path(base, str(script_rel))
    else:
        synth_script = (base.parent / "voice_tts" / "scripts" / "synthesize_sesame_csm.py").resolve()

    if not synth_script or not synth_script.is_file():
        raise RuntimeError(
            f"sesame_csm script not found: {synth_script}. "
            "Set voiceover.sesame_csm.script in pipeline.config.json "
            "or place voice_tts next to ai-director-app."
        )

    cmd: list[str] = [python_exe, str(synth_script), "--text", narration_text, "--out", str(out_wav)]

    lora = sc.get("lora_dir")
    if lora:
        lora_path = resolve_path(base, str(lora))
        if lora_path and lora_path.is_dir():
            cmd.extend(["--lora-dir", str(lora_path)])

    model_name = sc.get("model_name")
    if model_name:
        cmd.extend(["--model-name", str(model_name)])

    max_tok = sc.get("max_new_tokens")
    if max_tok is not None:
        cmd.extend(["--max-new-tokens", str(int(max_tok))])

    spk = sc.get("speaker_id")
    if spk is not None:
        cmd.extend(["--speaker-id", str(int(spk))])

    device = sc.get("device")
    if device:
        cmd.extend(["--device", str(device)])

    ctx_wav = sc.get("context_wav")
    ctx_txt = sc.get("context_text")
    if ctx_wav:
        cw = resolve_path(base, str(ctx_wav))
        if not cw or not cw.is_file():
            raise RuntimeError(f"voiceover.sesame_csm.context_wav not found: {ctx_wav}")
        cmd.extend(["--context-wav", str(cw)])
        if not ctx_txt:
            raise RuntimeError("voiceover.sesame_csm.context_text is required when context_wav is set")
        cmd.extend(["--context-text", str(ctx_txt)])

    print(f"[voiceover] engine=sesame_csm cmd={cmd[0]} {synth_script.name} ...", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or "sesame_csm failed"
        raise RuntimeError(err)
    if proc.stdout.strip():
        print(proc.stdout.strip(), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--engine",
        default=None,
        help="Override pipeline voiceover.engine: espeak | sesame_csm",
    )
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    cfg_path = Path(args.config).resolve()
    script_lines_path = project_dir / "script-lines.json"
    out_dir = project_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / "narration.wav"

    voice_cfg: dict = {}
    try:
        root_cfg = load_json(cfg_path)
        voice_cfg = root_cfg.get("voiceover") or {}
    except Exception as exc:
        print(f"[voiceover] config warning: {exc}", flush=True)

    if not script_lines_path.exists():
        print(f"[voiceover] script lines not found: {script_lines_path}")
        return 0

    payload = load_json(script_lines_path)
    lines = payload.get("lines", [])
    text_parts = []
    for line in lines:
        sub = str(line.get("subtitle_text") or "").strip()
        full = str(line.get("text") or "").strip()
        raw = sub if sub else full
        if is_skippable_script_line(raw):
            continue
        body = clean_for_narration(raw)
        if body:
            text_parts.append(body)
    narration_text = ". ".join(text_parts)
    if not narration_text:
        print("[voiceover] no script text available")
        return 0

    engine = pick_engine(args.engine, voice_cfg)
    print(f"[voiceover] engine={engine}", flush=True)

    if args.dry_run:
        print(f"[dry-run] voiceover hook: {out_wav} ({engine})")
        return 0

    if engine == "sesame_csm":
        run_sesame_csm(narration_text, out_wav, cfg_path, voice_cfg)
    else:
        if not run_espeak(narration_text, out_wav):
            return 0

    print(out_wav)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

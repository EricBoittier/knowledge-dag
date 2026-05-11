#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def _load_shared_module():
    here = Path(__file__).resolve()
    repo_root = here.parents[4]
    shared_src = repo_root / "video-pipeline" / "src"
    if str(shared_src) not in sys.path:
        sys.path.insert(0, str(shared_src))
    try:
        import broll_analyzer as shared  # type: ignore
    except Exception as ex:  # pragma: no cover - import shim
        raise RuntimeError(f"shared_broll_analyzer_import_failed:{ex}") from ex
    return shared


_shared = _load_shared_module()

AnalyzerConfig = _shared.AnalyzerConfig
DEFAULT_SCHEMA_VERSION = _shared.DEFAULT_SCHEMA_VERSION
analyze_video_for_broll = _shared.analyze_video_for_broll
default_analysis = _shared.default_analysis
load_analyzer_config = _shared.load_analyzer_config

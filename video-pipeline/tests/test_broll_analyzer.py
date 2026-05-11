from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from broll_analyzer import _build_windows, _score_caption, default_analysis, load_analyzer_config  # noqa: E402


class BrollAnalyzerTest(unittest.TestCase):
    def test_default_analysis_schema_shape(self) -> None:
        payload = default_analysis(12.5, reason="analyzer_disabled")
        self.assertEqual(payload["schema_version"], "broll-analysis.v1")
        self.assertEqual(payload["duration_seconds"], 12.5)
        self.assertEqual(payload["broll_windows"], [])
        self.assertIsNone(payload["broll_top_window"])

    def test_caption_scoring_prefers_interesting_terms(self) -> None:
        high = _score_caption("dramatic wildlife animal close shot in ocean")
        low = _score_caption("plain image")
        self.assertGreater(high["score"], low["score"])
        self.assertGreaterEqual(high["interest"], low["interest"])

    def test_window_builder_keeps_ranked_windows_only(self) -> None:
        captions = [
            "dramatic wildlife ocean close shot",
            "plain frame",
            "city crowd action scene",
            "quiet static object",
        ]
        windows = _build_windows(
            captions=captions,
            duration_seconds=16.0,
            sample_interval_sec=2.0,
            window_duration_sec=4.0,
            min_window_score=0.35,
            max_windows=2,
        )
        self.assertEqual(len(windows), 2)
        self.assertGreaterEqual(windows[0]["scores"]["score"], windows[1]["scores"]["score"])

    def test_config_loader_normalizes_values(self) -> None:
        cfg = load_analyzer_config(
            {
                "enabled": True,
                "sample_interval_sec": 0.1,
                "window_duration_sec": 0.2,
                "max_windows": 0,
                "min_window_score": 10,
            }
        )
        self.assertTrue(cfg.enabled)
        self.assertGreaterEqual(cfg.sample_interval_sec, 0.4)
        self.assertGreaterEqual(cfg.window_duration_sec, 1.0)
        self.assertEqual(cfg.max_windows, 1)
        self.assertEqual(cfg.min_window_score, 1.0)


if __name__ == "__main__":
    unittest.main()

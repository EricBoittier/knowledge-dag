from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

import gemini_broll_evaluator as judge  # noqa: E402


class GeminiBrollEvaluatorTest(unittest.TestCase):
    def test_extract_json_block_with_fences(self) -> None:
        text = '```json\n{"include": true, "fit_score": 0.8, "reason": "good", "suggested_window": null}\n```'
        parsed = judge._extract_json_block(text)
        self.assertTrue(parsed["include"])
        self.assertEqual(parsed["fit_score"], 0.8)

    def test_marks_no_windows_as_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "source_label": "clip_a",
                                "duration_seconds": 4.0,
                                "timeline": {"enabled": True},
                                "broll_windows": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            cfg = {"gemini_broll_judge": {"enabled": True, "apply_to_timeline": True}}
            old_call = judge._call_gemini
            try:
                judge._call_gemini = lambda **_: {"include": True, "fit_score": 0.9, "reason": "ok"}  # type: ignore
                # Key missing should short-circuit.
                result = judge.evaluate_manifest_broll_fit(manifest_path=manifest_path, cfg=cfg, gemini_project_dir=None)
                self.assertFalse(result["enabled"])
            finally:
                judge._call_gemini = old_call


if __name__ == "__main__":
    unittest.main()

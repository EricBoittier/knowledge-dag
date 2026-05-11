from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from overlay_manifest import validate_overlay_manifest  # noqa: E402


class OverlayManifestValidationTest(unittest.TestCase):
    def test_valid_manifest_passes(self) -> None:
        payload = {
            "style": {"profile": "default", "font": "Arial", "font_size": 56, "stroke": 3, "safe_margin": 64},
            "subtitle_segments": [{"text": "hello world", "start": 0.0, "end": 1.2}],
            "image_overlays": [
                {
                    "asset": "/tmp/a.png",
                    "start": 0.0,
                    "end": 1.2,
                    "x": 20,
                    "y": 40,
                    "width": 512,
                    "height": 512,
                    "anchor": "bottom_left",
                    "sentence_index": 0,
                    "source_text": "hello world",
                }
            ],
        }
        out = validate_overlay_manifest(payload)
        self.assertEqual(out["style"]["profile"], "default")

    def test_non_monotonic_subtitles_fail(self) -> None:
        payload = {
            "style": {"profile": "default", "font": "Arial", "font_size": 56, "stroke": 3, "safe_margin": 64},
            "subtitle_segments": [
                {"text": "first", "start": 1.0, "end": 2.0},
                {"text": "second", "start": 0.5, "end": 1.0},
            ],
            "image_overlays": [],
        }
        with self.assertRaises(ValueError):
            validate_overlay_manifest(payload)


if __name__ == "__main__":
    unittest.main()

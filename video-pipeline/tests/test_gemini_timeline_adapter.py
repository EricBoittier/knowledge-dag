from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gemini_timeline_adapter import build_complex_overlay_payload  # noqa: E402


class GeminiTimelineAdapterTest(unittest.TestCase):
    def test_builds_style_and_dialogue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / "a.png").write_bytes(b"x")
            manifest = {
                "entries": [
                    {"duration_seconds": 2.0, "timeline": {"enabled": True, "label": "First", "in_seconds": 0.0, "out_seconds": 2.0}},
                    {"duration_seconds": 3.0, "timeline": {"enabled": True, "label": "Second", "in_seconds": 0.0, "out_seconds": 3.0}},
                ]
            }
            script = {"lines": [{"segment_id": "seg_001", "text": "hello there", "subtitle_text": "hello"}, {"segment_id": "seg_002", "text": "second", "subtitle_text": "second"}]}
            ann = {"annotations": [{"segment_id": "seg_001", "effects": ["title_lower_third"], "transition": "cross_dissolve_8f"}]}
            payload = build_complex_overlay_payload(
                manifest_payload=manifest,
                script_payload=script,
                annotations_payload=ann,
                image_asset_dir=assets,
                video_width=1920,
                video_height=1080,
                safe_margin=64,
                overlay_width=256,
                overlay_height=256,
                anchor="bottom_left",
                checkpoint_cycle=["/tmp/c1", "/tmp/c2"],
                style_rules=[
                    {"profile": "shorts", "keywords": ["title_lower_third"]},
                    {"profile": "tiktok", "keywords": ["film", "vignette"]},
                ],
            )
            self.assertEqual(len(payload["subtitle_segments"]), 2)
            self.assertEqual(len(payload["style_events"]), 2)
            self.assertEqual(len(payload["dialogue_plan"]), 2)
            self.assertEqual(payload["style_events"][0]["profile"], "shorts")


if __name__ == "__main__":
    unittest.main()

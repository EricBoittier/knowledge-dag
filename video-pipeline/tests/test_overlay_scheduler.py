from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from overlay_scheduler import build_image_events  # noqa: E402


class OverlaySchedulerTest(unittest.TestCase):
    def test_deterministic_round_robin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset_dir = Path(tmp)
            (asset_dir / "a.png").write_bytes(b"x")
            (asset_dir / "b.png").write_bytes(b"x")
            segments = [
                {"text": "first", "start": 0.0, "end": 1.0},
                {"text": "second", "start": 1.0, "end": 2.0},
                {"text": "third", "start": 2.0, "end": 3.0},
            ]
            events = build_image_events(
                subtitle_segments=segments,
                asset_dir=asset_dir,
                video_width=1920,
                video_height=1080,
                safe_margin=64,
                overlay_width=256,
                overlay_height=256,
            )
            self.assertEqual(len(events), 3)
            self.assertTrue(str(events[0]["asset"]).endswith("a.png"))
            self.assertTrue(str(events[1]["asset"]).endswith("b.png"))
            self.assertTrue(str(events[2]["asset"]).endswith("a.png"))


if __name__ == "__main__":
    unittest.main()

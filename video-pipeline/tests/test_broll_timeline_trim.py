from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from build_timeline_fcpxml import choose_entry_trim_bounds  # noqa: E402


class BrollTimelineTrimTest(unittest.TestCase):
    def test_uses_timeline_bounds_when_broll_disabled(self) -> None:
        entry = {
            "duration_seconds": 10.0,
            "timeline": {"in_seconds": 1.0, "out_seconds": 6.0},
            "broll_top_window": {"start_seconds": 2.0, "end_seconds": 4.0},
        }
        in_sec, out_sec = choose_entry_trim_bounds(entry, use_broll_top_window=False)
        self.assertEqual((in_sec, out_sec), (1.0, 6.0))

    def test_uses_broll_window_when_enabled(self) -> None:
        entry = {
            "duration_seconds": 10.0,
            "timeline": {"in_seconds": 0.0, "out_seconds": 10.0},
            "broll_top_window": {"start_seconds": 2.5, "end_seconds": 5.5},
        }
        in_sec, out_sec = choose_entry_trim_bounds(entry, use_broll_top_window=True)
        self.assertEqual((in_sec, out_sec), (2.5, 5.5))

    def test_clamps_window_to_duration(self) -> None:
        entry = {
            "duration_seconds": 3.0,
            "timeline": {"in_seconds": 0.0, "out_seconds": 3.0},
            "broll_top_window": {"start_seconds": 2.5, "end_seconds": 9.0},
        }
        in_sec, out_sec = choose_entry_trim_bounds(entry, use_broll_top_window=True)
        self.assertEqual((in_sec, out_sec), (2.5, 3.0))


if __name__ == "__main__":
    unittest.main()

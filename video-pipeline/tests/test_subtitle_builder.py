from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from subtitle_builder import format_ass_time, format_srt_time, write_subtitles  # noqa: E402


class SubtitleBuilderTest(unittest.TestCase):
    def test_time_formatters(self) -> None:
        self.assertEqual(format_ass_time(61.5), "0:01:01.50")
        self.assertEqual(format_srt_time(61.5), "00:01:01,500")

    def test_write_subtitles_outputs_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            paths = write_subtitles(
                subtitle_segments=[
                    {"text": "one two three four five", "start": 0.0, "end": 1.0},
                    {"text": "second line", "start": 1.0, "end": 2.0},
                ],
                output_dir=out_dir,
                profile_name="default",
                max_chars_per_line=10,
                max_lines_per_cue=2,
                style_events=[{"profile": "shorts"}, {"profile": "dialogue"}],
            )
            self.assertTrue(Path(paths["ass"]).exists())
            self.assertTrue(Path(paths["srt"]).exists())
            srt_text = Path(paths["srt"]).read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:01,000", srt_text)
            ass_text = Path(paths["ass"]).read_text(encoding="utf-8")
            self.assertIn(r"{\k", ass_text)
            self.assertIn("Profile1", ass_text)


if __name__ == "__main__":
    unittest.main()

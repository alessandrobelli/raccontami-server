"""Run from the repository root with:  python -m unittest discover tests"""

import unittest

from raccontami_sync import banner

GPU = ("THIS SERVER", [("GPU", "RTX 5080", "")])


class RenderTest(unittest.TestCase):
    def test_a_value_sits_in_the_column_after_its_name(self):
        self.assertIn(banner.INDENT + "  GPU         RTX 5080", banner.render([GPU]))

    def test_every_line_starts_under_the_time(self):
        self.assertTrue(all(line.startswith(banner.INDENT) for line in banner.render([GPU])))

    def test_the_block_opens_and_closes_with_a_double_rule(self):
        lines = banner.render([GPU])
        self.assertEqual((lines[0], lines[-1]), (banner.INDENT + "=" * banner.WIDTH,) * 2)

    def test_sections_are_parted_by_a_single_rule(self):
        lines = banner.render([GPU, ("MODELS", [("Sync", "Whisper turbo", "")])])
        self.assertIn(banner.INDENT + "-" * banner.WIDTH, lines)

    def test_a_value_of_several_lines_keeps_them_in_its_column(self):
        lines = banner.render([("MODELS", [("Voices", "Italian: VoxCPM2\nEnglish: Qwen3-TTS", "")])])
        self.assertIn(banner.INDENT + " " * banner.VALUE + "English: Qwen3-TTS", lines)

    def test_a_long_note_is_wrapped_in_the_value_column(self):
        note = "word " * 40
        lines = banner.render([("CONNECT THE PHONE", [("Token", "abc", note)])])
        notes = [line for line in lines if line.strip().startswith("word")]
        self.assertTrue(len(notes) > 1 and all(len(line) <= len(banner.INDENT) + banner.WIDTH for line in notes))

    def test_a_section_without_rows_is_left_out(self):
        self.assertNotIn(banner.INDENT + "WORK", banner.render([GPU, ("WORK", [])]))


if __name__ == "__main__":
    unittest.main()

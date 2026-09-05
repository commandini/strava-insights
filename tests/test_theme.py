import unittest

from theme import (
    APP_BODY_FONT_SIZE_REM,
    APP_FONT_CSS,
    APP_FONT_FAMILY,
    APP_FONT_STACK,
    APP_METRIC_LABEL_FONT_SIZE_REM,
    APP_METRIC_VALUE_FONT_SIZE_REM,
    APP_PAGE_TITLE_FONT_SIZE_REM,
    APP_REPORT_TITLE_FONT_SIZE_REM,
    APP_SECTION_FONT_SIZE_REM,
    APP_SUBSECTION_FONT_SIZE_REM,
    APP_TABLE_FONT_SIZE_REM,
    hex_to_rgb,
    rgb_to_hex,
)


class ThemeTests(unittest.TestCase):
    def test_app_font_has_a_portable_fallback_stack(self) -> None:
        self.assertEqual(APP_FONT_FAMILY, "Avenir")
        self.assertEqual(APP_FONT_STACK[0], APP_FONT_FAMILY)
        self.assertEqual(APP_FONT_STACK[-1], "sans-serif")
        self.assertEqual(
            APP_FONT_CSS,
            '"Avenir", "Avenir Next", "Segoe UI", "Helvetica Neue", "Arial", sans-serif',
        )

    def test_typography_sizes_have_a_clear_and_consistent_hierarchy(self) -> None:
        self.assertGreater(APP_PAGE_TITLE_FONT_SIZE_REM, APP_REPORT_TITLE_FONT_SIZE_REM)
        self.assertGreater(APP_REPORT_TITLE_FONT_SIZE_REM, APP_SECTION_FONT_SIZE_REM)
        self.assertGreater(APP_SECTION_FONT_SIZE_REM, APP_SUBSECTION_FONT_SIZE_REM)
        self.assertGreater(APP_SUBSECTION_FONT_SIZE_REM, APP_BODY_FONT_SIZE_REM)
        self.assertEqual(APP_TABLE_FONT_SIZE_REM, APP_METRIC_LABEL_FONT_SIZE_REM)
        self.assertGreater(APP_METRIC_VALUE_FONT_SIZE_REM, APP_METRIC_LABEL_FONT_SIZE_REM)

    def test_converts_colors_in_both_directions(self) -> None:
        self.assertEqual(rgb_to_hex((255, 165, 0)), "#FFA500")
        self.assertEqual(hex_to_rgb("#fFa500"), (255, 165, 0))

    def test_rejects_invalid_rgb_channels(self) -> None:
        for value in ((256, 0, 0), (-1, 0, 0), (1, 2), (True, 0, 0)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rgb_to_hex(value)

    def test_rejects_invalid_hex_colors(self) -> None:
        for value in ("#FFF", "##FFA500", "#GG0000", "FFA50000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                hex_to_rgb(value)


if __name__ == "__main__":
    unittest.main()

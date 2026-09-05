"""Shared visual theme values for the app and exported reports."""

import string

DEFAULT_BACKGROUND_RGB = (255, 165, 0)
APP_FONT_FAMILY = "Avenir"
APP_FONT_FALLBACKS = (
    "Avenir Next",
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
    "sans-serif",
)
APP_FONT_STACK = (APP_FONT_FAMILY, *APP_FONT_FALLBACKS)
APP_FONT_CSS = ", ".join(
    font if font == "sans-serif" else f'"{font}"'
    for font in APP_FONT_STACK
)
APP_BODY_FONT_SIZE_REM = 0.95
APP_TABLE_FONT_SIZE_REM = 0.875
APP_PAGE_TITLE_FONT_SIZE_REM = 2.25
APP_REPORT_TITLE_FONT_SIZE_REM = 1.65
APP_SECTION_FONT_SIZE_REM = 1.3
APP_SUBSECTION_FONT_SIZE_REM = 1.05
APP_METRIC_LABEL_FONT_SIZE_REM = 0.875
APP_METRIC_VALUE_FONT_SIZE_REM = 1.75
APP_HEADING_FONT_SIZES = (
    f"{APP_PAGE_TITLE_FONT_SIZE_REM}rem",
    f"{APP_REPORT_TITLE_FONT_SIZE_REM}rem",
    f"{APP_SECTION_FONT_SIZE_REM}rem",
    f"{APP_SUBSECTION_FONT_SIZE_REM}rem",
    f"{APP_BODY_FONT_SIZE_REM}rem",
    f"{APP_TABLE_FONT_SIZE_REM}rem",
)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    if len(rgb) != 3 or any(
        isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255
        for channel in rgb
    ):
        raise ValueError(f"Invalid RGB color: {rgb}")
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    normalized = value.removeprefix("#")
    if len(normalized) != 6 or any(character not in string.hexdigits for character in normalized):
        raise ValueError(f"Invalid hex color: {value}")
    return tuple(int(normalized[index:index + 2], 16) for index in (0, 2, 4))

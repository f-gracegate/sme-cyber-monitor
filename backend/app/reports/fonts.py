"""House fonts for generated documents: Poppins for text, Montserrat for headings.

The TrueType files ship with the app (app/assets/fonts, SIL Open Font License) and are embedded
in every PDF, so reports and receipts look the same on any device.
"""

from pathlib import Path

from reportlab import rl_config
from reportlab.graphics import shapes
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import flowables, tables

_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

TEXT = "Poppins"
TEXT_MEDIUM = "Poppins-Medium"
TEXT_BOLD = "Poppins-Bold"
HEADING = "Montserrat-SemiBold"
HEADING_BOLD = "Montserrat-Bold"

_FILES = {
    TEXT: "Poppins_400Regular.ttf",
    TEXT_MEDIUM: "Poppins_500Medium.ttf",
    "Poppins-SemiBold": "Poppins_600SemiBold.ttf",
    TEXT_BOLD: "Poppins_700Bold.ttf",
    "Montserrat-Medium": "Montserrat_500Medium.ttf",
    HEADING: "Montserrat_600SemiBold.ttf",
    HEADING_BOLD: "Montserrat_700Bold.ttf",
}


def register() -> None:
    """Register the fonts once; safe to call repeatedly."""
    if TEXT in pdfmetrics.getRegisteredFontNames():
        return
    for name, filename in _FILES.items():
        pdfmetrics.registerFont(TTFont(name, str(_DIR / filename)))
    # <b> inside paragraphs maps to the bold face of the same family.
    addMapping(TEXT, 0, 0, TEXT)
    addMapping(TEXT, 1, 0, TEXT_BOLD)
    addMapping(TEXT, 0, 1, TEXT)
    addMapping(TEXT, 1, 1, TEXT_BOLD)
    addMapping(HEADING, 0, 0, HEADING)
    addMapping(HEADING, 1, 0, HEADING_BOLD)
    addMapping(HEADING, 0, 1, HEADING)
    addMapping(HEADING, 1, 1, HEADING_BOLD)
    # ReportLab falls back to Helvetica in a few places (each new page, table cells, some
    # flowables). Point all of them at Poppins so no other font is ever embedded.
    rl_config.canvas_basefontname = TEXT
    tables.CellStyle.fontname = TEXT
    flowables._baseFontName = TEXT
    shapes.STATE_DEFAULTS["fontName"] = TEXT  # charts and drawings


register()

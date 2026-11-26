"""Render report content as PDF (ReportLab) or CSV."""

import csv
import io
from datetime import UTC, datetime

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.reports.content import ReportContent

NAVY = colors.HexColor("#101828")
BLUE = colors.HexColor("#2563EB")
MUTED = colors.HexColor("#475467")
BORDER = colors.HexColor("#E2E8F0")
SOFT = colors.HexColor("#F1F5F9")
WIDE_TYPES = {"asset_inventory", "endpoint_health", "findings", "incidents", "remediation"}

_styles = getSampleStyleSheet()
H1 = ParagraphStyle(
    "h1",
    parent=_styles["Title"],
    fontSize=20,
    leading=24,
    textColor=NAVY,
    alignment=TA_LEFT,
    spaceAfter=2,
)
H2 = ParagraphStyle(
    "h2",
    parent=_styles["Heading2"],
    fontSize=13,
    leading=16,
    textColor=NAVY,
    spaceBefore=10,
    spaceAfter=6,
)
BODY = ParagraphStyle(
    "body",
    parent=_styles["BodyText"],
    fontSize=9.5,
    leading=13,
    textColor=colors.HexColor("#1F2937"),
)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10, textColor=MUTED)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8, leading=10)
CELL_HEAD = ParagraphStyle(
    "cellhead", parent=CELL, textColor=colors.white, fontName="Helvetica-Bold"
)
KPI_VALUE = ParagraphStyle(
    "kpi", parent=BODY, fontSize=15, leading=18, textColor=NAVY, fontName="Helvetica-Bold"
)


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kpis(content: ReportContent, width: float):
    if not content.kpis:
        return []
    # Each cell is a stack of three paragraphs: label, value, hint.
    cells = [
        [
            Paragraph(_escape(label), SMALL),
            Paragraph(_escape(value), KPI_VALUE),
            Paragraph(_escape(hint), SMALL),
        ]
        for label, value, hint in content.kpis
    ]
    table = Table([cells], colWidths=[width / len(cells)] * len(cells))
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [table, Spacer(1, 6)]


def _table(t, width: float):
    widths = [width * w for w in (t.widths or [1 / len(t.headers)] * len(t.headers))]
    data = [[Paragraph(_escape(h), CELL_HEAD) for h in t.headers]]
    data += [[Paragraph(_escape(str(v)), CELL) for v in row] for row in t.rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _chart(points: list[tuple[str, int]], width: float):
    drawing = Drawing(width, 120)
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 30, 20, width - 50, 85
    plot.data = [[(i, v) for i, (_, v) in enumerate(points)]]
    plot.lines[0].strokeColor = BLUE
    plot.lines[0].strokeWidth = 2
    plot.yValueAxis.valueMin, plot.yValueAxis.valueMax = 0, 100
    plot.yValueAxis.valueSteps = [0, 25, 50, 75, 100]
    plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 0, max(1, len(points) - 1)
    plot.xValueAxis.visibleLabels = False
    drawing.add(plot)
    drawing.add(String(30, 4, points[0][0], fontSize=7, fillColor=MUTED))
    drawing.add(String(width - 20, 4, points[-1][0], fontSize=7, fillColor=MUTED, textAnchor="end"))
    return drawing


def to_pdf(content: ReportContent, report_type: str) -> bytes:
    buffer = io.BytesIO()
    pagesize = landscape(A4) if report_type in WIDE_TYPES else A4
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{content.title} · {content.organisation}",
        author=settings.brand_product_name,
    )
    width = pagesize[0] - 32 * mm
    generated = datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            16 * mm,
            10 * mm,
            f"{settings.brand_product_name} · Powered by GraceGate Technologies · Confidential",
        )
        canvas.drawRightString(pagesize[0] - 16 * mm, 10 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    story = [
        Paragraph(_escape(settings.brand_product_name.upper()), SMALL),
        Paragraph(_escape(content.title), H1),
        Paragraph(
            f"{_escape(content.organisation)} · {_escape(content.period)} · generated {generated}",
            SMALL,
        ),
        Spacer(1, 10),
        *_kpis(content, width),
    ]
    for section in content.sections:
        block = [Paragraph(_escape(section.heading), H2)]
        block += [Paragraph(_escape(p), BODY) for p in section.paragraphs]
        if section.bullets:
            block.append(
                ListFlowable(
                    [ListItem(Paragraph(_escape(b), BODY), leftIndent=10) for b in section.bullets],
                    bulletType="bullet",
                    start="•",
                    leftIndent=10,
                )
            )
        if section.chart:
            block.append(_chart(section.chart, width))
        story.append(KeepTogether(block))  # heading never stranded from its content
        if section.table:
            story.append(_table(section.table, width))
        story.append(Spacer(1, 4))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def to_csv(content: ReportContent) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(content.csv.headers)
    for row in content.csv.rows:
        # Neutralise spreadsheet formulas in exported text (CSV injection).
        writer.writerow([f"'{v}" if str(v)[:1] in "=+-@" else v for v in row])
    return ("﻿" + out.getvalue()).encode("utf-8")

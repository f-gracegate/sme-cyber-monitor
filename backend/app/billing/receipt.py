"""Payment receipts as PDF."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.billing.service import receipt_label
from app.core.config import settings
from app.models import Organisation, Payment
from app.reports.render import BODY, BORDER, H1, H2, NAVY, SMALL, SOFT, _escape
from app.services.plans import get_plan

CHANNELS = {"mobile_money": "Mobile Money", "card": "Card"}
PERIODS = {"monthly": "Monthly", "annual": "Annual"}


def _method(payment: Payment) -> str:
    m = payment.payment_method or {}
    label = CHANNELS.get(payment.channel, payment.channel)
    if payment.channel == "card" and m.get("last4"):
        return f"{label} · {str(m.get('brand', '')).title()} ending {m['last4']}"
    if payment.channel == "mobile_money" and (m.get("network") or m.get("phone")):
        return f"{label} · {' '.join(str(v) for v in (m.get('network'), m.get('phone')) if v)}"
    return label


def render_receipt(payment: Payment, org: Organisation) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Receipt {receipt_label(payment)}",
        author=settings.brand_company_name,
    )
    width = doc.width
    plan = get_plan(payment.plan_code)
    # Poppins (the text font) has no cedi sign, so amounts use the ISO code.
    amount = f"GHS {payment.amount_minor / 100:,.2f}"
    story = [
        Paragraph("Payment receipt", H1),
        Paragraph(_escape(settings.brand_product_name), SMALL),
        Spacer(1, 8 * mm),
    ]
    details = [
        ("Receipt number", receipt_label(payment)),
        ("Date paid", f"{payment.paid_at:%d %B %Y, %H:%M} UTC" if payment.paid_at else "—"),
        ("Billed to", org.name),
        ("Paid with", _method(payment)),
        ("Payment reference", payment.reference),
    ]
    rows = [[Paragraph(k, SMALL), Paragraph(_escape(v), BODY)] for k, v in details]
    t = Table(rows, colWidths=[45 * mm, width - 45 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
            ]
        )
    )
    story += [t, Spacer(1, 6 * mm), Paragraph("Summary", H2)]
    period = ""
    if payment.period_start and payment.period_end:
        period = f"{payment.period_start:%d %b %Y} – {payment.period_end:%d %b %Y}"
    description = f"{plan.name} plan · {PERIODS.get(payment.billing_period, '')} · {period}"
    if payment.credit_days:
        description += f" (includes {payment.credit_days} days credited from your previous plan)"
    lines = Table(
        [
            [Paragraph("<b>Description</b>", BODY), Paragraph("<b>Amount</b>", BODY)],
            [Paragraph(_escape(description), BODY), Paragraph(amount, BODY)],
            [Paragraph("<b>Total paid</b>", BODY), Paragraph(f"<b>{amount}</b>", BODY)],
        ],
        colWidths=[width - 40 * mm, 40 * mm],
    )
    lines.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDER),
                ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story += [
        lines,
        Spacer(1, 10 * mm),
        Paragraph(
            "Prices are shown in Ghana cedis. This receipt confirms payment; it is not a VAT "
            "invoice.",
            SMALL,
        ),
        Spacer(1, 2 * mm),
        Paragraph(f"Powered by {_escape(settings.brand_company_name)}", SMALL),
    ]
    doc.build(story)
    return buf.getvalue()

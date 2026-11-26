"""Generate reports and store them encrypted. Also the monthly executive report."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Membership, Organisation, Report, User
from app.reports import content, render
from app.security.rbac import Role
from app.services import storage
from app.services.email import send_email

log = logging.getLogger("app.reports")


def generate(
    db: Session,
    org_id: uuid.UUID,
    report_type: str,
    fmt: str,
    start: datetime,
    end: datetime,
    created_by: uuid.UUID | None = None,
    scheduled: bool = False,
) -> Report:
    built = content.build(db, org_id, report_type, start, end)
    data = render.to_csv(built) if fmt == "csv" else render.to_pdf(built, report_type)
    key = storage.put(org_id, "reports", data)
    report = Report(
        organisation_id=org_id,
        report_type=report_type,
        format=fmt,
        title=f"{built.title} · {built.period}",
        period_start=start,
        period_end=end,
        status="ready",
        storage_key=key,
        size_bytes=len(data),
        scheduled=scheduled,
        created_by=created_by,
    )
    db.add(report)
    db.flush()
    return report


def previous_month(now: datetime) -> tuple[datetime, datetime]:
    """[first day of last month, first day of this month)."""
    this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year, month = (
        (this_month.year, this_month.month - 1)
        if this_month.month > 1
        else (this_month.year - 1, 12)
    )
    return this_month.replace(year=year, month=month), this_month


def generate_monthly_reports(db: Session, now: datetime | None = None) -> int:
    """Create last month's executive summary for every organisation that doesn't have one yet,
    and email owners and administrators a link. Safe to run repeatedly."""
    now = now or datetime.now(UTC)
    start, end = previous_month(now)
    created = 0
    orgs = list(db.scalars(select(Organisation).where(Organisation.status == "active")))
    for org in orgs:
        exists = db.scalar(
            select(Report.id).where(
                Report.organisation_id == org.id,
                Report.report_type == "executive",
                Report.scheduled.is_(True),
                Report.period_start == start,
            )
        )
        if exists:
            continue
        try:
            generate(db, org.id, "executive", "pdf", start, end, scheduled=True)
        except Exception:  # noqa: BLE001 - one organisation's failure mustn't stop the rest
            log.exception("monthly report failed for %s", org.id)
            continue
        recipients = list(
            db.scalars(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organisation_id == org.id,
                    Membership.status == "active",
                    Membership.role.in_((Role.OWNER, Role.ADMIN)),
                    User.status == "active",
                )
            )
        )
        db.commit()
        for user in recipients:
            send_email(
                user.email,
                f"{org.name}: your {start:%B %Y} security report is ready",
                f"Your monthly executive security summary for {start:%B %Y} is ready.\n\n"
                f"Download it: {settings.web_base_url}/reports\n\n"
                "It covers your security score, the most important risks, incidents "
                "and what to do next.",
            )
        created += 1
    return created

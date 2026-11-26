"""Management reports: generate, list and download (PDF or CSV)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, org_scope
from app.core.db import get_db
from app.core.errors import APIError, not_found
from app.core.redis import rate_limit
from app.models import Report, User
from app.reports import service
from app.reports.content import CSV_TYPES, REPORT_TYPES
from app.schemas.common import Page
from app.security.rbac import Perm
from app.services import audit, storage

router = APIRouter(tags=["Reports"])

ReportType = Literal[
    "executive",
    "asset_inventory",
    "endpoint_health",
    "findings",
    "incidents",
    "remediation",
    "coverage",
]


class ReportCreate(BaseModel):
    report_type: ReportType
    format: Literal["pdf", "csv"] = "pdf"
    period_start: datetime | None = None
    period_end: datetime | None = None

    @model_validator(mode="after")
    def _check(self) -> "ReportCreate":
        if self.format == "csv" and self.report_type not in CSV_TYPES:
            raise ValueError("This report is only available as PDF.")
        if self.period_start and self.period_end and self.period_end <= self.period_start:
            raise ValueError("The period must end after it starts.")
        return self


class ReportOut(BaseModel):
    id: uuid.UUID
    report_type: str
    type_label: str
    format: str
    title: str
    period_start: datetime
    period_end: datetime
    status: str
    size_bytes: int | None
    scheduled: bool
    created_by_name: str | None
    created_at: datetime


class ReportTypeOut(BaseModel):
    value: str
    label: str
    csv: bool


def _out(db: Session, r: Report) -> ReportOut:
    user = db.get(User, r.created_by) if r.created_by else None
    return ReportOut(
        id=r.id,
        report_type=r.report_type,
        type_label=REPORT_TYPES[r.report_type],
        format=r.format,
        title=r.title,
        period_start=r.period_start,
        period_end=r.period_end,
        status=r.status,
        size_bytes=r.size_bytes,
        scheduled=r.scheduled,
        created_by_name=(user.full_name or user.email)
        if user
        else ("Monthly schedule" if r.scheduled else None),
        created_at=r.created_at,
    )


@router.get("/reports/types", response_model=list[ReportTypeOut])
def report_types(_: OrgContext = Depends(org_scope(Perm.REPORTS_READ))) -> list[ReportTypeOut]:
    return [ReportTypeOut(value=k, label=v, csv=k in CSV_TYPES) for k, v in REPORT_TYPES.items()]


@router.get("/reports", response_model=Page[ReportOut])
def list_reports(
    ctx: OrgContext = Depends(org_scope(Perm.REPORTS_READ)),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> Page[ReportOut]:
    stmt = select(Report).where(Report.organisation_id == ctx.org_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Report.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[ReportOut](
        items=[_out(db, r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(
    body: ReportCreate,
    ctx: OrgContext = Depends(org_scope(Perm.REPORTS_READ)),
    db: Session = Depends(get_db),
) -> ReportOut:
    rate_limit(f"reports:{ctx.org_id}", limit=30, window_seconds=3600)
    end = body.period_end or datetime.now(UTC)
    start = body.period_start or end - timedelta(days=30)
    if end - start > timedelta(days=366):
        raise APIError(422, "validation_error", "Reports can cover up to one year.")
    report = service.generate(
        db, ctx.org_id, body.report_type, body.format, start, end, created_by=ctx.user.id
    )
    audit.record(
        db,
        "report.generated",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="report",
        resource_id=report.id,
        details={"type": body.report_type, "format": body.format},
        request=ctx.request,
    )
    db.commit()
    return _out(db, report)


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: uuid.UUID,
    ctx: OrgContext = Depends(org_scope(Perm.REPORTS_READ)),
    db: Session = Depends(get_db),
) -> Response:
    report = db.get(Report, report_id)
    if report is None or report.organisation_id != ctx.org_id or not report.storage_key:
        raise not_found("Report")
    data = storage.get(ctx.org_id, report.storage_key)
    audit.record(
        db,
        "report.downloaded",
        actor=ctx.user,
        organisation_id=ctx.org_id,
        resource_type="report",
        resource_id=report.id,
        request=ctx.request,
    )
    db.commit()
    name = f"{report.report_type}-{report.period_end:%Y-%m-%d}.{report.format}"
    return Response(
        content=data,
        media_type="application/pdf" if report.format == "pdf" else "text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )

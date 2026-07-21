"""
Green Curve — Pricing request / contact form endpoint.
Stores submission in SQLite and optionally emails kneha2381@gmail.com
if SMTP env vars are configured.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, EmailStr

import graph_mailer
from db import get_conn

logger = logging.getLogger("greencurve.contact")

router = APIRouter(prefix="/api", tags=["contact"])


def _ensure_table():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pricing_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                company     TEXT    NOT NULL,
                email       TEXT    NOT NULL,
                phone       TEXT,
                role        TEXT,
                company_size TEXT,
                use_case    TEXT,
                message     TEXT
            )
        """)


_ensure_table()


class PricingRequest(BaseModel):
    name:         str
    company:      str
    email:        EmailStr
    phone:        str = ""
    role:         str = ""
    company_size: str = ""
    use_case:     str = ""
    message:      str = ""


def _send_email(req: PricingRequest, row_id: int):
    notify_to = os.environ.get("NOTIFY_EMAIL", "kneha2381@gmail.com")

    body = f"""New pricing request #{row_id} — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

Name:         {req.name}
Company:      {req.company}
Email:        {req.email}
Phone:        {req.phone or '—'}
Role:         {req.role or '—'}
Company size: {req.company_size or '—'}
Use case:     {req.use_case or '—'}

Message:
{req.message or '(none)'}
"""
    if graph_mailer.send_mail(notify_to, f"[Green Curve] Pricing Request — {req.company}", body):
        logger.info("Pricing request email sent for %s <%s>", req.company, req.email)
    else:
        logger.warning("Pricing request email not sent (mailer not configured or failed)")


@router.post("/pricing-request")
async def pricing_request(req: PricingRequest, background_tasks: BackgroundTasks):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO pricing_requests
           (created_at, name, company, email, phone, role, company_size, use_case, message)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (now, req.name, req.company, str(req.email),
         req.phone, req.role, req.company_size, req.use_case, req.message),
    )
    conn.commit()
    row_id = cur.lastrowid
    logger.info("Pricing request #%d saved — %s <%s> @ %s", row_id, req.name, req.email, req.company)
    # SMTP can take several seconds (TLS handshake + login). Run it after the
    # response is sent — Starlette executes sync background tasks in a threadpool,
    # so neither the event loop nor the client request blocks on email delivery.
    background_tasks.add_task(_send_email, req, row_id)
    return {"ok": True, "id": row_id}

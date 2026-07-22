"""
Green Curve — outbound mail via Resend.

Replaces an earlier Microsoft Graph attempt (kept in git history): Graph
sendMail was correctly configured (Mail.Send granted, Application Access
Policy valid, token carried the right role) but was blocked tenant-wide by
something outside our own admin visibility — most likely a restriction
imposed by GoDaddy as this M365 tenant's delegated admin partner. Rather
than chase that further, app-originated mail now goes through Resend on an
isolated subdomain (mail.greencurve.solutions), completely separate from
the SPF/DKIM the human mailboxes (neha@/kdr@) depend on.

Required env var: RESEND_API_KEY.
Optional: MAIL_FROM (defaults to a mail.greencurve.solutions address).
"""

import base64
import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger("greencurve.mailer")

_SEND_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "Green Curve <noreply@mail.greencurve.solutions>"


def ready() -> bool:
    return bool(os.environ.get("RESEND_API_KEY"))


def send_mail(to_addr: str, subject: str, body: str, ics: Optional[str] = None,
              from_addr: Optional[str] = None) -> bool:
    """Best-effort send: logs and returns False on any failure, never raises."""
    if not ready() or not to_addr:
        return False

    sender = from_addr or os.environ.get("MAIL_FROM", _DEFAULT_FROM)
    # header-injection guard: no CR/LF may ever reach a header value
    subject = re.sub(r"[\r\n]+", " ", subject)
    to_addr = to_addr.strip().splitlines()[0]

    payload = {
        "from": sender,
        "to": [to_addr],
        "subject": subject,
        "text": body,
    }
    if ics:
        payload["attachments"] = [{
            "filename": "invite.ics",
            "content": base64.b64encode(ics.encode("utf-8")).decode("ascii"),
        }]

    try:
        resp = requests.post(
            _SEND_URL,
            headers={
                "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Mail to <redacted> failed: %s", exc)
        return False

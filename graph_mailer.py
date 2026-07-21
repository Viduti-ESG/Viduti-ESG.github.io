"""
Green Curve — outbound mail via Microsoft Graph (application permissions).

Replaces legacy SMTP AUTH, which the M365 tenant's Security defaults block
outright (Security defaults enforces MFA + disables basic auth for legacy
protocols like SMTP AUTH — app passwords do NOT bypass this). Instead this
authenticates as the "GreenCurve-Mailer" Entra app registration via the
OAuth2 client-credentials flow and calls Graph's /sendMail, scoped by an
Exchange Application Access Policy to only the neha@/kdr@ mailboxes.

Required env vars: GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET.
Optional: MAIL_FROM (defaults to neha@greencurve.solutions — must be one of
the mailboxes covered by the MailerScope access policy).
"""

import base64
import logging
import os
import re
import time
from typing import Optional

import requests

logger = logging.getLogger("greencurve.graph_mailer")

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"

_token_cache = {"value": None, "expires_at": 0.0}


def ready() -> bool:
    return bool(
        os.environ.get("GRAPH_TENANT_ID")
        and os.environ.get("GRAPH_CLIENT_ID")
        and os.environ.get("GRAPH_CLIENT_SECRET")
    )


def _get_token() -> Optional[str]:
    if _token_cache["value"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["value"]

    tenant_id = os.environ["GRAPH_TENANT_ID"]
    resp = requests.post(
        _TOKEN_URL.format(tenant=tenant_id),
        data={
            "client_id": os.environ["GRAPH_CLIENT_ID"],
            "client_secret": os.environ["GRAPH_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["value"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
    return _token_cache["value"]


def send_mail(to_addr: str, subject: str, body: str, ics: Optional[str] = None,
              from_addr: Optional[str] = None) -> bool:
    """Best-effort send: logs and returns False on any failure, never raises."""
    if not ready() or not to_addr:
        return False

    sender = from_addr or os.environ.get("MAIL_FROM", "neha@greencurve.solutions")
    # header-injection guard: no CR/LF may ever reach a header value
    subject = re.sub(r"[\r\n]+", " ", subject)
    to_addr = to_addr.strip().splitlines()[0]

    message = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to_addr}}],
        },
        "saveToSentItems": "false",
    }
    if ics:
        message["message"]["attachments"] = [{
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": "invite.ics",
            "contentType": "text/calendar",
            "contentBytes": base64.b64encode(ics.encode("utf-8")).decode("ascii"),
        }]

    try:
        token = _get_token()
        if not token:
            return False
        resp = requests.post(
            _SEND_URL.format(sender=sender),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=message,
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Graph mail to <redacted> failed: %s", exc)
        return False

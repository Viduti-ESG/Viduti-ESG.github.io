#!/usr/bin/env python3
"""Green Curve daily Anthropic API usage/cost report (Admin API).

Emails a summary of yesterday's Anthropic token usage and USD cost, broken
down per API key (i.e. per staff member, if each staff member has their own
key named after them in the Console).

Requires:
  ANTHROPIC_ADMIN_KEY  — an Admin API key (sk-ant-admin01-...), separate from
                          the regular ANTHROPIC_API_KEY. Create one at
                          console.anthropic.com -> Settings -> Admin API Keys.
  SMTP_HOST / SMTP_USER / SMTP_PASS (SMTP_PORT optional, default 587)
                          — same convention as booking_api.py / contact_api.

Optional:
  USAGE_REPORT_TO      — recipient email (default: neha@greencurve.solutions)

There is currently no Anthropic API for remaining prepaid credit balance —
only token usage and billed USD cost are queryable. The report notes this
and links to the Console billing page instead of guessing a number.

Exit codes: 0 = sent, 3 = dormant (admin key or SMTP not configured yet,
not an error in monitoring terms), 1 = real failure.

Run from the site root:  venv/bin/python tools/anthropic_usage_report.py
Designed for the gc-usage-report systemd timer (User=www-data,
EnvironmentFile=/var/www/greencurve/.env).
"""
import argparse
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TO = "neha@greencurve.solutions"

# $ per million tokens (input, output) — see shared/models.md for updates.
PRICING = {
    "claude-opus-4-8":     (5.00, 25.00),
    "claude-opus-4-7":     (5.00, 25.00),
    "claude-opus-4-6":     (5.00, 25.00),
    "claude-opus-4-5":     (5.00, 25.00),
    "claude-sonnet-5":     (3.00, 15.00),
    "claude-sonnet-4-6":   (3.00, 15.00),
    "claude-sonnet-4-5":   (3.00, 15.00),
    "claude-haiku-4-5":    (1.00, 5.00),
}


def _admin_headers(admin_key: str) -> dict:
    return {"anthropic-version": ANTHROPIC_VERSION, "x-api-key": admin_key}


def fetch_api_key_names(admin_key: str) -> dict:
    """id -> display name, for every API key in the org (paginated)."""
    names, page = {}, None
    while True:
        params = {"limit": 1000}
        if page:
            params["after_id"] = page
        resp = requests.get(f"{API_BASE}/organizations/api_keys",
                             headers=_admin_headers(admin_key), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for k in data["data"]:
            names[k["id"]] = k["name"]
        if not data.get("has_more"):
            break
        page = data["last_id"]
    return names


def fetch_usage(admin_key: str, start: datetime, end: datetime) -> list:
    """Per-day usage grouped by api_key_id + model."""
    params = {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1d",
        "group_by[]": ["api_key_id", "model"],
    }
    buckets, page = [], None
    while True:
        q = dict(params)
        if page:
            q["page"] = page
        resp = requests.get(f"{API_BASE}/organizations/usage_report/messages",
                             headers=_admin_headers(admin_key), params=q, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        buckets.extend(data.get("data", []))
        if not data.get("has_more"):
            break
        page = data["next_page"]
    return buckets


def fetch_total_cost_usd(admin_key: str, start: datetime, end: datetime) -> float:
    """Actual billed USD for the window (org-wide, exact — not per-key)."""
    params = {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    total_cents = 0
    page = None
    while True:
        q = dict(params)
        if page:
            q["page"] = page
        resp = requests.get(f"{API_BASE}/organizations/cost_report",
                             headers=_admin_headers(admin_key), params=q, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for bucket in data.get("data", []):
            for item in bucket.get("results", []):
                total_cents += float(item.get("amount", 0))
        if not data.get("has_more"):
            break
        page = data["next_page"]
    return total_cents / 100.0


def fetch_cost_by_day(admin_key: str, start: datetime, end: datetime) -> dict:
    """date (YYYY-MM-DD) -> billed USD. Used by --breakdown to find where spend went."""
    params = {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    by_day, page = {}, None
    while True:
        q = dict(params)
        if page:
            q["page"] = page
        resp = requests.get(f"{API_BASE}/organizations/cost_report",
                             headers=_admin_headers(admin_key), params=q, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for bucket in data.get("data", []):
            day = (bucket.get("starting_at") or "")[:10]
            cents = sum(float(i.get("amount", 0)) for i in bucket.get("results", []))
            by_day[day] = by_day.get(day, 0.0) + cents / 100.0
        if not data.get("has_more"):
            break
        page = data["next_page"]
    return by_day


def summarize(buckets: list, key_names: dict) -> tuple[dict, dict]:
    """Returns (per_staff, per_model) each mapping name -> {tokens, cost_usd}."""
    per_staff, per_model = {}, {}
    for bucket in buckets:
        for row in bucket.get("results", []):
            key_id = row.get("api_key_id")
            model = row.get("model", "unknown")
            staff = key_names.get(key_id, "(no API key / Workbench)") if key_id else "(no API key / Workbench)"
            tokens_in = (row.get("uncached_input_tokens", 0) or 0) + (row.get("cache_creation", {}).get("input_tokens", 0) if isinstance(row.get("cache_creation"), dict) else 0)
            tokens_cached = row.get("cache_read_input_tokens", 0) or 0
            tokens_out = row.get("output_tokens", 0) or 0
            in_price, out_price = PRICING.get(model, (0.0, 0.0))
            cost = (tokens_in / 1_000_000 * in_price) + (tokens_out / 1_000_000 * out_price) + (tokens_cached / 1_000_000 * in_price * 0.1)
            total_tokens = tokens_in + tokens_cached + tokens_out

            s = per_staff.setdefault(staff, {"tokens": 0, "cost_usd": 0.0})
            s["tokens"] += total_tokens
            s["cost_usd"] += cost

            m = per_model.setdefault(model, {"tokens": 0, "cost_usd": 0.0})
            m["tokens"] += total_tokens
            m["cost_usd"] += cost
    return per_staff, per_model


def build_email(report_date: str, total_cost_usd: float, per_staff: dict, per_model: dict) -> str:
    lines = [
        f"Green Curve — Anthropic API usage for {report_date} (UTC)",
        "",
        f"Total billed cost: ${total_cost_usd:,.2f}",
        "",
        "Remaining prepaid credit balance is not exposed by any Anthropic API —",
        "check console.anthropic.com -> Settings -> Billing for the current balance.",
        "",
        "By staff (API key):",
    ]
    if not per_staff:
        lines.append("  (no usage recorded)")
    for name, s in sorted(per_staff.items(), key=lambda kv: -kv[1]["cost_usd"]):
        lines.append(f"  {name:<30} {s['tokens']:>10,} tokens   ~${s['cost_usd']:.2f} (estimated)")
    lines += ["", "By model:"]
    for model, m in sorted(per_model.items(), key=lambda kv: -kv[1]["cost_usd"]):
        lines.append(f"  {model:<30} {m['tokens']:>10,} tokens   ~${m['cost_usd']:.2f} (estimated)")
    lines += [
        "",
        "Per-staff and per-model $ figures above are estimated from token counts",
        "at published list pricing (see shared/models.md) and may not exactly",
        "match the billed total above (which comes straight from Anthropic).",
    ]
    return "\n".join(lines)


def send_mail(subject: str, body: str, to_addr: str):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    if not smtp_host or not smtp_user:
        print("DORMANT: SMTP_HOST/SMTP_USER not set — skipping send.")
        sys.exit(3)
    msg = MIMEMultipart()
    msg["Subject"], msg["From"], msg["To"] = subject, smtp_user, to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.sendmail(smtp_user, [to_addr], msg.as_string())


def main() -> int:
    ap = argparse.ArgumentParser(description="Anthropic usage/cost report")
    ap.add_argument("--days", type=int, default=1,
                    help="how many days back to cover (default 1 = yesterday)")
    ap.add_argument("--print", dest="to_stdout", action="store_true",
                    help="print to screen instead of emailing (works without SMTP)")
    ap.add_argument("--breakdown", action="store_true",
                    help="also show cost per day — use this to find where spend went")
    args = ap.parse_args()

    admin_key = os.environ.get("ANTHROPIC_ADMIN_KEY", "")
    if not admin_key:
        print("DORMANT: ANTHROPIC_ADMIN_KEY not set — create one at "
              "console.anthropic.com -> Settings -> Admin API Keys.")
        sys.exit(3)

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=args.days)
    end = today + timedelta(days=1)          # include today's partial usage
    report_date = (start.strftime("%Y-%m-%d") if args.days == 1
                   else f"{start:%Y-%m-%d} to {today:%Y-%m-%d}")

    key_names = fetch_api_key_names(admin_key)
    buckets = fetch_usage(admin_key, start, end)
    total_cost_usd = fetch_total_cost_usd(admin_key, start, end)
    per_staff, per_model = summarize(buckets, key_names)

    body = build_email(report_date, total_cost_usd, per_staff, per_model)

    if args.breakdown:
        by_day = fetch_cost_by_day(admin_key, start, end)
        lines = ["", "Cost per day:"]
        for day in sorted(by_day):
            if by_day[day] > 0:
                lines.append(f"  {day}   ${by_day[day]:>8.2f}  {'#' * int(by_day[day] * 2)}")
        body += "\n".join(lines)

    if args.to_stdout:
        print(body)
        return 0

    to_addr = os.environ.get("USAGE_REPORT_TO", DEFAULT_TO)
    send_mail(f"Green Curve — Anthropic API usage, {report_date}", body, to_addr)
    print(f"Sent usage report for {report_date} to {to_addr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

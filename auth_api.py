"""
Green Curve — Auth & User Data API
Endpoints: /api/auth/* and /api/user/*

Install deps (add to requirements.txt):
    pip install python-jose[cryptography] bcrypt passlib[bcrypt]
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from db import get_conn, init_db

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET", "gc-dev-secret-change-in-production")
ALGORITHM  = "HS256"
TOKEN_DAYS = 7

router  = APIRouter()
bearer  = HTTPBearer(auto_error=False)

# ── DB init on import ─────────────────────────────────────────────────────────
init_db()


# ── Pydantic models ───────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    email:    EmailStr
    name:     str
    org:      str = ""
    password: str

class LoginIn(BaseModel):
    email:    EmailStr
    password: str

class WatchlistAddIn(BaseModel):
    company_name: str

class CAPUpdateIn(BaseModel):
    status:   Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    notes:    Optional[str] = None

class PrefsIn(BaseModel):
    prefs: dict

class SnapshotIn(BaseModel):
    company_name:  str
    snapshot_data: dict


# ── Token helpers ─────────────────────────────────────────────────────────────
def _make_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"sub": str(user_id), "email": email, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(creds.credentials)
    user_id = int(payload["sub"])
    with get_conn() as conn:
        row = conn.execute("SELECT id, email, name, org FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)


# ── Auth endpoints ─────────────────────────────────────────────────────────────
@router.post("/api/auth/register", status_code=201)
def register(body: RegisterIn):
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    pw_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, name, org, password_hash) VALUES (?,?,?,?)",
                (body.email.lower(), body.name.strip(), body.org.strip(), pw_hash)
            )
            user_id = cur.lastrowid
    except Exception:
        raise HTTPException(409, "Email already registered")
    token = _make_token(user_id, body.email.lower())
    return {"token": token, "user": {"id": user_id, "email": body.email.lower(), "name": body.name, "org": body.org}}


@router.post("/api/auth/login")
def login(body: LoginIn):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, email, name, org, password_hash FROM users WHERE email=? AND is_active=1",
            (body.email.lower(),)
        ).fetchone()
    if not row or not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise HTTPException(401, "Invalid email or password")
    token = _make_token(row["id"], row["email"])
    return {"token": token, "user": {"id": row["id"], "email": row["email"], "name": row["name"], "org": row["org"]}}


@router.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return {"user": user}


# ── Watchlist endpoints ────────────────────────────────────────────────────────
@router.get("/api/user/watchlist")
def get_watchlist(user=Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT company_name FROM watchlist WHERE user_id=? ORDER BY added_at",
            (user["id"],)
        ).fetchall()
    return {"watchlist": [r["company_name"] for r in rows]}


@router.post("/api/user/watchlist", status_code=201)
def add_to_watchlist(body: WatchlistAddIn, user=Depends(get_current_user)):
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist (user_id, company_name) VALUES (?,?)",
                (user["id"], body.company_name)
            )
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


@router.delete("/api/user/watchlist/{company_name}")
def remove_from_watchlist(company_name: str, user=Depends(get_current_user)):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id=? AND company_name=?",
            (user["id"], company_name)
        )
    return {"ok": True}


# ── Watchlist snapshots ────────────────────────────────────────────────────────
@router.get("/api/user/watchlist/snapshots")
def get_snapshots(user=Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT company_name, snapshot_data FROM watchlist_snapshots WHERE user_id=?",
            (user["id"],)
        ).fetchall()
    result = {}
    for r in rows:
        try:
            result[r["company_name"]] = json.loads(r["snapshot_data"])
        except Exception:
            pass
    return {"snapshots": result}


@router.post("/api/user/watchlist/snapshots", status_code=201)
def save_snapshot(body: SnapshotIn, user=Depends(get_current_user)):
    data_str = json.dumps(body.snapshot_data)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM watchlist_snapshots WHERE user_id=? AND company_name=?",
            (user["id"], body.company_name)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE watchlist_snapshots SET snapshot_data=?, created_at=CURRENT_TIMESTAMP WHERE user_id=? AND company_name=?",
                (data_str, user["id"], body.company_name)
            )
        else:
            conn.execute(
                "INSERT INTO watchlist_snapshots (user_id, company_name, snapshot_data) VALUES (?,?,?)",
                (user["id"], body.company_name, data_str)
            )
    return {"ok": True}


# ── Watchlist prefs ────────────────────────────────────────────────────────────
@router.get("/api/user/watchlist/prefs")
def get_prefs(user=Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT prefs_json FROM watchlist_prefs WHERE user_id=?",
            (user["id"],)
        ).fetchone()
    if not row:
        return {"prefs": {"tier_change": True, "high_risk": True}}
    try:
        return {"prefs": json.loads(row["prefs_json"])}
    except Exception:
        return {"prefs": {"tier_change": True, "high_risk": True}}


@router.put("/api/user/watchlist/prefs")
def update_prefs(body: PrefsIn, user=Depends(get_current_user)):
    data_str = json.dumps(body.prefs)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO watchlist_prefs (user_id, prefs_json) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET prefs_json=excluded.prefs_json",
            (user["id"], data_str)
        )
    return {"ok": True}


# ── CAP progress endpoints ─────────────────────────────────────────────────────
@router.get("/api/user/cap")
def get_cap(user=Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT company_name, rec_id, status, assignee, due_date, notes FROM cap_progress WHERE user_id=?",
            (user["id"],)
        ).fetchall()
    # Return as nested dict: { company_name: { rec_id: {status, assignee, due_date, notes} } }
    result: dict = {}
    for r in rows:
        c = r["company_name"]
        if c not in result:
            result[c] = {}
        result[c][r["rec_id"]] = {
            "status":   r["status"],
            "assignee": r["assignee"],
            "due_date": r["due_date"],
            "notes":    r["notes"],
        }
    return {"cap": result}


@router.put("/api/user/cap/{company_name}/{rec_id}")
def update_cap(company_name: str, rec_id: str, body: CAPUpdateIn, user=Depends(get_current_user)):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT status, assignee, due_date, notes FROM cap_progress WHERE user_id=? AND company_name=? AND rec_id=?",
            (user["id"], company_name, rec_id)
        ).fetchone()
        if existing:
            new_status   = body.status   if body.status   is not None else existing["status"]
            new_assignee = body.assignee if body.assignee is not None else existing["assignee"]
            new_due_date = body.due_date if body.due_date is not None else existing["due_date"]
            new_notes    = body.notes    if body.notes    is not None else existing["notes"]
            conn.execute(
                "UPDATE cap_progress SET status=?, assignee=?, due_date=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND company_name=? AND rec_id=?",
                (new_status, new_assignee, new_due_date, new_notes, user["id"], company_name, rec_id)
            )
        else:
            conn.execute(
                "INSERT INTO cap_progress (user_id, company_name, rec_id, status, assignee, due_date, notes) VALUES (?,?,?,?,?,?,?)",
                (user["id"], company_name, rec_id,
                 body.status   or "Not Started",
                 body.assignee or "",
                 body.due_date or "",
                 body.notes    or "")
            )
    return {"ok": True}

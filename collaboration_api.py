"""
Green Curve — Collaboration & Teams API.
Endpoints under /api/collab/*

Pillar 3 of the retention ecosystem: turn single-user tools into a team workflow.
Once a consultancy's whole team works inside Green Curve — co-authoring BRSR reports,
sharing Data Room evidence, assigning tasks, commenting — the switching cost becomes
retraining the entire team, not just one user.

Design is ADDITIVE and non-breaking:
  - Data Room (dr_*) and BRSR (brsr_*) resources stay owner-keyed by user_id.
  - A resource owner may SHARE a resource with a team at 'view' or 'edit' permission.
  - Team members then gain exactly that access — nothing is exposed unless shared, so
    the existing per-user isolation guarantees still hold for anything not shared.

This module owns the shared access helpers (`can_view` / `can_edit`) that dataroom_api
and brsr_workspace_api import. It depends only on db + auth_api, so there is no import
cycle (collaboration never imports those feature modules).

Legal: this is workflow/account data (team membership, comments, tasks) — covered by the
same DPDP basis as the rest of the platform. No new regulatory regime (unlike the
AMC-facing investor portal, which is deliberately deferred).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from db import get_conn
from auth_api import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

ROLES = {"owner", "admin", "editor", "viewer"}
MANAGE_ROLES = {"owner", "admin"}          # can invite / remove / share
RESOURCE_TYPES = {"dataroom_doc", "brsr_report"}
# Ownership lookup per resource type — couples to table names but avoids an import cycle.
_OWNER_SQL = {
    "dataroom_doc": "SELECT user_id FROM dr_documents WHERE id=?",
    "brsr_report":  "SELECT user_id FROM brsr_reports WHERE id=?",
}


# ── Schema ──────────────────────────────────────────────────────────────────────
def init_collab_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                owner_id   INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS team_members (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id       INTEGER NOT NULL,
                user_id       INTEGER,                 -- NULL until an invite is accepted
                invited_email TEXT    DEFAULT '',
                role          TEXT    DEFAULT 'viewer', -- owner|admin|editor|viewer
                status        TEXT    DEFAULT 'invited',-- invited|active
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tm_team_user  ON team_members(team_id, user_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tm_team_email ON team_members(team_id, invited_email);
            CREATE INDEX IF NOT EXISTS idx_tm_user  ON team_members(user_id);
            CREATE INDEX IF NOT EXISTS idx_tm_email ON team_members(invited_email);

            CREATE TABLE IF NOT EXISTS resource_shares (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id       INTEGER NOT NULL,
                resource_type TEXT    NOT NULL,
                resource_id   INTEGER NOT NULL,
                permission    TEXT    DEFAULT 'view',  -- view|edit
                shared_by     INTEGER NOT NULL,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id),
                UNIQUE(team_id, resource_type, resource_id)
            );
            CREATE INDEX IF NOT EXISTS idx_shares_res ON resource_shares(resource_type, resource_id);

            CREATE TABLE IF NOT EXISTS collab_comments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_type TEXT    NOT NULL,
                resource_id   INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                author_email  TEXT    DEFAULT '',
                body          TEXT    NOT NULL,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_comments_res ON collab_comments(resource_type, resource_id);

            CREATE TABLE IF NOT EXISTS collab_tasks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_type TEXT    DEFAULT '',
                resource_id   INTEGER,
                title         TEXT    NOT NULL,
                assignee_email TEXT   DEFAULT '',
                status        TEXT    DEFAULT 'open',  -- open|doing|done
                due_date      TEXT    DEFAULT '',
                created_by    INTEGER NOT NULL,
                created_email TEXT    DEFAULT '',
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON collab_tasks(assignee_email);
            CREATE INDEX IF NOT EXISTS idx_tasks_res      ON collab_tasks(resource_type, resource_id);
        """)


init_collab_db()


# ── Time helper ───────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ════════════════════════════════════════════════════════════════════════════════
#  SHARED ACCESS HELPERS  (imported by dataroom_api and brsr_workspace_api)
# ════════════════════════════════════════════════════════════════════════════════
def _resolve_invites(conn, user: dict) -> None:
    """Attach any pending email invites to this user's id on their first interaction."""
    conn.execute(
        """UPDATE team_members SET user_id=?, status='active'
           WHERE user_id IS NULL AND lower(invited_email)=lower(?)""",
        (user["id"], user["email"]),
    )


def user_team_ids(conn, user_id: int) -> list:
    rows = conn.execute(
        "SELECT team_id FROM team_members WHERE user_id=? AND status='active'", (user_id,)
    ).fetchall()
    return [r["team_id"] for r in rows]


def _share_permission(conn, user_id: int, rtype: str, rid: int) -> Optional[str]:
    """Highest share permission this user has for a resource via team membership, or None."""
    teams = user_team_ids(conn, user_id)
    if not teams:
        return None
    qmarks = ",".join("?" * len(teams))
    rows = conn.execute(
        f"""SELECT permission FROM resource_shares
            WHERE resource_type=? AND resource_id=? AND team_id IN ({qmarks})""",
        (rtype, rid, *teams),
    ).fetchall()
    perms = {r["permission"] for r in rows}
    if "edit" in perms:
        return "edit"
    if "view" in perms:
        return "view"
    return None


def can_view(conn, user_id: int, rtype: str, rid: int) -> bool:
    owner = _resource_owner(conn, rtype, rid)
    if owner == user_id:
        return True
    return _share_permission(conn, user_id, rtype, rid) is not None


def can_edit(conn, user_id: int, rtype: str, rid: int) -> bool:
    owner = _resource_owner(conn, rtype, rid)
    if owner == user_id:
        return True
    return _share_permission(conn, user_id, rtype, rid) == "edit"


def _resource_owner(conn, rtype: str, rid: int) -> Optional[int]:
    sql = _OWNER_SQL.get(rtype)
    if not sql:
        return None
    row = conn.execute(sql, (rid,)).fetchone()
    return row["user_id"] if row else None


# ── internal team helpers ──────────────────────────────────────────────────────
def _my_membership(conn, team_id: int, user_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM team_members WHERE team_id=? AND user_id=? AND status='active'",
        (team_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def _require_member(conn, team_id: int, user_id: int) -> dict:
    m = _my_membership(conn, team_id, user_id)
    if not m:
        raise HTTPException(403, "You are not a member of this team")
    return m


def _require_manager(conn, team_id: int, user_id: int) -> dict:
    m = _require_member(conn, team_id, user_id)
    if m["role"] not in MANAGE_ROLES:
        raise HTTPException(403, "Only team owners or admins can do this")
    return m


# ── Pydantic models ───────────────────────────────────────────────────────────────
class TeamIn(BaseModel):
    name: str

class InviteIn(BaseModel):
    email: EmailStr
    role:  str = "editor"

class RoleIn(BaseModel):
    role: str

class ShareIn(BaseModel):
    team_id:       int
    resource_type: str
    resource_id:   int
    permission:    str = "view"

class CommentIn(BaseModel):
    resource_type: str
    resource_id:   int
    body:          str

class TaskIn(BaseModel):
    title:         str
    assignee_email: str = ""
    due_date:      str = ""
    resource_type: str = ""
    resource_id:   Optional[int] = None

class TaskUpdateIn(BaseModel):
    status:   Optional[str] = None
    title:    Optional[str] = None
    assignee_email: Optional[str] = None
    due_date: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════════
#  TEAMS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/collab/teams")
def my_teams(user=Depends(get_current_user)):
    conn = get_conn()
    with conn:
        _resolve_invites(conn, user)
    rows = conn.execute(
        """SELECT t.id, t.name, t.owner_id, tm.role,
                  (SELECT COUNT(*) FROM team_members x WHERE x.team_id=t.id) AS member_count
           FROM teams t JOIN team_members tm ON tm.team_id=t.id
           WHERE tm.user_id=? AND tm.status='active' ORDER BY t.name""",
        (user["id"],),
    ).fetchall()
    return {"teams": [dict(r) for r in rows]}


@router.post("/api/collab/teams", status_code=201)
def create_team(body: TeamIn, user=Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Team name is required")
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO teams (name, owner_id) VALUES (?,?)", (name, user["id"]))
        tid = cur.lastrowid
        conn.execute(
            """INSERT INTO team_members (team_id, user_id, invited_email, role, status)
               VALUES (?,?,?,?,'active')""",
            (tid, user["id"], user["email"], "owner"),
        )
    return {"ok": True, "team_id": tid}


@router.get("/api/collab/teams/{team_id}/members")
def list_members(team_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    _require_member(conn, team_id, user["id"])
    rows = conn.execute(
        """SELECT tm.id, tm.role, tm.status, tm.invited_email,
                  u.email AS user_email, u.name AS user_name
           FROM team_members tm LEFT JOIN users u ON u.id=tm.user_id
           WHERE tm.team_id=? ORDER BY tm.role, tm.created_at""",
        (team_id,),
    ).fetchall()
    return {"members": [dict(r) for r in rows]}


@router.post("/api/collab/teams/{team_id}/invite", status_code=201)
def invite_member(team_id: int, body: InviteIn, user=Depends(get_current_user)):
    if body.role not in ROLES or body.role == "owner":
        raise HTTPException(400, "role must be admin, editor or viewer")
    conn = get_conn()
    _require_manager(conn, team_id, user["id"])
    email = body.email.lower()
    # If the invitee already has an account, link immediately as active.
    existing_user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    uid = existing_user["id"] if existing_user else None
    status_ = "active" if uid else "invited"
    try:
        with conn:
            conn.execute(
                """INSERT INTO team_members (team_id, user_id, invited_email, role, status)
                   VALUES (?,?,?,?,?)""",
                (team_id, uid, email, body.role, status_),
            )
    except Exception:
        raise HTTPException(409, "That person is already a member or invited")
    return {"ok": True, "status": status_}


@router.put("/api/collab/teams/{team_id}/members/{member_id}/role")
def change_role(team_id: int, member_id: int, body: RoleIn, user=Depends(get_current_user)):
    if body.role not in ROLES or body.role == "owner":
        raise HTTPException(400, "role must be admin, editor or viewer")
    conn = get_conn()
    _require_manager(conn, team_id, user["id"])
    target = conn.execute(
        "SELECT role FROM team_members WHERE id=? AND team_id=?", (member_id, team_id)
    ).fetchone()
    if not target:
        raise HTTPException(404, "Member not found")
    if target["role"] == "owner":
        raise HTTPException(400, "Cannot change the owner's role")
    with conn:
        conn.execute("UPDATE team_members SET role=? WHERE id=? AND team_id=?",
                     (body.role, member_id, team_id))
    return {"ok": True}


@router.delete("/api/collab/teams/{team_id}/members/{member_id}")
def remove_member(team_id: int, member_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    _require_manager(conn, team_id, user["id"])
    target = conn.execute(
        "SELECT role FROM team_members WHERE id=? AND team_id=?", (member_id, team_id)
    ).fetchone()
    if not target:
        raise HTTPException(404, "Member not found")
    if target["role"] == "owner":
        raise HTTPException(400, "Cannot remove the team owner")
    with conn:
        conn.execute("DELETE FROM team_members WHERE id=? AND team_id=?", (member_id, team_id))
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════════
#  SHARING
# ════════════════════════════════════════════════════════════════════════════════
@router.post("/api/collab/share", status_code=201)
def share_resource(body: ShareIn, user=Depends(get_current_user)):
    if body.resource_type not in RESOURCE_TYPES:
        raise HTTPException(400, f"resource_type must be one of {sorted(RESOURCE_TYPES)}")
    if body.permission not in ("view", "edit"):
        raise HTTPException(400, "permission must be 'view' or 'edit'")
    conn = get_conn()
    # Only the resource owner may share it.
    if _resource_owner(conn, body.resource_type, body.resource_id) != user["id"]:
        raise HTTPException(403, "Only the owner of this item can share it")
    _require_member(conn, body.team_id, user["id"])
    with conn:
        conn.execute(
            """INSERT INTO resource_shares (team_id, resource_type, resource_id, permission, shared_by)
               VALUES (?,?,?,?,?)
               ON CONFLICT(team_id, resource_type, resource_id)
               DO UPDATE SET permission=excluded.permission""",
            (body.team_id, body.resource_type, body.resource_id, body.permission, user["id"]),
        )
    return {"ok": True}


@router.delete("/api/collab/share")
def unshare_resource(team_id: int, resource_type: str, resource_id: int,
                     user=Depends(get_current_user)):
    conn = get_conn()
    if _resource_owner(conn, resource_type, resource_id) != user["id"]:
        raise HTTPException(403, "Only the owner of this item can unshare it")
    with conn:
        conn.execute(
            "DELETE FROM resource_shares WHERE team_id=? AND resource_type=? AND resource_id=?",
            (team_id, resource_type, resource_id),
        )
    return {"ok": True}


@router.get("/api/collab/shared-with-me")
def shared_with_me(user=Depends(get_current_user)):
    """Resources shared to any team the user belongs to (excludes their own)."""
    conn = get_conn()
    with conn:
        _resolve_invites(conn, user)
    teams = user_team_ids(conn, user["id"])
    if not teams:
        return {"documents": [], "reports": []}
    qmarks = ",".join("?" * len(teams))

    docs = conn.execute(
        f"""SELECT d.id, d.title, d.category, s.permission, t.name AS team, u.email AS owner
            FROM resource_shares s
            JOIN dr_documents d ON d.id = s.resource_id
            JOIN teams t ON t.id = s.team_id
            JOIN users u ON u.id = d.user_id
            WHERE s.resource_type='dataroom_doc' AND s.team_id IN ({qmarks})
              AND d.user_id != ?""",
        (*teams, user["id"]),
    ).fetchall()
    reports = conn.execute(
        f"""SELECT r.id, r.title, r.financial_year, r.status, r.completion_pct,
                   s.permission, t.name AS team, u.email AS owner
            FROM resource_shares s
            JOIN brsr_reports r ON r.id = s.resource_id
            JOIN teams t ON t.id = s.team_id
            JOIN users u ON u.id = r.user_id
            WHERE s.resource_type='brsr_report' AND s.team_id IN ({qmarks})
              AND r.user_id != ?""",
        (*teams, user["id"]),
    ).fetchall()
    return {"documents": [dict(r) for r in docs], "reports": [dict(r) for r in reports]}


@router.get("/api/collab/resource-shares")
def resource_shares(resource_type: str, resource_id: int, user=Depends(get_current_user)):
    """List the teams a resource the user OWNS is shared with."""
    conn = get_conn()
    if _resource_owner(conn, resource_type, resource_id) != user["id"]:
        raise HTTPException(403, "Only the owner can see shares")
    rows = conn.execute(
        """SELECT s.id, s.team_id, s.permission, t.name AS team
           FROM resource_shares s JOIN teams t ON t.id=s.team_id
           WHERE s.resource_type=? AND s.resource_id=?""",
        (resource_type, resource_id),
    ).fetchall()
    return {"shares": [dict(r) for r in rows]}


# ════════════════════════════════════════════════════════════════════════════════
#  COMMENTS  (on any resource the user can view)
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/collab/comments")
def get_comments(resource_type: str, resource_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    if not can_view(conn, user["id"], resource_type, resource_id):
        raise HTTPException(403, "You do not have access to this item")
    rows = conn.execute(
        """SELECT id, user_id, author_email, body, created_at FROM collab_comments
           WHERE resource_type=? AND resource_id=? ORDER BY created_at""",
        (resource_type, resource_id),
    ).fetchall()
    return {"comments": [dict(r) for r in rows]}


@router.post("/api/collab/comments", status_code=201)
def add_comment(body: CommentIn, user=Depends(get_current_user)):
    if body.resource_type not in RESOURCE_TYPES:
        raise HTTPException(400, "Invalid resource_type")
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Comment cannot be empty")
    conn = get_conn()
    if not can_view(conn, user["id"], body.resource_type, body.resource_id):
        raise HTTPException(403, "You do not have access to this item")
    with conn:
        cur = conn.execute(
            """INSERT INTO collab_comments (resource_type, resource_id, user_id, author_email, body)
               VALUES (?,?,?,?,?)""",
            (body.resource_type, body.resource_id, user["id"], user["email"], text),
        )
    return {"ok": True, "comment_id": cur.lastrowid}


@router.delete("/api/collab/comments/{comment_id}")
def delete_comment(comment_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    row = conn.execute("SELECT user_id FROM collab_comments WHERE id=?", (comment_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Comment not found")
    if row["user_id"] != user["id"]:
        raise HTTPException(403, "You can only delete your own comments")
    with conn:
        conn.execute("DELETE FROM collab_comments WHERE id=?", (comment_id,))
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════════
#  TASKS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/collab/tasks")
def list_tasks(resource_type: str = "", resource_id: Optional[int] = None,
               mine: int = 0, user=Depends(get_current_user)):
    conn = get_conn()
    if mine:
        rows = conn.execute(
            """SELECT * FROM collab_tasks WHERE lower(assignee_email)=lower(?)
               ORDER BY (status='done'), due_date""",
            (user["email"],),
        ).fetchall()
        return {"tasks": [dict(r) for r in rows]}
    if resource_type and resource_id is not None:
        if not can_view(conn, user["id"], resource_type, resource_id):
            raise HTTPException(403, "You do not have access to this item")
        rows = conn.execute(
            """SELECT * FROM collab_tasks WHERE resource_type=? AND resource_id=?
               ORDER BY (status='done'), due_date""",
            (resource_type, resource_id),
        ).fetchall()
        return {"tasks": [dict(r) for r in rows]}
    raise HTTPException(400, "Provide mine=1 or both resource_type and resource_id")


@router.post("/api/collab/tasks", status_code=201)
def create_task(body: TaskIn, user=Depends(get_current_user)):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Task title is required")
    conn = get_conn()
    if body.resource_type:
        if body.resource_type not in RESOURCE_TYPES or body.resource_id is None:
            raise HTTPException(400, "Invalid resource reference")
        if not can_edit(conn, user["id"], body.resource_type, body.resource_id):
            raise HTTPException(403, "You need edit access to add tasks to this item")
    with conn:
        cur = conn.execute(
            """INSERT INTO collab_tasks
               (resource_type, resource_id, title, assignee_email, due_date, created_by, created_email)
               VALUES (?,?,?,?,?,?,?)""",
            (body.resource_type, body.resource_id, title, body.assignee_email.strip().lower(),
             body.due_date.strip(), user["id"], user["email"]),
        )
    return {"ok": True, "task_id": cur.lastrowid}


@router.put("/api/collab/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdateIn, user=Depends(get_current_user)):
    conn = get_conn()
    task = conn.execute("SELECT * FROM collab_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise HTTPException(404, "Task not found")
    # Creator, assignee, or anyone with edit access on the linked resource may update.
    allowed = (task["created_by"] == user["id"]
               or (task["assignee_email"] or "").lower() == user["email"].lower())
    if not allowed and task["resource_type"]:
        allowed = can_edit(conn, user["id"], task["resource_type"], task["resource_id"])
    if not allowed:
        raise HTTPException(403, "Not allowed to update this task")
    if body.status is not None and body.status not in ("open", "doing", "done"):
        raise HTTPException(400, "status must be open, doing or done")
    status_   = body.status if body.status is not None else task["status"]
    title     = body.title.strip() if body.title is not None else task["title"]
    assignee  = body.assignee_email.strip().lower() if body.assignee_email is not None else task["assignee_email"]
    due       = body.due_date.strip() if body.due_date is not None else task["due_date"]
    with conn:
        conn.execute(
            "UPDATE collab_tasks SET status=?, title=?, assignee_email=?, due_date=? WHERE id=?",
            (status_, title, assignee, due, task_id),
        )
    return {"ok": True}


@router.delete("/api/collab/tasks/{task_id}")
def delete_task(task_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    task = conn.execute("SELECT created_by FROM collab_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise HTTPException(404, "Task not found")
    if task["created_by"] != user["id"]:
        raise HTTPException(403, "Only the task creator can delete it")
    with conn:
        conn.execute("DELETE FROM collab_tasks WHERE id=?", (task_id,))
    return {"ok": True}

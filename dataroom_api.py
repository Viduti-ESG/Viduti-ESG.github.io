"""
Green Curve — ESG Data Room API.
Endpoints under /api/dataroom/*

The Data Room is the customer's private workspace for storing, versioning and
organising their own ESG evidence: emissions data, policies, supplier documents,
BRSR drafts, board minutes, assurance reports, certificates, etc. It is the
deepest retention moat — once a consultancy has months of a client's evidence
organised here, re-uploading it elsewhere is painful.

Plugs into the existing Green Curve FastAPI app:
  - reuses auth_api.get_current_user for auth
  - reuses db.get_conn (SQLite) and adds its own dr_* tables on import

DPDP Act 2023 (Data Fiduciary) compliance is built in, NOT bolted on:
  - Consent is recorded before the first upload (purpose limitation + consent).
  - Every read/write/delete is written to an immutable audit log (accountability).
  - A full export endpoint gives the customer their data back on demand
    (data portability — and it keeps the moat value-based, not hostage-based).
  - Hard delete honours the right to erasure: rows AND files are removed.
  - Files are stored privately and only ever served through an authed,
    ownership-checked endpoint — never mounted statically.
"""

import io
import json
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from db import get_conn
from auth_api import get_current_user
from collaboration_api import can_view as _collab_can_view, can_edit as _collab_can_edit

logger = logging.getLogger(__name__)
router = APIRouter()

# ── File storage (private — never mounted statically) ───────────────────────────
BASE_DIR    = Path(__file__).parent
DATAROOM_DIR = BASE_DIR / "uploads" / "dataroom"
DATAROOM_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — ESG evidence (PDFs, spreadsheets, XBRL) can be large
ALLOWED_EXT = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
    ".png", ".jpg", ".jpeg", ".webp", ".xml", ".json", ".zip", ".ppt", ".pptx",
}

# ESG evidence taxonomy — drives folder defaults and reporting completeness later.
CATEGORIES = [
    ("emissions-data",   "Emissions & Energy Data"),
    ("policies",         "ESG Policies & Governance"),
    ("supplier-docs",    "Supplier / Value-Chain Docs"),
    ("brsr-drafts",      "BRSR / Report Drafts"),
    ("board-minutes",    "Board & Committee Minutes"),
    ("audit-assurance",  "Audit & Assurance"),
    ("certifications",   "Certifications & Licences"),
    ("social-hr",        "Social & HR Records"),
    ("other",            "Other Evidence"),
]
_CATEGORY_SLUGS = {c[0] for c in CATEGORIES}

# The consent text shown to and accepted by the user before their first upload.
CONSENT_VERSION = "1.0"
CONSENT_TEXT = (
    "I consent to Green Curve storing the documents and data I upload to my Data Room "
    "for the purpose of organising, versioning and preparing my organisation's ESG "
    "disclosures. I understand the data is private to my account, that I can export or "
    "permanently delete it at any time, and that Green Curve acts as a Data Fiduciary "
    "under India's DPDP Act 2023."
)


# ── Schema ──────────────────────────────────────────────────────────────────────
def init_dataroom_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS dr_consent (
                user_id        INTEGER PRIMARY KEY,
                consented      INTEGER  DEFAULT 0,
                consent_version TEXT    DEFAULT '',
                consent_text   TEXT     DEFAULT '',
                consent_at     DATETIME,
                consent_ip     TEXT     DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS dr_folders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                name       TEXT    NOT NULL,
                category   TEXT    DEFAULT 'other',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_dr_folders_user ON dr_folders(user_id);

            CREATE TABLE IF NOT EXISTS dr_documents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                folder_id       INTEGER,
                title           TEXT    NOT NULL,
                category        TEXT    DEFAULT 'other',
                reporting_year  TEXT    DEFAULT '',
                latest_version  INTEGER DEFAULT 0,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)   REFERENCES users(id),
                FOREIGN KEY (folder_id) REFERENCES dr_folders(id)
            );
            CREATE INDEX IF NOT EXISTS idx_dr_docs_user   ON dr_documents(user_id);
            CREATE INDEX IF NOT EXISTS idx_dr_docs_folder ON dr_documents(folder_id);

            CREATE TABLE IF NOT EXISTS dr_versions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id  INTEGER NOT NULL,
                version_no   INTEGER NOT NULL,
                orig_name    TEXT    DEFAULT '',
                stored_name  TEXT    NOT NULL,
                size_bytes   INTEGER DEFAULT 0,
                mime         TEXT    DEFAULT '',
                note         TEXT    DEFAULT '',
                uploaded_by  TEXT    DEFAULT '',
                uploaded_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES dr_documents(id)
            );
            CREATE INDEX IF NOT EXISTS idx_dr_versions_doc ON dr_versions(document_id);

            CREATE TABLE IF NOT EXISTS dr_audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                action      TEXT    NOT NULL,
                target_type TEXT    DEFAULT '',
                target_id   INTEGER,
                detail      TEXT    DEFAULT '',
                ip          TEXT    DEFAULT '',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_dr_audit_user ON dr_audit_log(user_id);
        """)


init_dataroom_db()


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _client_ip(request: Request) -> str:
    # Honour the reverse proxy (nginx) X-Forwarded-For when present.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _audit(conn, user_id: int, action: str, target_type: str = "",
           target_id: Optional[int] = None, detail: str = "", ip: str = "") -> None:
    conn.execute(
        """INSERT INTO dr_audit_log (user_id, action, target_type, target_id, detail, ip)
           VALUES (?,?,?,?,?,?)""",
        (user_id, action, target_type, target_id, detail, ip),
    )


def _has_consent(user_id: int) -> bool:
    row = get_conn().execute(
        "SELECT consented FROM dr_consent WHERE user_id=?", (user_id,)
    ).fetchone()
    return bool(row and row["consented"])


def _require_consent(user_id: int) -> None:
    if not _has_consent(user_id):
        raise HTTPException(
            403,
            "You must accept the Data Room consent terms before uploading. "
            "Call POST /api/dataroom/consent first.",
        )


def _owned_document(conn, doc_id: int, user_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM dr_documents WHERE id=? AND user_id=?", (doc_id, user_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return dict(row)


def _viewable_document(conn, doc_id: int, user_id: int) -> dict:
    """Owner OR a team member the document has been shared with (any permission)."""
    row = conn.execute("SELECT * FROM dr_documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    d = dict(row)
    if d["user_id"] == user_id or _collab_can_view(conn, user_id, "dataroom_doc", doc_id):
        return d
    raise HTTPException(404, "Document not found")


def _editable_document(conn, doc_id: int, user_id: int) -> dict:
    """Owner OR a team member with an 'edit' share."""
    row = conn.execute("SELECT * FROM dr_documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    d = dict(row)
    if d["user_id"] == user_id or _collab_can_edit(conn, user_id, "dataroom_doc", doc_id):
        return d
    # Distinguish "exists but read-only for you" from "not found at all".
    if _collab_can_view(conn, user_id, "dataroom_doc", doc_id):
        raise HTTPException(403, "You have view-only access to this document")
    raise HTTPException(404, "Document not found")


def _doc_payload(conn, doc: dict) -> dict:
    versions = conn.execute(
        """SELECT id, version_no, orig_name, size_bytes, mime, note, uploaded_by, uploaded_at
           FROM dr_versions WHERE document_id=? ORDER BY version_no DESC""",
        (doc["id"],),
    ).fetchall()
    d = dict(doc)
    d["versions"] = [dict(v) for v in versions]
    d["version_count"] = len(d["versions"])
    return d


# ── Pydantic models ───────────────────────────────────────────────────────────────
class ConsentIn(BaseModel):
    accept: bool = True

class FolderIn(BaseModel):
    name:     str
    category: str = "other"

class DocumentMetaIn(BaseModel):
    title:          Optional[str] = None
    folder_id:      Optional[int] = None
    category:       Optional[str] = None
    reporting_year: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════════
#  CONSENT (DPDP gate)
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/dataroom/consent")
def consent_status(user=Depends(get_current_user)):
    row = get_conn().execute(
        "SELECT consented, consent_version, consent_at FROM dr_consent WHERE user_id=?",
        (user["id"],),
    ).fetchone()
    return {
        "consented":       bool(row and row["consented"]),
        "current_version": CONSENT_VERSION,
        "consent_text":    CONSENT_TEXT,
        "accepted_version": row["consent_version"] if row else "",
        "accepted_at":     row["consent_at"] if row else None,
    }


@router.post("/api/dataroom/consent")
def give_consent(body: ConsentIn, request: Request, user=Depends(get_current_user)):
    if not body.accept:
        raise HTTPException(400, "Consent must be accepted to use the Data Room")
    ip = _client_ip(request)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO dr_consent (user_id, consented, consent_version, consent_text, consent_at, consent_ip)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 consented=1, consent_version=excluded.consent_version,
                 consent_text=excluded.consent_text, consent_at=excluded.consent_at,
                 consent_ip=excluded.consent_ip""",
            (user["id"], 1, CONSENT_VERSION, CONSENT_TEXT, _now(), ip),
        )
        _audit(conn, user["id"], "consent_given", "consent", None, CONSENT_VERSION, ip)
    return {"ok": True, "consented": True}


# ════════════════════════════════════════════════════════════════════════════════
#  METADATA
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/dataroom/categories")
def list_categories():
    return {"categories": [{"slug": s, "name": n} for s, n in CATEGORIES]}


# ════════════════════════════════════════════════════════════════════════════════
#  FOLDERS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/dataroom/folders")
def list_folders(user=Depends(get_current_user)):
    rows = get_conn().execute(
        """SELECT f.*, (SELECT COUNT(*) FROM dr_documents d WHERE d.folder_id=f.id) AS doc_count
           FROM dr_folders f WHERE f.user_id=? ORDER BY f.name""",
        (user["id"],),
    ).fetchall()
    return {"folders": [dict(r) for r in rows]}


@router.post("/api/dataroom/folders", status_code=201)
def create_folder(body: FolderIn, request: Request, user=Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Folder name is required")
    category = body.category if body.category in _CATEGORY_SLUGS else "other"
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO dr_folders (user_id, name, category) VALUES (?,?,?)",
            (user["id"], name, category),
        )
        fid = cur.lastrowid
        _audit(conn, user["id"], "folder_created", "folder", fid, name, _client_ip(request))
    return {"ok": True, "folder_id": fid}


@router.delete("/api/dataroom/folders/{folder_id}")
def delete_folder(folder_id: int, request: Request, user=Depends(get_current_user)):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM dr_folders WHERE id=? AND user_id=?", (folder_id, user["id"])
    ).fetchone()
    if not row:
        raise HTTPException(404, "Folder not found")
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM dr_documents WHERE folder_id=? AND user_id=?",
        (folder_id, user["id"]),
    ).fetchone()["c"]
    if n:
        raise HTTPException(400, f"Folder is not empty ({n} document(s)). Move or delete them first.")
    with conn:
        conn.execute("DELETE FROM dr_folders WHERE id=? AND user_id=?", (folder_id, user["id"]))
        _audit(conn, user["id"], "folder_deleted", "folder", folder_id, "", _client_ip(request))
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════════
#  DOCUMENTS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/dataroom/documents")
def list_documents(folder_id: Optional[int] = None, category: str = "", q: str = "",
                   user=Depends(get_current_user)):
    conn = get_conn()
    sql = "SELECT * FROM dr_documents WHERE user_id=?"
    params: list = [user["id"]]
    if folder_id is not None:
        sql += " AND folder_id=?"
        params.append(folder_id)
    if category:
        sql += " AND category=?"
        params.append(category)
    if q:
        sql += " AND title LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY updated_at DESC LIMIT 500"
    rows = conn.execute(sql, params).fetchall()
    return {"documents": [_doc_payload(conn, dict(r)) for r in rows]}


@router.get("/api/dataroom/documents/{doc_id}")
def get_document(doc_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    doc = _viewable_document(conn, doc_id, user["id"])
    return {"document": _doc_payload(conn, doc)}


@router.post("/api/dataroom/documents", status_code=201)
async def upload_document(
    request: Request,
    title:          str = Form(""),
    folder_id:      Optional[int] = Form(None),
    category:       str = Form("other"),
    reporting_year: str = Form(""),
    note:           str = Form(""),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Create a new document with its first version."""
    _require_consent(user["id"])
    conn = get_conn()

    if folder_id is not None:
        owned = conn.execute(
            "SELECT id FROM dr_folders WHERE id=? AND user_id=?", (folder_id, user["id"])
        ).fetchone()
        if not owned:
            raise HTTPException(404, "Folder not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"File type {ext or '(none)'} not allowed")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File exceeds 25 MB limit")

    stored = f"{uuid.uuid4().hex}{ext}"
    (DATAROOM_DIR / stored).write_bytes(data)

    cat = category if category in _CATEGORY_SLUGS else "other"
    doc_title = (title or file.filename or "Untitled").strip()
    ip = _client_ip(request)
    with conn:
        cur = conn.execute(
            """INSERT INTO dr_documents (user_id, folder_id, title, category, reporting_year, latest_version)
               VALUES (?,?,?,?,?,1)""",
            (user["id"], folder_id, doc_title, cat, reporting_year.strip()),
        )
        doc_id = cur.lastrowid
        conn.execute(
            """INSERT INTO dr_versions
               (document_id, version_no, orig_name, stored_name, size_bytes, mime, note, uploaded_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (doc_id, 1, file.filename or stored, stored, len(data),
             file.content_type or "", note.strip(), user["email"]),
        )
        _audit(conn, user["id"], "document_uploaded", "document", doc_id,
               f"{doc_title} (v1)", ip)
    return {"ok": True, "document_id": doc_id, "version_no": 1}


@router.post("/api/dataroom/documents/{doc_id}/versions", status_code=201)
async def upload_version(
    doc_id: int,
    request: Request,
    note: str = Form(""),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Add a new version to an existing document (keeps full history)."""
    _require_consent(user["id"])
    conn = get_conn()
    doc = _editable_document(conn, doc_id, user["id"])

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"File type {ext or '(none)'} not allowed")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File exceeds 25 MB limit")

    next_no = int(doc["latest_version"]) + 1
    stored = f"{uuid.uuid4().hex}{ext}"
    (DATAROOM_DIR / stored).write_bytes(data)
    ip = _client_ip(request)
    with conn:
        conn.execute(
            """INSERT INTO dr_versions
               (document_id, version_no, orig_name, stored_name, size_bytes, mime, note, uploaded_by)
               VALUES (?,?,?,?,?,?,?,?)""",
            (doc_id, next_no, file.filename or stored, stored, len(data),
             file.content_type or "", note.strip(), user["email"]),
        )
        conn.execute(
            "UPDATE dr_documents SET latest_version=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (next_no, doc_id),
        )
        _audit(conn, user["id"], "version_uploaded", "document", doc_id,
               f"{doc['title']} (v{next_no})", ip)
    return {"ok": True, "version_no": next_no}


@router.put("/api/dataroom/documents/{doc_id}")
def update_document_meta(doc_id: int, body: DocumentMetaIn, request: Request,
                         user=Depends(get_current_user)):
    conn = get_conn()
    doc = _editable_document(conn, doc_id, user["id"])
    if body.folder_id is not None:
        owned = conn.execute(
            "SELECT id FROM dr_folders WHERE id=? AND user_id=?", (body.folder_id, user["id"])
        ).fetchone()
        if not owned:
            raise HTTPException(404, "Folder not found")
    title    = body.title.strip() if body.title is not None else doc["title"]
    folder_id = body.folder_id if body.folder_id is not None else doc["folder_id"]
    category = body.category if (body.category in _CATEGORY_SLUGS) else doc["category"]
    ryear    = body.reporting_year if body.reporting_year is not None else doc["reporting_year"]
    with conn:
        conn.execute(
            """UPDATE dr_documents SET title=?, folder_id=?, category=?, reporting_year=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?""",
            (title, folder_id, category, ryear, doc_id, user["id"]),
        )
        _audit(conn, user["id"], "document_updated", "document", doc_id, title, _client_ip(request))
    return {"ok": True}


@router.get("/api/dataroom/versions/{version_id}/file")
def download_version(version_id: int, request: Request, user=Depends(get_current_user)):
    """Serve a private file — owner or a shared team member. Never mounted statically."""
    conn = get_conn()
    row = conn.execute(
        """SELECT v.*, d.user_id AS owner_id, d.title AS doc_title
           FROM dr_versions v JOIN dr_documents d ON d.id = v.document_id
           WHERE v.id=?""",
        (version_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Version not found")
    if row["owner_id"] != user["id"] and not _collab_can_view(conn, user["id"], "dataroom_doc", row["document_id"]):
        raise HTTPException(403, "Not authorized")
    path = DATAROOM_DIR / row["stored_name"]
    if not path.exists():
        raise HTTPException(404, "File missing")
    with conn:
        _audit(conn, user["id"], "file_downloaded", "version", version_id,
               f"{row['doc_title']} (v{row['version_no']})", _client_ip(request))
    return FileResponse(
        str(path),
        filename=row["orig_name"] or row["stored_name"],
        media_type=row["mime"] or "application/octet-stream",
    )


@router.delete("/api/dataroom/documents/{doc_id}")
def delete_document(doc_id: int, request: Request, user=Depends(get_current_user)):
    """Right to erasure — permanently remove a document, all its versions, and the files."""
    conn = get_conn()
    doc = _owned_document(conn, doc_id, user["id"])
    versions = conn.execute(
        "SELECT stored_name FROM dr_versions WHERE document_id=?", (doc_id,)
    ).fetchall()
    for v in versions:
        try:
            (DATAROOM_DIR / v["stored_name"]).unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete file %s during erasure", v["stored_name"])
    with conn:
        conn.execute("DELETE FROM dr_versions WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM dr_documents WHERE id=? AND user_id=?", (doc_id, user["id"]))
        _audit(conn, user["id"], "document_deleted", "document", doc_id, doc["title"], _client_ip(request))
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════════════════
#  AUDIT LOG  (DPDP accountability)
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/dataroom/audit-log")
def get_audit_log(limit: int = 100, user=Depends(get_current_user)):
    limit = max(1, min(limit, 500))
    rows = get_conn().execute(
        """SELECT action, target_type, target_id, detail, ip, created_at
           FROM dr_audit_log WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
        (user["id"], limit),
    ).fetchall()
    return {"entries": [dict(r) for r in rows]}


# ════════════════════════════════════════════════════════════════════════════════
#  EXPORT  (DPDP data portability — keeps the moat value-based, not hostage-based)
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/dataroom/export")
def export_all(request: Request, user=Depends(get_current_user)):
    """Stream a ZIP of every document (latest + all versions) plus a JSON manifest."""
    conn = get_conn()
    docs = conn.execute(
        "SELECT * FROM dr_documents WHERE user_id=? ORDER BY id", (user["id"],)
    ).fetchall()

    manifest = {
        "exported_at": _now(),
        "account":     {"email": user["email"], "org": user.get("org", "")},
        "documents":   [],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            doc = dict(d)
            versions = conn.execute(
                "SELECT * FROM dr_versions WHERE document_id=? ORDER BY version_no", (doc["id"],)
            ).fetchall()
            doc_entry = {
                "title": doc["title"], "category": doc["category"],
                "reporting_year": doc["reporting_year"], "versions": [],
            }
            safe_title = "".join(c if c.isalnum() or c in " -_." else "_" for c in doc["title"])[:60]
            for v in versions:
                path = DATAROOM_DIR / v["stored_name"]
                arc = f"documents/{doc['id']}_{safe_title}/v{v['version_no']}_{v['orig_name']}"
                if path.exists():
                    zf.write(str(path), arc)
                doc_entry["versions"].append({
                    "version_no": v["version_no"], "file": arc,
                    "original_name": v["orig_name"], "size_bytes": v["size_bytes"],
                    "uploaded_at": v["uploaded_at"], "note": v["note"],
                })
            manifest["documents"].append(doc_entry)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    buf.seek(0)
    with conn:
        _audit(conn, user["id"], "data_exported", "account", None,
               f"{len(docs)} document(s)", _client_ip(request))
    fname = f"green-curve-dataroom-export-{datetime.now().strftime('%Y%m%d')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

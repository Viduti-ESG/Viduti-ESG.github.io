"""
Green Curve Marketplace — Sustainable product marketplace API.
Endpoints under /api/market/*

Plugs into the existing Green Curve FastAPI app:
  - reuses auth_api.get_current_user / require_admin for auth & roles
  - reuses db.get_conn (SQLite) and adds its own mkt_* tables on import
  - uses the Anthropic SDK (already a dependency) for AI-assisted cert review

Model: sellers list sustainable products and upload sustainability/organic
certificates. Green Curve verifies certs (manual + AI-assisted) and shows a
trust badge to buyers. Commission is tracked per seller (collection wired later).
"""

import base64
import json
import logging
import mimetypes
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from db import get_conn
from auth_api import get_current_user, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

# ── File storage ───────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
UPLOAD_DIR     = BASE_DIR / "uploads"
CERT_DIR       = UPLOAD_DIR / "certs"        # private — never served statically
PRODUCT_IMG_DIR = UPLOAD_DIR / "products"    # public — mounted at /media/products
for _d in (CERT_DIR, PRODUCT_IMG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_CERT_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_IMG_EXT  = {".png", ".jpg", ".jpeg", ".webp"}

# ── Anthropic client (lazy) ──────────────────────────────────────────────────────
try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

_client = None
_client_lock = threading.Lock()
SONNET = "claude-sonnet-4-6"


def _claude():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not _ANTHROPIC_AVAILABLE:
                    raise RuntimeError("anthropic package not installed")
                key = os.environ.get("ANTHROPIC_API_KEY", "")
                if not key:
                    raise RuntimeError("ANTHROPIC_API_KEY not set")
                _client = anthropic.Anthropic(api_key=key)
    return _client


# ── Schema ───────────────────────────────────────────────────────────────────────
def init_marketplace_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS mkt_sellers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER UNIQUE NOT NULL,
                business_name   TEXT    NOT NULL,
                gstin           TEXT    DEFAULT '',
                contact_phone   TEXT    DEFAULT '',
                address         TEXT    DEFAULT '',
                description     TEXT    DEFAULT '',
                logo_url        TEXT    DEFAULT '',
                kyc_status      TEXT    DEFAULT 'pending',   -- pending|approved|rejected
                commission_rate REAL    DEFAULT 0.10,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS mkt_categories (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                slug          TEXT UNIQUE NOT NULL,
                name          TEXT NOT NULL,
                cert_required INTEGER DEFAULT 0     -- 1 = a valid cert is mandatory to list
            );

            CREATE TABLE IF NOT EXISTS mkt_cert_types (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                slug                TEXT UNIQUE NOT NULL,
                name                TEXT NOT NULL,
                issuer              TEXT DEFAULT '',
                has_public_registry INTEGER DEFAULT 0,
                registry_url        TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS mkt_products (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id     INTEGER NOT NULL,
                name          TEXT NOT NULL,
                slug          TEXT NOT NULL,
                description   TEXT DEFAULT '',
                price         REAL DEFAULT 0,
                currency      TEXT DEFAULT 'INR',
                category_id   INTEGER,
                image_url     TEXT DEFAULT '',
                sustainability_attrs TEXT DEFAULT '[]',
                status        TEXT DEFAULT 'draft',   -- draft|pending|listed|rejected|delisted
                reviewer_notes TEXT DEFAULT '',
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_id)   REFERENCES mkt_sellers(id),
                FOREIGN KEY (category_id) REFERENCES mkt_categories(id)
            );
            CREATE INDEX IF NOT EXISTS idx_mkt_products_status   ON mkt_products(status);
            CREATE INDEX IF NOT EXISTS idx_mkt_products_seller   ON mkt_products(seller_id);
            CREATE INDEX IF NOT EXISTS idx_mkt_products_category ON mkt_products(category_id);

            CREATE TABLE IF NOT EXISTS mkt_certificates (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id           INTEGER NOT NULL,
                product_id          INTEGER,              -- NULL = applies to whole seller
                cert_type_id        INTEGER,
                cert_type_name      TEXT DEFAULT '',
                issuer              TEXT DEFAULT '',
                cert_number         TEXT DEFAULT '',
                issue_date          TEXT DEFAULT '',
                expiry_date         TEXT DEFAULT '',
                document_path       TEXT DEFAULT '',
                status              TEXT DEFAULT 'pending', -- pending|verified|rejected|expired
                verification_method TEXT DEFAULT '',        -- manual|ai|registry
                ai_recommendation   TEXT DEFAULT '',
                ai_extracted        TEXT DEFAULT '{}',
                reviewer_notes      TEXT DEFAULT '',
                verified_by         INTEGER,
                verified_at         DATETIME,
                created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_id)  REFERENCES mkt_sellers(id),
                FOREIGN KEY (product_id) REFERENCES mkt_products(id)
            );
            CREATE INDEX IF NOT EXISTS idx_mkt_certs_seller  ON mkt_certificates(seller_id);
            CREATE INDEX IF NOT EXISTS idx_mkt_certs_status  ON mkt_certificates(status);
            CREATE INDEX IF NOT EXISTS idx_mkt_certs_product ON mkt_certificates(product_id);

            CREATE TABLE IF NOT EXISTS mkt_verification_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                certificate_id INTEGER NOT NULL,
                action         TEXT NOT NULL,
                actor          TEXT DEFAULT '',
                notes          TEXT DEFAULT '',
                created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (certificate_id) REFERENCES mkt_certificates(id)
            );
        """)
        _seed(conn)


def _seed(conn) -> None:
    cats = [
        ("organic-food", "Organic Food & Beverages", 1),
        ("personal-care", "Personal Care & Cosmetics", 0),
        ("home-cleaning", "Home & Cleaning", 0),
        ("sustainable-gifting", "Sustainable Gifting", 0),
        ("apparel-textiles", "Apparel & Textiles", 0),
        ("packaging", "Eco Packaging", 0),
        ("stationery", "Stationery & Office", 0),
        ("other", "Other Sustainable Goods", 0),
    ]
    for slug, name, req in cats:
        conn.execute(
            "INSERT OR IGNORE INTO mkt_categories (slug, name, cert_required) VALUES (?,?,?)",
            (slug, name, req),
        )

    cert_types = [
        ("india-organic", "India Organic (NPOP)", "APEDA / NPOP", 1, "https://www.apeda.gov.in/apedawebsite/organic/"),
        ("jaivik-bharat", "Jaivik Bharat (PGS-India)", "PGS-India / FSSAI", 1, "https://jaivikbharat.fssai.gov.in/"),
        ("fssai", "FSSAI Licence", "FSSAI", 1, "https://foscos.fssai.gov.in/"),
        ("gots", "GOTS (Organic Textile)", "Global Organic Textile Standard", 1, "https://global-standard.org/find-suppliers-shops-and-inputs/certified-suppliers"),
        ("fsc", "FSC (Forest Stewardship)", "FSC", 1, "https://search.fsc.org/"),
        ("fairtrade", "Fairtrade", "Fairtrade International", 1, "https://www.flocert.net/about-flocert/customer-search/"),
        ("usda-organic", "USDA Organic", "USDA", 1, "https://organic.ams.usda.gov/integrity/"),
        ("eu-organic", "EU Organic", "EU", 0, ""),
        ("ecocert", "ECOCERT", "ECOCERT", 0, ""),
        ("b-corp", "B Corp", "B Lab", 1, "https://www.bcorporation.net/en-us/find-a-b-corp/"),
        ("other", "Other / Self-declared", "", 0, ""),
    ]
    for slug, name, issuer, reg, url in cert_types:
        conn.execute(
            "INSERT OR IGNORE INTO mkt_cert_types (slug, name, issuer, has_public_registry, registry_url) VALUES (?,?,?,?,?)",
            (slug, name, issuer, reg, url),
        )


init_marketplace_db()


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "item"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _seller_for_user(user_id: int) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM mkt_sellers WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def _require_seller(user: dict) -> dict:
    seller = _seller_for_user(user["id"])
    if not seller:
        raise HTTPException(403, "You are not registered as a seller. Create a seller profile first.")
    return seller


def _verified_badge(cert_row: dict) -> str:
    """Map a certificate's stored state to the buyer-facing badge label."""
    status = cert_row["status"]
    if status == "verified" and cert_row.get("expiry_date"):
        try:
            if datetime.strptime(cert_row["expiry_date"], "%Y-%m-%d").date() < datetime.now(timezone.utc).date():
                return "expired"
        except ValueError:
            pass
    return {"verified": "verified", "pending": "pending", "rejected": "rejected", "expired": "expired"}.get(status, "pending")


# ── Pydantic models ───────────────────────────────────────────────────────────────
class SellerIn(BaseModel):
    business_name: str
    gstin:         str = ""
    contact_phone: str = ""
    address:       str = ""
    description:   str = ""

class ProductIn(BaseModel):
    name:        str
    description: str = ""
    price:       float = 0
    category_id: Optional[int] = None
    sustainability_attrs: list = []

class DecisionIn(BaseModel):
    decision: str            # approve | reject
    notes:    str = ""

class KycIn(BaseModel):
    decision: str            # approve | reject
    notes:    str = ""


# ════════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/market/categories")
def list_categories():
    rows = get_conn().execute("SELECT id, slug, name, cert_required FROM mkt_categories ORDER BY name").fetchall()
    return {"categories": [dict(r) for r in rows]}


@router.get("/api/market/cert-types")
def list_cert_types():
    rows = get_conn().execute(
        "SELECT id, slug, name, issuer, has_public_registry, registry_url FROM mkt_cert_types ORDER BY name"
    ).fetchall()
    return {"cert_types": [dict(r) for r in rows]}


@router.get("/api/market/products")
def browse_products(category: str = "", q: str = "", verified_only: int = 0):
    conn = get_conn()
    sql = """
        SELECT p.id, p.name, p.slug, p.description, p.price, p.currency, p.image_url,
               p.sustainability_attrs, c.name AS category, s.business_name AS seller,
               s.id AS seller_id
        FROM mkt_products p
        JOIN mkt_sellers s   ON s.id = p.seller_id
        LEFT JOIN mkt_categories c ON c.id = p.category_id
        WHERE p.status = 'listed'
    """
    params: list = []
    if category:
        sql += " AND c.slug = ?"
        params.append(category)
    if q:
        sql += " AND (p.name LIKE ? OR p.description LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY p.updated_at DESC LIMIT 200"
    rows = conn.execute(sql, params).fetchall()

    out = []
    for r in rows:
        prod = dict(r)
        badges = _product_badges(conn, prod["id"], prod["seller_id"])
        if verified_only and not any(b["state"] == "verified" for b in badges):
            continue
        prod["badges"] = badges
        prod["sustainability_attrs"] = json.loads(prod.get("sustainability_attrs") or "[]")
        out.append(prod)
    return {"products": out}


def _product_badges(conn, product_id: int, seller_id: int) -> list:
    """Verified certificates that apply to a product (product-specific or seller-wide)."""
    rows = conn.execute(
        """SELECT cert_type_name, issuer, status, expiry_date FROM mkt_certificates
           WHERE status IN ('verified','expired')
             AND (product_id = ? OR (product_id IS NULL AND seller_id = ?))""",
        (product_id, seller_id),
    ).fetchall()
    return [
        {"label": r["cert_type_name"] or "Certified", "issuer": r["issuer"], "state": _verified_badge(dict(r))}
        for r in rows
    ]


@router.get("/api/market/products/{product_id}")
def product_detail(product_id: int):
    conn = get_conn()
    r = conn.execute(
        """SELECT p.*, c.name AS category, s.business_name AS seller, s.description AS seller_desc,
                  s.id AS seller_id
           FROM mkt_products p
           JOIN mkt_sellers s ON s.id = p.seller_id
           LEFT JOIN mkt_categories c ON c.id = p.category_id
           WHERE p.id = ? AND p.status = 'listed'""",
        (product_id,),
    ).fetchone()
    if not r:
        raise HTTPException(404, "Product not found")
    prod = dict(r)
    prod["sustainability_attrs"] = json.loads(prod.get("sustainability_attrs") or "[]")
    prod["badges"] = _product_badges(conn, product_id, prod["seller_id"])
    return {"product": prod}


# ════════════════════════════════════════════════════════════════════════════════
#  SELLER ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════════
@router.post("/api/market/seller", status_code=201)
def create_seller(body: SellerIn, user=Depends(get_current_user)):
    if _seller_for_user(user["id"]):
        raise HTTPException(409, "Seller profile already exists")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mkt_sellers (user_id, business_name, gstin, contact_phone, address, description)
               VALUES (?,?,?,?,?,?)""",
            (user["id"], body.business_name.strip(), body.gstin.strip(),
             body.contact_phone.strip(), body.address.strip(), body.description.strip()),
        )
        seller_id = cur.lastrowid
    return {"ok": True, "seller_id": seller_id, "kyc_status": "pending"}


@router.get("/api/market/seller/me")
def my_seller(user=Depends(get_current_user)):
    seller = _seller_for_user(user["id"])
    return {"seller": seller}


@router.get("/api/market/seller/products")
def my_products(user=Depends(get_current_user)):
    seller = _require_seller(user)
    rows = get_conn().execute(
        """SELECT p.*, c.name AS category FROM mkt_products p
           LEFT JOIN mkt_categories c ON c.id = p.category_id
           WHERE p.seller_id=? ORDER BY p.updated_at DESC""",
        (seller["id"],),
    ).fetchall()
    products = []
    for r in rows:
        d = dict(r)
        d["sustainability_attrs"] = json.loads(d.get("sustainability_attrs") or "[]")
        products.append(d)
    return {"products": products}


@router.post("/api/market/seller/products", status_code=201)
def create_product(body: ProductIn, user=Depends(get_current_user)):
    seller = _require_seller(user)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mkt_products (seller_id, name, slug, description, price, category_id, sustainability_attrs)
               VALUES (?,?,?,?,?,?,?)""",
            (seller["id"], body.name.strip(), _slugify(body.name), body.description.strip(),
             body.price, body.category_id, json.dumps(body.sustainability_attrs)),
        )
        pid = cur.lastrowid
    return {"ok": True, "product_id": pid}


@router.put("/api/market/seller/products/{product_id}")
def update_product(product_id: int, body: ProductIn, user=Depends(get_current_user)):
    seller = _require_seller(user)
    conn = get_conn()
    owned = conn.execute(
        "SELECT id FROM mkt_products WHERE id=? AND seller_id=?", (product_id, seller["id"])
    ).fetchone()
    if not owned:
        raise HTTPException(404, "Product not found")
    with conn:
        conn.execute(
            """UPDATE mkt_products SET name=?, slug=?, description=?, price=?, category_id=?,
                   sustainability_attrs=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (body.name.strip(), _slugify(body.name), body.description.strip(), body.price,
             body.category_id, json.dumps(body.sustainability_attrs), product_id),
        )
    return {"ok": True}


@router.post("/api/market/seller/products/{product_id}/submit")
def submit_product(product_id: int, user=Depends(get_current_user)):
    """Move a draft product into the admin listing-approval queue.
    If its category requires a certificate, at least one verified cert must apply."""
    seller = _require_seller(user)
    conn = get_conn()
    prod = conn.execute(
        "SELECT * FROM mkt_products WHERE id=? AND seller_id=?", (product_id, seller["id"])
    ).fetchone()
    if not prod:
        raise HTTPException(404, "Product not found")

    cat = conn.execute("SELECT cert_required FROM mkt_categories WHERE id=?", (prod["category_id"],)).fetchone()
    if cat and cat["cert_required"]:
        badges = _product_badges(conn, product_id, seller["id"])
        if not any(b["state"] == "verified" for b in badges):
            raise HTTPException(
                400,
                "This category requires a verified sustainability certificate before the product can be listed. "
                "Upload a certificate and wait for verification first.",
            )
    with conn:
        conn.execute(
            "UPDATE mkt_products SET status='pending', updated_at=CURRENT_TIMESTAMP WHERE id=?", (product_id,)
        )
    return {"ok": True, "status": "pending"}


@router.post("/api/market/seller/products/{product_id}/image")
async def upload_product_image(product_id: int, file: UploadFile = File(...), user=Depends(get_current_user)):
    seller = _require_seller(user)
    conn = get_conn()
    owned = conn.execute(
        "SELECT id FROM mkt_products WHERE id=? AND seller_id=?", (product_id, seller["id"])
    ).fetchone()
    if not owned:
        raise HTTPException(404, "Product not found")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMG_EXT:
        raise HTTPException(400, f"Image must be one of {sorted(ALLOWED_IMG_EXT)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Image exceeds 8 MB limit")
    fname = f"{uuid.uuid4().hex}{ext}"
    (PRODUCT_IMG_DIR / fname).write_bytes(data)
    url = f"/media/products/{fname}"
    with conn:
        conn.execute("UPDATE mkt_products SET image_url=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (url, product_id))
    return {"ok": True, "image_url": url}


@router.get("/api/market/seller/certificates")
def my_certificates(user=Depends(get_current_user)):
    seller = _require_seller(user)
    rows = get_conn().execute(
        """SELECT id, product_id, cert_type_name, issuer, cert_number, issue_date, expiry_date,
                  status, verification_method, reviewer_notes, created_at
           FROM mkt_certificates WHERE seller_id=? ORDER BY created_at DESC""",
        (seller["id"],),
    ).fetchall()
    return {"certificates": [dict(r) for r in rows]}


@router.post("/api/market/seller/certificates", status_code=201)
async def upload_certificate(
    cert_type_id: int = Form(...),
    cert_number:  str = Form(""),
    issuer:       str = Form(""),
    issue_date:   str = Form(""),
    expiry_date:  str = Form(""),
    product_id:   Optional[int] = Form(None),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    seller = _require_seller(user)
    conn = get_conn()

    ct = conn.execute("SELECT name, issuer FROM mkt_cert_types WHERE id=?", (cert_type_id,)).fetchone()
    if not ct:
        raise HTTPException(400, "Unknown certificate type")

    if product_id is not None:
        owned = conn.execute(
            "SELECT id FROM mkt_products WHERE id=? AND seller_id=?", (product_id, seller["id"])
        ).fetchone()
        if not owned:
            raise HTTPException(404, "Product not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_CERT_EXT:
        raise HTTPException(400, f"Certificate must be one of {sorted(ALLOWED_CERT_EXT)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File exceeds 8 MB limit")
    fname = f"{uuid.uuid4().hex}{ext}"
    (CERT_DIR / fname).write_bytes(data)

    with conn:
        cur = conn.execute(
            """INSERT INTO mkt_certificates
               (seller_id, product_id, cert_type_id, cert_type_name, issuer, cert_number,
                issue_date, expiry_date, document_path)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (seller["id"], product_id, cert_type_id, ct["name"], issuer or ct["issuer"],
             cert_number.strip(), issue_date.strip(), expiry_date.strip(), fname),
        )
        cert_id = cur.lastrowid
        conn.execute(
            "INSERT INTO mkt_verification_log (certificate_id, action, actor) VALUES (?,?,?)",
            (cert_id, "uploaded", user["email"]),
        )
    return {"ok": True, "certificate_id": cert_id, "status": "pending"}


@router.get("/api/market/seller/certificates/{cert_id}/file")
def download_certificate(cert_id: int, user=Depends(get_current_user)):
    """Serve the private cert document — owner or admin only (never public)."""
    conn = get_conn()
    cert = conn.execute("SELECT * FROM mkt_certificates WHERE id=?", (cert_id,)).fetchone()
    if not cert:
        raise HTTPException(404, "Certificate not found")
    seller = _seller_for_user(user["id"])
    is_owner = seller and seller["id"] == cert["seller_id"]
    if not is_owner and user.get("role") != "admin":
        raise HTTPException(403, "Not authorized")
    path = CERT_DIR / cert["document_path"]
    if not path.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(str(path))


# ════════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS — verification & moderation
# ════════════════════════════════════════════════════════════════════════════════
@router.get("/api/market/admin/verification-queue")
def verification_queue(admin=Depends(require_admin)):
    rows = get_conn().execute(
        """SELECT c.*, s.business_name AS seller, p.name AS product_name
           FROM mkt_certificates c
           JOIN mkt_sellers s ON s.id = c.seller_id
           LEFT JOIN mkt_products p ON p.id = c.product_id
           WHERE c.status = 'pending' ORDER BY c.created_at""",
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("document_path", None)  # don't leak filename
        try:
            d["ai_extracted"] = json.loads(d.get("ai_extracted") or "{}")
        except Exception:
            d["ai_extracted"] = {}
        out.append(d)
    return {"queue": out}


@router.post("/api/market/admin/certificates/{cert_id}/ai-review")
def ai_review_certificate(cert_id: int, admin=Depends(require_admin)):
    """Use Claude to read the uploaded certificate, extract key fields, and
    recommend approve / reject / manual. The human admin still makes the call."""
    conn = get_conn()
    cert = conn.execute("SELECT * FROM mkt_certificates WHERE id=?", (cert_id,)).fetchone()
    if not cert:
        raise HTTPException(404, "Certificate not found")
    path = CERT_DIR / cert["document_path"]
    if not path.exists():
        raise HTTPException(404, "Document file missing")

    ext = path.suffix.lower()
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    b64 = base64.standard_b64encode(path.read_bytes()).decode()

    if ext == ".pdf":
        doc_block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    elif ext in {".png", ".jpg", ".jpeg", ".webp"}:
        doc_block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
    else:
        raise HTTPException(400, "Unsupported document type for AI review")

    claimed = {
        "cert_type":   cert["cert_type_name"],
        "issuer":      cert["issuer"],
        "cert_number": cert["cert_number"],
        "issue_date":  cert["issue_date"],
        "expiry_date": cert["expiry_date"],
    }
    system = (
        "You are a sustainability-certificate verification assistant for an Indian e-commerce "
        "marketplace. You read an uploaded certificate document and assess whether it is a genuine, "
        "current sustainability/organic certificate that matches what the seller claimed. "
        "You do NOT have access to issuer registries — judge only from the document itself: legibility, "
        "presence of issuer name/logo, certificate number, holder name, issue & expiry dates, and whether "
        "the claimed details match the document. Be conservative: if anything is unreadable, missing, expired, "
        "or inconsistent, recommend 'manual' or 'reject'. Respond ONLY with a JSON object."
    )
    user_text = (
        "Seller's claimed details:\n" + json.dumps(claimed, indent=2) +
        "\n\nToday's date: " + datetime.now(timezone.utc).strftime("%Y-%m-%d") +
        "\n\nReturn JSON exactly: {\"extracted\":{\"issuer\":\"\",\"cert_number\":\"\","
        "\"holder\":\"\",\"issue_date\":\"\",\"expiry_date\":\"\"},"
        "\"matches_claim\":true,\"is_expired\":false,\"confidence\":0.0,"
        "\"recommendation\":\"approve|reject|manual\",\"reasons\":[\"\"]}"
    )
    try:
        msg = _claude().messages.create(
            model=SONNET,
            max_tokens=800,
            system=system,
            messages=[
                {"role": "user", "content": [doc_block, {"type": "text", "text": user_text}]},
                {"role": "assistant", "content": "{"},
            ],
        )
        raw = "{" + msg.content[0].text
        start, end = raw.find("{"), raw.rfind("}")
        result = json.loads(raw[start:end + 1])
    except Exception as e:
        logger.exception("AI cert review failed for cert %s", cert_id)
        raise HTTPException(502, f"AI review failed: {e}")

    rec = result.get("recommendation", "manual")
    with conn:
        conn.execute(
            "UPDATE mkt_certificates SET ai_recommendation=?, ai_extracted=? WHERE id=?",
            (rec, json.dumps(result.get("extracted", {})), cert_id),
        )
        conn.execute(
            "INSERT INTO mkt_verification_log (certificate_id, action, actor, notes) VALUES (?,?,?,?)",
            (cert_id, "ai_review", admin["email"], rec),
        )
    return {"ok": True, "ai": result}


@router.post("/api/market/admin/certificates/{cert_id}/decision")
def decide_certificate(cert_id: int, body: DecisionIn, admin=Depends(require_admin)):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")
    conn = get_conn()
    cert = conn.execute("SELECT id FROM mkt_certificates WHERE id=?", (cert_id,)).fetchone()
    if not cert:
        raise HTTPException(404, "Certificate not found")
    new_status = "verified" if body.decision == "approve" else "rejected"
    with conn:
        conn.execute(
            """UPDATE mkt_certificates
               SET status=?, verification_method='manual', reviewer_notes=?, verified_by=?, verified_at=?
               WHERE id=?""",
            (new_status, body.notes, admin["id"], _now(), cert_id),
        )
        conn.execute(
            "INSERT INTO mkt_verification_log (certificate_id, action, actor, notes) VALUES (?,?,?,?)",
            (cert_id, f"decision:{new_status}", admin["email"], body.notes),
        )
    return {"ok": True, "status": new_status}


@router.get("/api/market/admin/sellers")
def list_sellers(admin=Depends(require_admin)):
    rows = get_conn().execute(
        """SELECT s.*, u.email FROM mkt_sellers s JOIN users u ON u.id = s.user_id
           ORDER BY s.created_at DESC"""
    ).fetchall()
    return {"sellers": [dict(r) for r in rows]}


@router.post("/api/market/admin/sellers/{seller_id}/kyc")
def decide_kyc(seller_id: int, body: KycIn, admin=Depends(require_admin)):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")
    new_status = "approved" if body.decision == "approve" else "rejected"
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM mkt_sellers WHERE id=?", (seller_id,)).fetchone():
            raise HTTPException(404, "Seller not found")
        conn.execute("UPDATE mkt_sellers SET kyc_status=? WHERE id=?", (new_status, seller_id))
    return {"ok": True, "kyc_status": new_status}


@router.get("/api/market/admin/products/pending")
def pending_products(admin=Depends(require_admin)):
    rows = get_conn().execute(
        """SELECT p.*, s.business_name AS seller, c.name AS category
           FROM mkt_products p JOIN mkt_sellers s ON s.id = p.seller_id
           LEFT JOIN mkt_categories c ON c.id = p.category_id
           WHERE p.status='pending' ORDER BY p.updated_at"""
    ).fetchall()
    return {"products": [dict(r) for r in rows]}


@router.post("/api/market/admin/products/{product_id}/decision")
def decide_product(product_id: int, body: DecisionIn, admin=Depends(require_admin)):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")
    new_status = "listed" if body.decision == "approve" else "rejected"
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM mkt_products WHERE id=?", (product_id,)).fetchone():
            raise HTTPException(404, "Product not found")
        conn.execute(
            "UPDATE mkt_products SET status=?, reviewer_notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_status, body.notes, product_id),
        )
    return {"ok": True, "status": new_status}

#!/usr/bin/env python3
"""
Green Curve — Unified API entry point
Combines ai_api and supplier_api routers into one app.
Run: uvicorn main:app --host 127.0.0.1 --port 8000
"""

import logging
import logging.handlers
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ── Structured file logging ────────────────────────────────────────────────────
LOG_DIR = Path("/var/log/greencurve")
LOG_DIR.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")

_file_handler = logging.handlers.RotatingFileHandler(
    str(LOG_DIR / "api.log"),
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_fmt)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_file_handler, _console_handler],
)

logger = logging.getLogger("greencurve.main")

BASE_DIR = Path(__file__).parent

from ai_api import router as ai_router
from supplier_api import router as supplier_router
from auth_api import router as auth_router
from esg_api  import router as esg_router
from contact_api import router as contact_router
from dataroom_api import router as dataroom_router
from brsr_workspace_api import router as brsr_workspace_router
from collaboration_api import router as collaboration_router
from alerts_api import router as alerts_router
# Marketplace deferred to a future phase (legal/e-commerce regime not yet set up:
# CP E-Commerce Rules 2020, GST TCS / GSTR-8, FSSAI organic, intermediary safe-harbour).
# Code is preserved; re-enable this import and the lines below when ready to launch.
# from marketplace_api import router as marketplace_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Green Curve API starting up (pid=%s)", os.getpid())
    yield
    logger.info("Green Curve API shutting down")


app = FastAPI(
    title="Green Curve API",
    description="ESG & Climate Compliance Intelligence for India",
    version="1.0.0",
    docs_url=None,   # disable Swagger UI in production
    redoc_url=None,
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [
    "https://greencurve.solutions",
    "https://www.greencurve.solutions",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Api-Key"],
)

app.include_router(auth_router)
app.include_router(esg_router)
app.include_router(ai_router)
app.include_router(supplier_router)
app.include_router(contact_router)
app.include_router(dataroom_router)
app.include_router(brsr_workspace_router)
app.include_router(collaboration_router)
app.include_router(alerts_router)
# app.include_router(marketplace_router)  # deferred — see note above

# Serve static HTML/CSS/JS — must come AFTER API routes
app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")

# Marketplace media mount deferred along with the marketplace router (see note above).
# _PRODUCT_IMG_DIR = BASE_DIR / "uploads" / "products"
# _PRODUCT_IMG_DIR.mkdir(parents=True, exist_ok=True)
# app.mount("/media/products", StaticFiles(directory=str(_PRODUCT_IMG_DIR)), name="product_media")

HTML_FILES = [
    "admin", "calculator", "assurance", "brsr-generator", "brsr-simple",
    "analytics", "ccts", "esg-intelligence", "ghg-profile",
    "learn", "login", "methodology", "pricing", "privacy-policy", "supplier-form",
    "tcfd-checker", "tcfd", "terms-of-use", "value-chain", "data-room", "brsr-workspace", "team", "alerts",
    # "marketplace", "seller-dashboard", "marketplace-admin",  # deferred — see note above
]

@app.get("/")
async def serve_index():
    return FileResponse(str(BASE_DIR / "index.html"))

for _page in HTML_FILES:
    _path = f"/{_page}"
    _file = str(BASE_DIR / f"{_page}.html")

    def _make_handler(f):
        async def _handler():
            return FileResponse(f)
        return _handler

    app.get(_path)(_make_handler(_file))

@app.get("/health")
async def health():
    return {"status": "ok", "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}

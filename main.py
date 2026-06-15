#!/usr/bin/env python3
"""
Green Curve — Unified API entry point
Combines ai_api and supplier_api routers into one app.
Run: uvicorn main:app --host 127.0.0.1 --port 8000
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).parent

from ai_api import router as ai_router
from supplier_api import router as supplier_router
from auth_api import router as auth_router
from esg_api  import router as esg_router

app = FastAPI(
    title="Green Curve API",
    description="ESG & Climate Compliance Intelligence for India",
    version="1.0.0",
    docs_url=None,   # disable Swagger UI in production
    redoc_url=None,
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

# Serve static HTML/CSS/JS — must come AFTER API routes
app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")

HTML_FILES = [
    "admin", "calculator", "assurance", "brsr-generator", "brsr-simple",
    "analytics", "ccts", "esg-intelligence", "ghg-profile",
    "learn", "login", "methodology", "privacy-policy", "supplier-form",
    "tcfd-checker", "tcfd", "terms-of-use", "value-chain",
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

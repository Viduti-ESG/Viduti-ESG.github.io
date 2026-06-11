#!/usr/bin/env python3
"""
Green Curve — Unified API entry point
Combines ai_api and supplier_api routers into one app.
Run: uvicorn main:app --host 127.0.0.1 --port 8000
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from ai_api import router as ai_router
from supplier_api import router as supplier_router

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
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(ai_router)
app.include_router(supplier_router)

# Serve static HTML/CSS/JS — must come AFTER API routes
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

HTML_FILES = [
    "calculator", "assurance", "brsr-generator", "brsr-simple",
    "analytics", "ccts", "esg-intelligence", "ghg-profile",
    "learn", "methodology", "privacy-policy", "supplier-form",
    "tcfd-checker", "tcfd", "terms-of-use", "value-chain",
]

@app.get("/")
async def serve_index():
    return FileResponse("index.html")

for _page in HTML_FILES:
    _path = f"/{_page}"
    _file = f"{_page}.html"

    def _make_handler(f):
        async def _handler():
            return FileResponse(f)
        return _handler

    app.get(_path)(_make_handler(_file))

@app.get("/health")
async def health():
    return {"status": "ok", "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}

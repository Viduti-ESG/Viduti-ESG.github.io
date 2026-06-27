#!/usr/bin/env python3
"""
Green Curve — Semantic Search Index Builder  (OFFLINE, run-once / on data refresh)
==================================================================================

Builds a CPU-only embedding index over all companies so the site can answer
*natural-language* queries like:

    "cement makers with high water risk in western India"
    "renewable energy firms with strong governance"
    "textile exporters exposed to forced-labour supply-chain risk"

…instead of only exact name / CIN substring matching.

Why this approach (and what it is NOT)
--------------------------------------
* Model: BAAI/bge-small-en-v1.5 via **fastembed** (ONNX Runtime, Apache-2.0).
  - Runs on CPU, ~130 MB model, no PyTorch, low RAM — fits the existing VM.
  - It is *production-legal* (Apache-2.0), unlike NVIDIA's free hosted NIM API
    (trial-only) and NVIDIA NeMo embedding NIMs (GPU-required / NVAIE-licensed).
* The heavy work (embedding 1,200+ docs) happens HERE, offline. The running API
  only ever embeds the short user query at request time — cheap on CPU.

Output
------
  assets/data/company_embeddings.npz
    vectors   : float32 [N, dim]  (L2-normalised → cosine == dot product)
    names     : str   [N]   company_name
    cins      : str   [N]
    sectors   : str   [N]
    tiers     : str   [N]   risk_tier
    scores    : float [N]   esg_risk_score
    meta      : json  {model, dim, count, built_at, source}

Usage
-----
  python tools/build_embeddings.py                  # from esg_quotient.json
  python tools/build_embeddings.py --from-db        # from live greencurve.db
  python tools/build_embeddings.py --model BAAI/bge-base-en-v1.5
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_JSON = BASE_DIR / "assets" / "data" / "esg_quotient.json"
DEFAULT_DB = BASE_DIR / "greencurve.db"
OUT_PATH = BASE_DIR / "assets" / "data" / "company_embeddings.npz"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


# ── Build one searchable text document per company ────────────────────────────
def _as_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v:
        return [v]
    return []


def company_to_document(c: dict) -> str:
    """Flatten the fields a user would actually search on into one passage.

    Order matters a little: the most identifying / discriminating signal first
    (name, sector, products) then the qualitative risk narrative."""
    parts: list[str] = []
    name = (c.get("company_name") or "").strip()
    if name:
        parts.append(name)
    sector = (c.get("sector") or "").strip()
    if sector:
        parts.append(f"Sector: {sector}.")
    products = (c.get("products") or "").strip()
    if products:
        parts.append(f"Products and services: {products}.")

    tier = (c.get("risk_tier") or "").strip()
    if tier:
        parts.append(f"ESG risk tier: {tier}.")

    risks = [str(r) for r in _as_list(c.get("top_risk_factors")) if r]
    if risks:
        parts.append("Key ESG risk factors: " + "; ".join(risks) + ".")

    mats = [str(m) for m in _as_list(c.get("materials_exposed")) if m]
    if mats:
        parts.append("Materials / commodities exposed: " + ", ".join(mats) + ".")

    targets = [str(t) for t in _as_list(c.get("esg_targets")) if t]
    if targets:
        parts.append("ESG targets: " + "; ".join(targets) + ".")

    summary = (c.get("ai_summary") or "").strip()
    if summary:
        # ai_summary is the richest field but also the longest; cap it so one
        # company can't dominate the token budget of the encoder.
        parts.append(summary[:1500])

    return "\n".join(parts)


# ── Data sources ──────────────────────────────────────────────────────────────
def load_from_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("companies", [])


def load_from_db(path: Path) -> list[dict]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM companies").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for f in ("top_risk_factors", "materials_exposed", "esg_targets"):
            try:
                d[f] = json.loads(d.get(f) or "[]")
            except Exception:
                d[f] = []
        out.append(d)
    conn.close()
    return out


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Build the semantic-search embedding index.")
    ap.add_argument("--from-db", action="store_true", help="read companies from greencurve.db instead of esg_quotient.json")
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--batch-size", type=int, default=16,
                    help="encoder batch size; keep small on low-RAM hosts (ONNX pads to "
                         "the longest doc in a batch, so big batches blow up memory)")
    args = ap.parse_args()

    if args.from_db:
        if not args.db.exists():
            print(f"ERROR: DB not found: {args.db}", file=sys.stderr)
            return 1
        companies = load_from_db(args.db)
        source = f"db:{args.db.name}"
    else:
        if not args.json.exists():
            print(f"ERROR: JSON not found: {args.json}", file=sys.stderr)
            return 1
        companies = load_from_json(args.json)
        source = f"json:{args.json.name}"

    companies = [c for c in companies if (c.get("company_name") or "").strip()]
    if not companies:
        print("ERROR: no companies to index", file=sys.stderr)
        return 1

    print(f"Loaded {len(companies)} companies from {source}")
    docs = [company_to_document(c) for c in companies]

    # Import here so `--help` works without the dependency installed.
    from fastembed import TextEmbedding

    print(f"Loading embedding model: {args.model} (first run downloads ~130 MB)...")
    model = TextEmbedding(model_name=args.model)

    print(f"Embedding documents (CPU, batch_size={args.batch_size})...")
    vectors = np.array(list(model.embed(docs, batch_size=args.batch_size)), dtype=np.float32)

    # L2-normalise so cosine similarity is a plain dot product at query time.
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vectors = vectors / norms

    names = np.array([c.get("company_name", "") for c in companies], dtype=object)
    cins = np.array([c.get("cin", "") or "" for c in companies], dtype=object)
    sectors = np.array([c.get("sector", "") or "" for c in companies], dtype=object)
    tiers = np.array([c.get("risk_tier", "") or "" for c in companies], dtype=object)
    scores = np.array([float(c.get("esg_risk_score") or 0) for c in companies], dtype=np.float32)

    meta = {
        "model": args.model,
        "dim": int(vectors.shape[1]),
        "count": int(vectors.shape[0]),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        vectors=vectors,
        names=names,
        cins=cins,
        sectors=sectors,
        tiers=tiers,
        scores=scores,
        meta=np.array(json.dumps(meta), dtype=object),
    )
    size_mb = args.out.stat().st_size / (1024 * 1024)
    # Plain ASCII only — the Windows console (cp1252) can't encode ✓/× and would
    # crash on this final line *after* the index was already written.
    print(f"[OK] Wrote {args.out}  ({vectors.shape[0]} x {vectors.shape[1]}, {size_mb:.1f} MB)")
    print(f"     meta: {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Green Curve — Semantic (natural-language) company search
========================================================

Adds  GET /api/esg/search?q=...  so users can search the ~1,200-company ESG
universe by *meaning*, not just exact name / CIN substrings:

    /api/esg/search?q=cement makers with high water risk
    /api/esg/search?q=renewable energy firms with strong governance&k=10
    /api/esg/search?q=forced labour supply chain risk&sector=Textiles

How it works
------------
* An offline-built index (assets/data/company_embeddings.npz) holds one
  L2-normalised embedding per company — see tools/build_embeddings.py.
* At request time we embed ONLY the short query (cheap on CPU) with the same
  Apache-2.0 bge-small model via fastembed (ONNX, no PyTorch), then rank by
  cosine similarity (a dot product, since vectors are normalised).

Cost / licensing
----------------
* ₹0 / month, CPU-only, production-legal (Apache-2.0). No Claude API call, no
  NVIDIA NIM (their hosted API is trial-only; their NeMo embeddings need a GPU).

Graceful degradation
--------------------
* If the index or fastembed isn't available on the host, the endpoint falls
  back to a simple keyword/substring search over the DB so it never hard-fails.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from db import get_conn

# numpy (and fastembed, imported in _load_index) are only needed for the
# *semantic* path. Import numpy lazily/safely so that on a host without these
# deps the module still imports cleanly and the endpoint serves keyword search
# instead of bringing down the whole app at `from search_api import router`.
try:
    import numpy as np
except Exception:  # pragma: no cover - numpy not installed on this host
    np = None

logger = logging.getLogger("greencurve.search")

router = APIRouter()
BASE_DIR = Path(__file__).parent
INDEX_PATH = BASE_DIR / "assets" / "data" / "company_embeddings.npz"

# bge-small wants this instruction prepended to *queries* (not documents) for
# best retrieval quality. Keep it in sync with the model used at build time.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

# ── Lazy singletons (loaded on first search, never at import/startup) ──────────
_lock = threading.Lock()
_index: Optional[dict] = None        # {vectors, names, cins, sectors, tiers, scores, meta}
_model = None                        # fastembed.TextEmbedding
_load_failed = False                 # once True we stay in keyword-fallback mode


def _load_index() -> Optional[dict]:
    global _index, _model, _load_failed
    if _index is not None:
        return _index
    if _load_failed:
        return None
    with _lock:
        if _index is not None:
            return _index
        if _load_failed:
            return None
        try:
            if np is None:
                raise ModuleNotFoundError("numpy not installed")
            if not INDEX_PATH.exists():
                raise FileNotFoundError(f"embedding index missing: {INDEX_PATH}")
            npz = np.load(INDEX_PATH, allow_pickle=True)
            meta = json.loads(str(npz["meta"]))
            idx = {
                "vectors": npz["vectors"].astype(np.float32),
                "names": npz["names"],
                "cins": npz["cins"],
                "sectors": npz["sectors"],
                "tiers": npz["tiers"],
                "scores": npz["scores"],
                "meta": meta,
            }
            from fastembed import TextEmbedding
            model = TextEmbedding(model_name=meta["model"])

            _index = idx
            _model = model
            logger.info(
                "Semantic search ready: %d companies, model=%s, dim=%s",
                meta.get("count"), meta.get("model"), meta.get("dim"),
            )
            return _index
        except Exception as e:
            _load_failed = True
            logger.warning("Semantic search unavailable, falling back to keyword: %s", e)
            return None


def _embed_query(text: str) -> np.ndarray:
    vec = np.array(list(_model.query_embed(QUERY_INSTRUCTION + text))[0], dtype=np.float32)
    n = np.linalg.norm(vec)
    return vec / n if n else vec


# ── Keyword fallback (also used when index is absent) ─────────────────────────
# Generic words that carry no discriminating signal in an ESG corpus — dropping
# them stops a query like "companies with high risk" from matching everything.
_STOPWORDS = {
    "the", "and", "with", "for", "from", "that", "this", "are", "has", "have",
    "company", "companies", "limited", "ltd", "firm", "firms", "business",
    "high", "low", "risk", "esg", "exposed", "exposure", "india", "indian",
}


def _tokenize(q: str) -> list[str]:
    """Split a natural-language query into meaningful >=3-char tokens."""
    import re
    toks = re.findall(r"[a-zA-Z0-9]+", q.lower())
    seen, out = set(), []
    for t in toks:
        if len(t) >= 3 and t not in _STOPWORDS and t not in seen:
            seen.add(t)
            out.append(t)
    return out or [t for t in toks if t]  # if everything was a stopword, keep raw


def _keyword_search(q: str, k: int, sector: Optional[str]) -> list[dict]:
    """Token-based fallback: rank by how many query words appear in the company's
    searchable text (name/products/sector/summary), not by matching the whole
    phrase as one substring (which fails for any multi-word query)."""
    tokens = _tokenize(q)
    if not tokens:
        return []
    # Score = number of distinct query tokens found in the concatenated text blob.
    blob = "(company_name||' '||products||' '||sector||' '||COALESCE(ai_summary,''))"
    score_expr = " + ".join([f"(CASE WHEN {blob} LIKE ? THEN 1 ELSE 0 END)" for _ in tokens])
    token_params = [f"%{t}%" for t in tokens]

    where = f"({score_expr}) > 0"
    sector_params: list = []
    if sector:
        where += " AND sector = ?"
        sector_params.append(sector)

    # Param order must follow the SQL text: score_expr in SELECT, then in WHERE,
    # then the optional sector filter, then LIMIT.
    params = token_params + token_params + sector_params + [k]
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT company_name, cin, sector, risk_tier, esg_risk_score, "
            f"  ({score_expr}) AS match_score "
            f"FROM companies WHERE {where} "
            f"ORDER BY match_score DESC, esg_risk_score DESC LIMIT ?",
            params,
        ).fetchall()
    return [
        {
            "company_name": r["company_name"],
            "cin": r["cin"] or "",
            "sector": r["sector"] or "",
            "risk_tier": r["risk_tier"] or "",
            "esg_risk_score": r["esg_risk_score"] or 0,
            "score": None,  # no semantic score in fallback mode
        }
        for r in rows
    ]


# ── Endpoint ──────────────────────────────────────────────────────────────────
@router.get("/api/esg/search")
def semantic_search(
    q: str = Query(..., min_length=2, max_length=200, description="natural-language query"),
    k: int = Query(20, ge=1, le=100),
    sector: Optional[str] = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=1.0, description="cosine cutoff; 0 = no filter"),
):
    q = q.strip()
    idx = _load_index()

    # Fallback path — semantic index unavailable on this host.
    if idx is None:
        kw = _keyword_search(q, k, sector)
        return JSONResponse({
            "query": q,
            "mode": "keyword",
            "count": len(kw),
            "results": kw,
        })

    qvec = _embed_query(q)
    sims = idx["vectors"] @ qvec  # cosine, vectors are normalised

    sectors = idx["sectors"]
    mask = None
    if sector:
        mask = np.array([str(s).lower() == sector.lower() for s in sectors])
    if min_score > 0:
        sm = sims >= min_score
        mask = sm if mask is None else (mask & sm)

    candidate_idx = np.where(mask)[0] if mask is not None else np.arange(len(sims))
    if candidate_idx.size == 0:
        return JSONResponse({"query": q, "mode": "semantic", "count": 0, "results": []})

    cand_sims = sims[candidate_idx]
    top_n = min(k, candidate_idx.size)
    # argpartition is O(n) vs a full sort — matters at request time on CPU.
    part = np.argpartition(-cand_sims, top_n - 1)[:top_n]
    order = part[np.argsort(-cand_sims[part])]
    winners = candidate_idx[order]

    results = [
        {
            "company_name": str(idx["names"][i]),
            "cin": str(idx["cins"][i]),
            "sector": str(idx["sectors"][i]),
            "risk_tier": str(idx["tiers"][i]),
            "esg_risk_score": round(float(idx["scores"][i]), 2),
            "score": round(float(sims[i]), 4),
        }
        for i in winners
    ]
    return JSONResponse({
        "query": q,
        "mode": "semantic",
        "model": idx["meta"].get("model"),
        "count": len(results),
        "results": results,
    })


@router.get("/api/esg/search/health")
def search_health():
    idx = _load_index()
    if idx is None:
        return {"ready": False, "mode": "keyword-fallback"}
    return {"ready": True, "mode": "semantic", **idx["meta"]}

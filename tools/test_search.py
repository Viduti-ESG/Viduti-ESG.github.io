#!/usr/bin/env python3
"""
Smoke-test the semantic search index quality (offline, no server needed).

Loads assets/data/company_embeddings.npz + the same fastembed model and prints
the top matches for a handful of natural-language queries so we can eyeball
relevance before wiring it into the live API.

  python tools/test_search.py
  python tools/test_search.py "your own query here"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX = BASE_DIR / "assets" / "data" / "company_embeddings.npz"
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

DEFAULT_QUERIES = [
    "cement makers with high water risk",
    "renewable energy firms with strong governance",
    "textile exporters exposed to labour and supply chain risk",
    "banks with climate transition exposure",
    "pharma companies with effluent and pollution risk",
]


def main() -> int:
    if not INDEX.exists():
        print(f"ERROR: index not found: {INDEX}\nRun tools/build_embeddings.py first.", file=sys.stderr)
        return 1
    npz = np.load(INDEX, allow_pickle=True)
    meta = json.loads(str(npz["meta"]))
    vectors = npz["vectors"].astype(np.float32)
    names, sectors, tiers, scores = npz["names"], npz["sectors"], npz["tiers"], npz["scores"]
    print(f"Index: {meta['count']} companies · model={meta['model']} · dim={meta['dim']}\n")

    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=meta["model"])

    queries = sys.argv[1:] or DEFAULT_QUERIES
    for q in queries:
        qv = np.array(list(model.query_embed(QUERY_INSTRUCTION + q))[0], dtype=np.float32)
        qv /= (np.linalg.norm(qv) or 1.0)
        sims = vectors @ qv
        top = np.argsort(-sims)[:8]
        print(f"🔎 {q}")
        for i in top:
            print(f"   {sims[i]:.3f}  {str(names[i])[:42]:42}  {str(sectors[i])[:24]:24}  {str(tiers[i])}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

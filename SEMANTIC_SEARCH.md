# Semantic ESG Search — Green Curve

Natural-language search over the ~1,200-company ESG universe. Users describe what
they want in plain English ("cement makers with high water risk") and get the
closest companies ranked by **meaning**, not just name/CIN substring matches.

## Why this exists / what it is

| | |
|---|---|
| **Cost** | ₹0 / month — CPU only, no third-party AI API call per query |
| **License** | Apache-2.0 (`BAAI/bge-small-en-v1.5` via `fastembed`/ONNX) — **production-legal** |
| **Runtime dep** | `fastembed` (ONNX Runtime, ~130 MB model, **no PyTorch**) — runs on the existing VM |
| **Privacy** | No data leaves the server; nothing sent to Claude/OpenAI/NVIDIA |

> Deliberately **not** NVIDIA NeMo embeddings (GPU-required, NVAIE-licensed) and
> **not** NVIDIA's free hosted NIM API (trial-only, forbidden in production). See
> the memory note `project_oracle_paid_upgrade` for the full reasoning.

## Architecture

```
tools/build_embeddings.py   (OFFLINE, run-once / on data refresh)
   esg_quotient.json ──► one text doc per company ──► bge-small embeddings
                                                   ──► assets/data/company_embeddings.npz

search_api.py               (RUNTIME, in the FastAPI app)
   GET /api/esg/search?q=... ──► embed the SHORT query only ──► cosine vs index ──► top-k

search.html                 (UI at /search)
```

The expensive step (embedding 1,200+ docs) is done **offline**. The live API only
embeds the user's short query — cheap on CPU.

## Files added

- `tools/build_embeddings.py` — builds `company_embeddings.npz` (offline).
- `tools/test_search.py` — eyeball relevance for sample queries (offline).
- `search_api.py` — `GET /api/esg/search`, `GET /api/esg/search/health` router.
- `search.html` — `/search` page UI.
- `main.py` — wires the router + the `/search` page (2 lines).
- `requirements.txt` — adds `fastembed`, `numpy`.

## Deploy steps

> **Build the index off-box, ship the `.npz`.** Building embeds 1,200+ docs and
> needs more RAM than serving does (it OOM'd at the default batch size on a small
> box — that's why `--batch-size` defaults to 16). The running API only embeds the
> short *query* per request, which is cheap. So generate the 1.7 MB index on a dev
> machine (or the current box when idle) and copy it up; don't build on the micro VM.

```bash
# 1. On a dev machine — (re)build the index and sanity-check it
python tools/build_embeddings.py            # -> assets/data/company_embeddings.npz
python tools/test_search.py                 # eyeball relevance

# 2. Copy artifact + new code to the server
scp assets/data/company_embeddings.npz  user@vm:/path/to/esg-site/assets/data/
scp search_api.py search.html            user@vm:/path/to/esg-site/
#   (also push the main.py + requirements.txt edits)

# 3. On the VM, as www-data
pip install -r requirements.txt             # adds fastembed + onnxruntime (no PyTorch)
sudo systemctl restart greencurve
curl -s localhost:8000/api/esg/search/health   # -> {"ready":true,"mode":"semantic",...}
```

If you'd rather build on the server, it's supported (`python tools/build_embeddings.py
--from-db --batch-size 8`) — just keep the batch size low and watch RAM.

**Rebuild the index whenever company data changes** (re-score / re-import). It is a
static artifact; stale data in = stale results out.

> **nginx:** `/api/esg/*` already routes to the main app (:8000), so no nginx change
> is needed for the API. The `/search` page is served by the app's HTML route.

## API

```
GET /api/esg/search?q=<text>&k=20&sector=<optional>&min_score=0.0
```
Returns:
```json
{
  "query": "cement makers with high water risk",
  "mode": "semantic",
  "model": "BAAI/bge-small-en-v1.5",
  "count": 20,
  "results": [
    {"company_name": "...", "cin": "...", "sector": "...",
     "risk_tier": "High", "esg_risk_score": 71.2, "score": 0.62}
  ]
}
```
`score` is cosine similarity in [0,1] (semantic mode) or `null` (keyword fallback).

## Graceful degradation

If `fastembed` or the `.npz` index is missing on the host, `/api/esg/search`
automatically falls back to SQL `LIKE` keyword search over name/products/sector/
summary — so the endpoint never hard-fails. `mode` in the response tells you which
path served the request.

## Footprint note (low-RAM VM)

`fastembed` + onnxruntime + the quantized model load lazily on the **first** query
(not at startup), and the resident set is well under what a 1 GB micro VM can hold
alongside the app — but if RAM is tight, the lazy load means the cost is only paid
when search is actually used. A CPU/RAM upgrade makes it snappier; it does **not**
require a GPU.

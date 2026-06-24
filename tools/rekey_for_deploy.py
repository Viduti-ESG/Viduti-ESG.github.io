"""Re-key rescored.json + fe_backfill.json to the LIVE DB's canonical company
names (matched by normalized name) so update_db.py matches every row and deletes
nothing. Writes *_deploy.json and reports any mismatches."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from data_clean import norm

B = Path(r"c:/Viduti")
live = json.loads((B / "_dq_backups/live_names.json").read_text(encoding="utf-8"))
resc = json.loads((B / "esg-site/tools/rescored.json").read_text(encoding="utf-8"))
feb = json.loads((B / "esg-site/tools/fe_backfill.json").read_text(encoding="utf-8"))
meta = json.loads((B / "esg-site/tools/meta_backfill.json").read_text(encoding="utf-8"))

resc_by_norm = {norm(k): (k, v) for k, v in resc.items()}
feb_by_norm = {norm(k): v for k, v in feb.items()}
meta_by_norm = {norm(k): v for k, v in meta.items()}

out_resc, out_feb, out_meta, missing = {}, {}, {}, []
for ln in live:
    n = norm(ln)
    if n in resc_by_norm:
        out_resc[ln] = resc_by_norm[n][1]
    else:
        missing.append(ln)
    if n in feb_by_norm:
        out_feb[ln] = feb_by_norm[n]
    if n in meta_by_norm:
        out_meta[ln] = meta_by_norm[n]

extra = [resc_by_norm[n][0] for n in resc_by_norm if n not in {norm(x) for x in live}]

(B / "esg-site/tools/rescored_deploy.json").write_text(json.dumps(out_resc), encoding="utf-8")
(B / "esg-site/tools/fe_backfill_deploy.json").write_text(json.dumps(out_feb), encoding="utf-8")
(B / "esg-site/tools/meta_backfill_deploy.json").write_text(json.dumps(out_meta), encoding="utf-8")

print(f"live names:            {len(live)}")
print(f"rescored matched:      {len(out_resc)}/{len(live)}")
print(f"fe_backfill matched:   {len(out_feb)}/{len(live)}")
print(f"meta matched:          {len(out_meta)}/{len(live)}")
print(f"live names NOT in my data (would stay stale): {len(missing)}")
for m in missing[:15]: print("   MISSING:", m)
print(f"my records NOT in live (ignored, not deleted): {len(extra)}")
for e in extra[:15]: print("   EXTRA:", e)

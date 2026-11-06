"""Re-apply extraction rules + scoring to all stored listings (run after editing config.yaml)."""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finder.extract import extract  # noqa: E402
from finder.pipeline import Pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

p = Pipeline()
for L in p.idx.values():
    keep_ai = L.get("ai_summary")
    raw = dict(L)
    for k in ("model_key", "model_name"):  # let rules recompute with new config (keep page fields)
        raw.pop(k, None)
    L.update(extract(raw, p.cfg))
    L["ai_summary"] = keep_ai
p.finish({"trigger": "rescore"})

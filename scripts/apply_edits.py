"""Apply what visitors did on the website: new links (pending) + edits (overrides). Fast: no browser."""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finder import http, store  # noqa: E402
from finder.pipeline import Pipeline  # noqa: E402
from finder.web import process_pending, record_hidden  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    http.DELAY = 1.0
    p = Pipeline()
    todo = process_pending(p)
    p.finish({"trigger": "web", "by": "، ".join({(s.get("by") or "زائر") for s in todo}) or "تعديل"})
    record_hidden(p)
    store.save(p.db)

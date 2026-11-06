"""JSON data store living inside docs/ so GitHub Pages can serve it."""
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data", "listings.json")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict:
    if os.path.exists(DATA):
        with open(DATA, encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": None, "listings": [], "stats": {}, "runs": []}


def save(db: dict):
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    db["updated_at"] = now()
    db["listings"].sort(key=lambda L: (L.get("archived", False), -L.get("score", 0)))
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))


def index(db: dict) -> dict:
    return {L["id"]: L for L in db["listings"]}


EDITS = os.path.join(ROOT, "docs", "data", "edits.json")


def load_edits() -> dict:
    """Edits written by the website (through the Apps Script bridge). Never written by workflows."""
    try:
        with open(EDITS, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("pending", [])
    d.setdefault("overrides", {})
    return d

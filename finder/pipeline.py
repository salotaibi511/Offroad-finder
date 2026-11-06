"""Glue: raw listing → extraction → (AI) → upsert → scoring → notifications."""
import logging
import os
from datetime import datetime, timedelta, timezone

import yaml

from . import llm, notify, store
from .extract import extract
from .score import market_stats, score
from .sources import generic, haraj

log = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict:
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class Pipeline:
    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()
        self.db = store.load()
        self.idx = store.index(self.db)
        self.ai_budget = self.cfg.get("llm", {}).get("max_per_run", 40) if llm.available(self.cfg) else 0
        self.added, self.updated = [], []
        self.edits = store.load_edits()
        self.ignored = set(self.db.get("ignored", []))
        self.hidden_now = []

    # ---------- user edits from the website ----------
    def apply_override(self, L: dict):
        ov = self.edits["overrides"].get(L["id"])
        if not ov:
            return L
        fields = ov.get("fields") or {}
        for k in ("title", "price", "year", "mileage_km", "city", "is_4x4", "transmission", "fuel", "model_key"):
            if k in fields and fields[k] not in ("", None):
                L[k] = fields[k]
        if "price" in fields and fields["price"]:
            L["price"], L["price_type"] = int(fields["price"]), "asking"
        if "model_key" in fields and fields["model_key"] in self.cfg["models"]:
            L["model_name"] = self.cfg["models"][fields["model_key"]]["name"]
        if "city" in fields and fields["city"]:
            from .extract import CITY_KM, REGION
            from .textnorm import norm
            c = next((k for k in CITY_KM if norm(k) == norm(fields["city"])), fields["city"])
            L["city"], L["distance_km"], L["region"] = c, CITY_KM.get(c), REGION.get(c)
        if fields:
            L["edited"] = {"by": ov.get("by"), "at": ov.get("at"), "fields": sorted(fields)}
        if ov.get("status"):
            L["status"] = ov["status"]
        if ov.get("notes"):
            L["web_notes"] = ov["notes"]
        if ov.get("hidden"):
            L["user_hidden"] = True
        return L

    def should_hide(self, L: dict):
        if L.get("user_hidden"):
            return "أُخفي من الموقع"
        if L.get("non_car"):
            return f"ليس سيارة ({L['non_car']})"
        if L.get("parts_car"):
            return "قطع غيار/تشليح"
        if L.get("source") == "haraj" and not L.get("year") and not str(L.get("added_by", "auto")).count("+") \
                and L.get("added_by", "auto") == "auto":
            return "بدون سنة صنع (غالبًا ليس سيارة)"
        return None

    # ---------- fetching ----------
    def fetch(self, url: str) -> dict:
        return haraj.fetch(url) if haraj.is_haraj(url) else generic.fetch(url)

    def expand(self, url: str) -> list:
        """A submitted URL may be a single ad or a search page → list of ad URLs."""
        url = url.strip()
        if haraj.is_haraj(url):
            if haraj.is_listing_url(url):
                return [url]
            from .http import get_html
            return [x["url"] for x in haraj.parse_search(get_html(url) or "")]
        if generic.looks_like_listing(url):
            return [url]
        return [x["url"] for x in generic.search(url)]

    # ---------- ingest ----------
    def ingest(self, raw: dict, added_by="auto", note=None) -> dict | None:
        if not raw or not raw.get("title"):
            return None
        ts = store.now()
        fields = extract(raw, self.cfg)
        old = self.idx.get(raw["id"])
        body_changed = not old or (old.get("body") != raw.get("body"))
        if self.ai_budget > 0 and body_changed:
            self.ai_budget -= 1
            fields = llm.merge(fields, llm.analyse(raw, self.cfg), self.cfg)
        elif old and old.get("ai_summary"):
            fields["ai_summary"] = old["ai_summary"]

        rec = {k: raw.get(k) for k in ("id", "source", "url", "title", "body", "images")}
        rec.update(fields)
        self.ignored.discard(rec["id"])
        rec["last_seen"] = rec["last_fetched"] = ts
        if old:
            for k in ("status", "notes", "added_by", "first_seen", "notified", "price_history", "votes"):
                if k in old:
                    rec[k] = old[k]
            if rec.get("price") and old.get("price") and rec["price"] != old["price"]:
                rec.setdefault("price_history", []).append({"date": ts[:10], "price": rec["price"]})
                if rec["price"] < old["price"]:
                    rec["_price_drop"] = old["price"]
            rec["archived"] = False
            self.updated.append(rec["id"])
        else:
            rec.update({"status": "جديد", "notes": [], "added_by": added_by, "first_seen": ts,
                        "notified": False, "archived": False,
                        "price_history": [{"date": ts[:10], "price": rec["price"]}] if rec.get("price") else []})
            self.added.append(rec["id"])
        if note:
            rec.setdefault("notes", []).append({"by": added_by, "date": ts[:10], "text": note})
        if added_by != "auto" and old and old.get("added_by") == "auto":
            rec["added_by"] = f"auto+{added_by}"
        self.apply_override(rec)
        self.idx[rec["id"]] = rec
        return rec

    def touch(self, lid: str):
        if lid in self.idx:
            self.idx[lid]["last_seen"] = store.now()
            self.idx[lid]["archived"] = False

    # ---------- finish ----------
    def finish(self, run_info=None):
        listings = []
        for L in self.idx.values():
            self.apply_override(L)
            why = self.should_hide(L)
            if why:
                self.ignored.add(L["id"])
                self.hidden_now.append((L["id"], why))
            else:
                listings.append(L)
        self.db["ignored"] = sorted(self.ignored)[-20000:]
        stats = market_stats([L for L in listings if not L.get("archived")])
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.cfg.get("archive_after_days", 45))
        ncfg = self.cfg.get("notify", {})
        sent = 0
        for L in listings:
            seen = _parse_ts(L.get("last_seen"))
            if seen and seen < cutoff and L.get("status") == "جديد":
                L["archived"] = True
            L.update(score(L, self.cfg, stats))
            good = L["label"] in ("فرصة", "يستحق السؤال") and L["score"] >= ncfg.get("min_score", 70)
            if ncfg.get("telegram") and good and not L.get("archived"):
                if not L.get("notified"):
                    if notify.send(L, "🟢 عرض جديد مناسب"):
                        sent += 1
                    L["notified"] = True
                elif L.get("_price_drop") and ncfg.get("price_drop"):
                    notify.send(L, f"📉 نزل السعر من {L['_price_drop']:,}")
            L.pop("_price_drop", None)
        self.db["listings"] = listings
        self.db["stats"] = {k: v for k, v in stats.items() if "|" not in k}
        self.db["stats_names"] = {k: m["name"] for k, m in self.cfg["models"].items()}
        self.db["requirements"] = self.cfg["requirements"]
        if run_info:
            run_info.update({"at": store.now(), "added": len(self.added), "updated": len(self.updated),
                             "notified": sent})
            self.db["runs"] = ([run_info] + self.db.get("runs", []))[:30]
        store.save(self.db)
        log.info("saved: %d new, %d updated, %d notified", len(self.added), len(self.updated), sent)

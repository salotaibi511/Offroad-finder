"""Website submissions (pending links) handling, shared by the api and collect workflows."""
import logging

log = logging.getLogger(__name__)


def process_pending(p):
    subs = p.db.setdefault("submissions", {})
    todo = [s for s in p.edits["pending"] if s.get("sid") and s["sid"] not in subs]
    for s in todo[:15]:
        url, by = (s.get("url") or "").strip(), (s.get("by") or "زائر")[:40]
        res = {"url": url, "at": s.get("at"), "ids": [], "hidden": [], "error": None}
        try:
            ads = p.expand(url)[:40]
            if not ads:
                res["error"] = "لم أجد إعلانًا في الرابط"
            for ad in ads:
                rec = p.ingest(p.fetch(ad), added_by=by, note=s.get("note") or None)
                if rec:
                    res["ids"].append(rec["id"])
                else:
                    res["error"] = "تعذر قراءة الإعلان"
        except Exception as e:  # noqa: BLE001
            log.warning("submission %s failed: %s", url, e)
            res["error"] = f"تعذر فتح الرابط ({type(e).__name__})"
        subs[s["sid"]] = res
    return todo


def record_hidden(p):
    hidden = dict(p.hidden_now)
    subs = p.db.setdefault("submissions", {})
    for res in subs.values():
        for i in list(res.get("ids", [])):
            if i in hidden:
                res["ids"].remove(i)
                res["hidden"].append(hidden[i])
    # keep the submissions log small
    if len(subs) > 300:
        for k in sorted(subs, key=lambda k: subs[k].get("at") or "")[:-300]:
            subs.pop(k)

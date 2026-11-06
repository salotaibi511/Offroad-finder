"""Scheduled run: search all configured sources, fetch new ads, score, notify, save."""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finder import http  # noqa: E402
from finder.pipeline import Pipeline, _parse_ts  # noqa: E402
from finder.sources import generic, haraj  # noqa: E402
from finder.extract import is_non_car  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("collect")


def main():
    p = Pipeline()
    hcfg = p.cfg["sources"]["haraj"]
    http.DELAY = hcfg.get("delay_seconds", 2.5)
    budget = hcfg.get("max_details_per_run", 60)
    run = {"queries": 0, "links": 0, "errors": 0}

    candidates = []  # (url, id)
    if hcfg.get("enabled"):
        for city in hcfg.get("cities") or [""]:
            for q in hcfg["queries"]:
                try:
                    items = haraj.search(q, city)
                except Exception as e:  # noqa: BLE001
                    log.warning("search failed %s: %s", q, e)
                    run["errors"] += 1
                    continue
                run["queries"] += 1
                run["links"] += len(items)
                for x in items:
                    if is_non_car(x["title"]):
                        run["skipped_non_car"] = run.get("skipped_non_car", 0) + 1
                        continue
                    candidates.append((x["url"], f"haraj:{x['id']}"))
    for su in p.cfg["sources"].get("extra_search_urls") or []:
        try:
            items = generic.search(su) if not haraj.is_haraj(su) else \
                [{"url": x["url"], "id": f"haraj:{x['id']}"} for x in haraj.parse_search(http.get_html(su))]
            candidates += [(x["url"], x["id"]) for x in items]
            run["links"] += len(items)
        except Exception as e:  # noqa: BLE001
            log.warning("extra search failed %s: %s", su, e)
            run["errors"] += 1

    # de-duplicate, new ads first, then stale good ones (re-check price)
    seen, new, recheck = set(), [], []
    stale = datetime.now(timezone.utc) - timedelta(hours=24)
    for url, lid in candidates:
        if lid in seen:
            continue
        seen.add(lid)
        old = p.idx.get(lid)
        if not old:
            new.append(url)
        else:
            p.touch(lid)
            last = _parse_ts(old.get("last_fetched"))
            if old.get("label") in ("فرصة", "يستحق السؤال") and (not last or last < stale):
                recheck.append(url)

    log.info("candidates=%d new=%d recheck=%d", len(seen), len(new), len(recheck))
    for url in (new + recheck)[:budget]:
        try:
            p.ingest(p.fetch(url))
        except Exception as e:  # noqa: BLE001
            log.warning("fetch failed %s: %s", url, e)
            run["errors"] += 1
    p.finish(run)
    if run["queries"] == 0 and hcfg.get("enabled"):
        log.error("Haraj returned nothing — the site may be blocking this runner.")
        sys.exit(2)


if __name__ == "__main__":
    main()

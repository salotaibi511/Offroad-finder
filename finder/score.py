"""Scoring and labelling of listings."""
from statistics import median

from .extract import CURRENT_YEAR

STATUS_CLOSED = {"مستبعد يدويًا", "تم الشراء", "مباع"}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def market_stats(listings: list) -> dict:
    """Median asking price per model and per model+5-year bucket, from collected data."""
    groups = {}
    for L in listings:
        if not L.get("price") or L.get("price_type") != "asking" or L.get("parts_car") or not L.get("model_key"):
            continue
        k = L["model_key"]
        groups.setdefault(k, []).append(L["price"])
        if L.get("year"):
            groups.setdefault(f"{k}|{L['year'] // 5 * 5}", []).append(L["price"])
    return {k: {"n": len(v), "median": int(median(v))} for k, v in groups.items() if len(v) >= 4}


def score(L: dict, cfg: dict, stats: dict) -> dict:
    req, w = cfg["requirements"], cfg["weights"]
    reasons_pos, reasons_neg, exclude = [], [], []
    price, ptype = L.get("price"), L.get("price_type")

    # ---- hard filters ----
    if price and price > req["max_price"]:
        exclude.append(f"السعر {price:,} أعلى من الميزانية")
    if L.get("year") and L["year"] < req["min_year"]:
        exclude.append(f"موديل {L['year']} أقدم من المطلوب")
    if L.get("mileage_km") and L["mileage_km"] > req["max_mileage_km"]:
        exclude.append(f"الممشى {L['mileage_km']:,} كم أعلى من الحد")
    if req.get("require_4x4") and L.get("is_4x4") is False:
        exclude.append("ليست دبل")
    if req.get("exclude_parts_cars") and L.get("parts_car"):
        exclude.append("للتشليح/قطع غيار")

    # ---- price value ----
    budget_v = None
    market_v = None
    med = None
    if price:
        ratio = price / req["max_price"]
        budget_v = 1.0 if ratio <= 0.6 else _clamp(1.0 - (ratio - 0.6) * 1.5)
        mk = L.get("model_key")
        if mk:
            s = stats.get(f"{mk}|{L['year'] // 5 * 5}") if L.get("year") else None
            s = s or stats.get(mk)
            if s:
                med = s["median"]
                rel = price / med
                market_v = _clamp((1.3 - rel) / 0.6)
                pct = round((1 - rel) * 100)
                if pct >= 10:
                    reasons_pos.append(f"أقل من متوسط السوق بـ {pct}% (متوسط {med:,})")
                elif pct <= -10:
                    reasons_neg.append(f"أعلى من متوسط السوق بـ {-pct}%")
        pv = budget_v if market_v is None else 0.6 * market_v + 0.4 * budget_v
        if ptype == "bid":
            pv *= 0.8
            reasons_neg.append("السعر المعروض سوم حالي وليس سعرًا نهائيًا")
    else:
        pv = 0.35
        reasons_neg.append("السعر غير مذكور" + (" (على السوم)" if ptype == "negotiable" else ""))

    # ---- model fit ----
    mk = L.get("model_key")
    fit = cfg["models"].get(mk, {}).get("fit", 0.3) if mk else 0.3
    if not mk:
        reasons_neg.append("الموديل غير واضح")
    elif fit >= 0.9:
        reasons_pos.append(f"{L.get('model_name')} ممتازة للبر")

    # ---- mileage ----
    km = L.get("mileage_km")
    if km is None:
        mv = 0.45
        reasons_neg.append("الممشى غير مذكور")
    else:
        good, mx = req.get("good_mileage_km", 250_000), req["max_mileage_km"]
        if km <= good:
            mv = 1.0
            if km <= good * 0.6:
                reasons_pos.append(f"ممشى منخفض ({km:,} كم)")
        elif km <= mx:
            mv = 1.0 - (km - good) / max(1, mx - good) * 0.7
        else:
            mv = 0.1
        if km > good + (mx - good) * 0.6:
            reasons_neg.append(f"ممشى عالٍ ({km:,} كم)")

    # ---- year ----
    y = L.get("year")
    if y:
        yv = _clamp((y - req["min_year"]) / max(1, 2012 - req["min_year"]), 0.1, 1.0)
    else:
        yv = 0.4
        reasons_neg.append("الموديل (السنة) غير مذكور")

    # ---- distance ----
    d = L.get("distance_km")
    if d is None:
        dv = 0.4
    elif d <= 100:
        dv = 1.0
        reasons_pos.append(f"قريبة ({L.get('city')})")
    elif d <= 200:
        dv = 0.85
    elif d <= 450:
        dv = 0.6
    elif d <= 900:
        dv = 0.35
    else:
        dv = 0.2
        reasons_neg.append(f"بعيدة ({L.get('city')} ~{d} كم)")

    # ---- condition ----
    sev, med_flags, green = L.get("red_flags_severe", []), L.get("red_flags", []), L.get("green_flags", [])
    cv = 0.65 + 0.07 * min(len(green), 4) - 0.2 * len(med_flags) - 0.45 * len(sev)
    if L.get("is_4x4") is None:
        cv -= 0.1
        reasons_neg.append("تأكد أنها دبل")
    cv = _clamp(cv)
    if sev:
        reasons_neg.append("إشارات خطيرة: " + "، ".join(sev))
    if med_flags:
        reasons_neg.append("ملاحظات: " + "، ".join(med_flags))
    if green:
        reasons_pos.append("إيجابيات: " + "، ".join(green))

    parts = {"price_value": pv, "model_fit": fit, "condition": cv, "mileage": mv, "year": yv, "distance": dv}
    total = sum(parts[k] * w[k] for k in w) / sum(w.values()) * 100
    total = round(total)

    if L.get("status") in STATUS_CLOSED:
        label = "مغلق"
    elif exclude:
        label = "مستبعد"
    elif total >= cfg["labels"]["opportunity"]:
        label = "فرصة"
    elif total >= cfg["labels"]["worth_asking"]:
        label = "يستحق السؤال"
    else:
        label = "ضعيف"

    return {
        "score": total,
        "label": label,
        "breakdown": {k: round(v * 100) for k, v in parts.items()},
        "reasons_pos": reasons_pos,
        "reasons_neg": reasons_neg,
        "exclude_reasons": exclude,
        "market_median": med,
    }

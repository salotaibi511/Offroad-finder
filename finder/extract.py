"""Rule-based extraction of car attributes from free Arabic ad text."""
import re
from datetime import date

from .textnorm import contains_any, digits, norm

CURRENT_YEAR = date.today().year

# Approximate road distance from Jeddah (km)
CITY_KM = {
    "جدة": 0, "جده": 0, "ذهبان": 25, "بحرة": 40, "الجموم": 60, "مكة": 80, "مكه": 80,
    "ثول": 90, "خليص": 100, "الكامل": 130, "رابغ": 150, "الطائف": 170, "الليث": 180,
    "تربة": 300, "ينبع": 330, "القنفذة": 340, "المويه": 350, "الخرمة": 380, "الباحة": 400,
    "المدينة": 420, "المدينة المنورة": 420, "رنية": 450, "املج": 500, "بيشة": 520,
    "عفيف": 550, "محايل": 560, "الوجه": 600, "أبها": 620, "خميس مشيط": 630,
    "الدوادمي": 650, "صبيا": 680, "جازان": 700, "جيزان": 700, "العلا": 700,
    "أبو عريش": 720, "الرس": 800, "نجران": 800, "عنيزة": 830, "بريدة": 850, "القصيم": 850,
    "حائل": 900, "الرياض": 950, "المجمعة": 950, "الخرج": 980, "تبوك": 1000,
    "حفر الباطن": 1200, "الأحساء": 1300, "الاحساء": 1300, "الهفوف": 1300, "سكاكا": 1300,
    "الجوف": 1300, "الدمام": 1350, "عرعر": 1350, "الخبر": 1360, "القطيف": 1380,
    "الظهران": 1360, "الجبيل": 1400, "القريات": 1500,
}

FOURX4_POS = ["دبل", "4x4", "4*4", "فور ويل", "فورويل", "دفع رباعي", "قير دبل", "جير دبل", "دبل شغال"]
FOURX4_NEG = ["غير دبل", "مو دبل", "ماهو دبل", "ما هو دبل", "مافيه دبل", "ما فيه دبل", "بدون دبل",
              "سنقل", "2x4", "4x2", "تو ويل", "دفع ثنائي"]
# phrases where "دبل" means double cabin, not four-wheel drive
DOUBLE_CAB = ["دبل قماره", "دبل غماره", "دبل كابينه", "دبل كبينه", "قمارتين", "غمارتين"]
# models that are almost always 4x4 in the Saudi market
DEFAULT_4X4 = {"land_cruiser", "lc70", "fj", "patrol", "pajero", "jimny", "wrangler", "lexus_lx_gx", "prado"}

RED_SEVERE = ["مقلوب", "مصدوم قوي", "تشريح", "سكراب", "للتشليح", "تشليح", "قطع غيار", "ماكينه خربانه",
              "مكينه خربانه", "ماكينه ضاربه", "مكينه ضاربه", "قير خربان", "جير خربان", "معطل", "ما يمشي",
              "مايمشي", "غرقان", "محروق", "واقف من"]
RED_MEDIUM = ["مصدوم", "حادث", "مضروب", "ماكينه مفتوحه", "مكينه مفتوحه", "قير مفتوح", "جير مفتوح",
              "يحتاج", "تبي", "يبي", "يبغاله", "يبغى له", "تهريب", "يهرب", "دخان", "يدخن", "استماره منتهيه",
              "بدون استماره", "فحص منتهي", "بدون فحص", "مرهون", "تنازل", "سمكره", "رش كامل", "صدا",
              "الدبل خربان", "دبل خربان", "الدبل ما يشتغل", "عليه مخالفات", "ما عليه فحص"]
GREEN = ["شرط", "ماكينه شرط", "مكينه شرط", "قير شرط", "جير شرط", "فحص جديد", "فحص ساري", "استماره جديده",
         "استماره ساريه", "بدون حوادث", "ما فيه حوادث", "مافيه حوادث", "نظيف", "نظيفه", "رش وكاله",
         "صبغ وكاله", "اسم واحد", "صيانه وكاله", "مجهز", "تجهيز بر", "ونش", "كفرات جديده", "اطارات جديده",
         "شاصي شرط", "ماكينه وكاله", "مكينه وكاله"]
PARTS = ["قطع غيار", "للتشليح", "تشليح", "سكراب", "تشريح"]
# title words that mean the ad is an accessory / part / other vehicle, not a car for sale
NON_CAR = ["دباب", "دبابه", "دبابات", "صاجه", "حمايه", "جنوط", "جنط", "كفرات", "كفر", "اطارات", "اطار", "طيس",
           "تكايه", "مرتبه", "مراتب", "صدام", "رفرف", "رفارف", "شبك", "اسطب", "اسطبات", "شمعات", "كبوت", "بودي",
           "سماعات", "شاشه", "تظليل", "لمبات", "ليتات", "مقاعد", "كراسي", "دعاسات", "غطاء", "جركل", "جراكل",
           "اغراض", "ونش", "دفلك", "سنوركل", "عفشه", "مساعدات", "قير", "مكينه", "ماكينه", "ماطور",
           "مطلوب", "ابغى", "ابغي", "ابي", "ابحث", "شراء", "عازل", "كمبيوتر", "كرونات", "كرون", "خطوط",
           "مكائن", "مكاين", "مسجل", "ديكور", "قطع", "طقم", "فرش", "دركسون", "رديتر", "كمبروسر", "دينمو",
           "سلف", "اسطوانه", "اسطوانات", "زجاج", "مرايا", "مرايه", "ستيكر", "بطاريه", "فلتر", "زيت"]
RENT = ["للايجار", "ايجار", "تاجير", "للتاجير", "توصيل", "نقل"]
OTHER_VEHICLES = ["دينا", "دينه", "هايس", "باص", "شاحنه", "تريله", "قلاب", "دباب", "دبابه", "بانشي"]
NON_CAR_CATEGORY = ["قطع غيار", "ملحقات", "اكسسوارات", "دبابات", "شاحنات", "معدات", "باص"]


def is_non_car(title: str, category: str = "") -> str | None:
    t = norm(title)
    words = [w for w in t.split() if w not in ("للبيع", "بيع", "عرض", "عاجل")]
    if contains_any(t, RENT):
        return "إيجار/خدمة"
    hits = contains_any(" ".join(words[:1]), NON_CAR) or contains_any(" ".join(words[:3]), OTHER_VEHICLES)
    if hits:
        return hits[0]
    c = norm(category)
    for w in NON_CAR_CATEGORY:
        if norm(w) in c:
            return w
    return None

_NUM = r"(\d{1,3}(?:[,\.]\d{3})+|\d+(?:\.\d+)?)"


def _to_number(s: str) -> float:
    s = s.replace(",", "")
    if s.count(".") == 1 and len(s.split(".")[1]) == 3:  # 15.000 thousands separator
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _thousands(val: float, unit: str, small_means_k: bool) -> int:
    if unit and norm(unit) in ("الف", "k"):
        val *= 1000
    elif unit and norm(unit) == "ريال":
        pass
    elif small_means_k and 0 < val < 1000:
        val *= 1000
    return int(val)


def parse_price(text: str):
    """Return (price, price_type) from free text. price_type: asking | negotiable | None."""
    t = norm(text)
    m = re.search(r"(?:السعر|سعره|بسعر|المطلوب|مطلوب|الحد|حده|حدها|نهايي|(?<![\w])ب)\s*[:：\-]?\s*" + _NUM +
                  r"\s*(الف|ريال|k)?", t)
    if m:
        p = _thousands(_to_number(m.group(1)), m.group(2) or "", True)
        if 3000 <= p <= 1_000_000:
            return p, "asking"
    m = re.search(_NUM + r"\s*(الف|ريال)(?:\s*(?:نهايي|فقط|وبس))?", t)
    if m and not re.search(r"ممشي|ممشاه|ماشي|عداد|كيلو|مشي", t[max(0, m.start() - 15):m.start()]):
        after = t[m.end():m.end() + 8]
        if "كيلو" not in after and "كم" not in after:
            p = _thousands(_to_number(m.group(1)), m.group(2), True)
            if 3000 <= p <= 1_000_000:
                return p, "asking"
    if re.search(r"السوم|علي السوم|سوم", t):
        return None, "negotiable"
    return None, None


def parse_mileage(text: str):
    t = norm(text)
    m = re.search(r"(?:ممشى|ممشي|ممشاه|ماشي|ماشيه|العداد|عداد|مشي|الممشى|الممشي)\s*[:：\-]?\s*(?:تقريبا\s*)?"
                  + _NUM + r"\s*(الف|كيلو|كم|km|k)?(?![\w])", t)
    if not m:
        m = re.search(_NUM + r"\s*(الف|k)\s*(?:كيلو|كم|km)", t)
    if not m:
        return None
    km = _thousands(_to_number(m.group(1)), m.group(2) or "", True)
    return km if 1000 <= km <= 2_000_000 else None


def parse_year(title: str, body: str = ""):
    for src in (title, body):
        t = norm(src)
        m = re.search(r"(?<![\w])(?:موديل|موديله|مودل|موديلها|model)\s*[:：\-]?\s*(19[6-9]\d|20[0-3]\d|\d{2})(?!\d)", t)
        if m:
            y = int(m.group(1))
            if y < 100:
                y = 2000 + y if y <= (CURRENT_YEAR % 100) + 1 else 1900 + y
            if 1960 <= y <= CURRENT_YEAR + 1:
                return y
        for m in re.finditer(r"(?<!\d)(19[6-9]\d|20[0-3]\d)(?!\d)", t):
            y = int(m.group(1))
            if 1960 <= y <= CURRENT_YEAR + 1:
                return y
    return None


def detect_model(text_n: str, models: dict):
    best = None
    for key, m in models.items():
        hits = contains_any(text_n, m.get("aliases", []))
        if hits:
            # prefer the longest alias match (more specific)
            ln = max(len(h) for h in hits)
            if best is None or ln > best[1]:
                best = (key, ln)
    return best[0] if best else None


def detect_city(text: str, given: str = ""):
    for src in (given, text):
        if not src:
            continue
        n = norm(src)
        for city in sorted(CITY_KM, key=len, reverse=True):
            if contains_any(n, [city]):
                return city
    return given or None


def extract(raw: dict, cfg: dict) -> dict:
    """raw: {title, body, city, price, price_type, mileage_km, year, ...} → structured fields."""
    title = raw.get("title") or ""
    body = raw.get("body") or ""
    extra = raw.get("fields_text") or ""
    full = f"{title}\n{body}\n{extra}"
    n = norm(full)

    # Haraj breadcrumb: حراج السيارات / البراند / الموديل / الموديل+السنة — most reliable model source
    cat_parts = [p.strip() for p in (raw.get("category") or "").split("/") if p.strip()]
    cat_model, cat_name = None, None
    if len(cat_parts) >= 3:
        cat_model = detect_model(norm(" ".join(cat_parts[1:3])), cfg["models"])
        cat_name = f"{cat_parts[1]} {cat_parts[2].split(',')[0]}"
    model_key = raw.get("model_key") or (cat_model if len(cat_parts) >= 3 else None) \
        or (None if len(cat_parts) >= 3 else detect_model(n, cfg["models"]))

    price, ptype = raw.get("price"), raw.get("price_type")
    if not price:
        p2, t2 = parse_price(f"{title}\n{body}")
        price = p2
        ptype = ptype or t2

    mileage = raw.get("mileage_km") or parse_mileage(f"{body}\n{extra}\n{title}")
    year = raw.get("year") or parse_year(title, body + "\n" + extra)

    # price sanity: Haraj sellers write prices in thousands (105 = 105,000) or put placeholders (1000, 1111)
    if price:
        p = int(price)
        if len(set(str(p))) == 1 or p in (1000, 123, 1234, 12345, 123456, 10, 100):
            price, ptype = None, "negotiable"
        elif p < 1000:
            price = p * 1000
    # mileage placeholder (e.g. 1000 km on a 15-year-old car)
    if mileage and mileage < 5000 and year and year < CURRENT_YEAR - 2:
        mileage = None

    n_4 = n
    for dc in DOUBLE_CAB:
        n_4 = n_4.replace(norm(dc), " ")
    if contains_any(n_4, FOURX4_NEG):
        is4, src4 = False, "نص الإعلان"
    elif contains_any(n_4, FOURX4_POS):
        is4, src4 = True, "نص الإعلان"
    elif model_key in DEFAULT_4X4:
        is4, src4 = True, "الموديل غالبًا دبل"
    else:
        is4, src4 = None, None
    if raw.get("is_4x4") is not None:
        is4, src4 = raw["is_4x4"], raw.get("is_4x4_source", "الإعلان")

    trans = None
    if contains_any(n, ["قير عادي", "جير عادي", "عادي قير", "مانيوال", "manual", "قير يدوي"]):
        trans = "عادي"
    elif contains_any(n, ["اوتوماتيك", "اتوماتيك", "اوتوماتك", "automatic", "قير اوتو", "جير اوتو"]):
        trans = "أوتوماتيك"
    fuel = "ديزل" if contains_any(n, ["ديزل", "diesel"]) else ("بنزين" if contains_any(n, ["بنزين"]) else None)

    severe = contains_any(n, RED_SEVERE)
    medium = [w for w in contains_any(n, RED_MEDIUM) if not any(norm(w) in norm(s) for s in severe)]
    green = contains_any(n, GREEN)
    # "شرط" is generic; drop it if a more specific green phrase already contains it
    if len(green) > 1 and "شرط" in green:
        green.remove("شرط")
    parts = bool(contains_any(n, PARTS))

    city = detect_city(f"{title}\n{body}", raw.get("city") or "")
    non_car = is_non_car(title, raw.get("category") or "")

    return {
        "model_key": model_key,
        "model_name": cfg["models"].get(model_key, {}).get("name") if model_key else cat_name,
        "year": year,
        "price": int(price) if price else None,
        "price_type": ptype,
        "mileage_km": mileage,
        "is_4x4": is4,
        "is_4x4_source": src4,
        "transmission": raw.get("transmission") or trans,
        "fuel": raw.get("fuel") or fuel,
        "city": city,
        "distance_km": CITY_KM.get(city) if city else None,
        "red_flags_severe": severe,
        "red_flags": medium,
        "green_flags": green,
        "parts_car": parts,
        "non_car": non_car,
        "category": raw.get("category"),
    }

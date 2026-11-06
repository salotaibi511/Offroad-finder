import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finder.extract import extract, parse_mileage, parse_price, parse_year  # noqa: E402
from finder.pipeline import load_config  # noqa: E402
from finder.score import score  # noqa: E402
from finder.sources import haraj  # noqa: E402

CFG = load_config()


def test_price():
    assert parse_price("السعر 18 الف نهائي") == (18000, "asking")
    assert parse_price("بـ ١٧٥٠٠ ريال") == (17500, "asking")
    assert parse_price("المطلوب 16,500") == (16500, "asking")
    assert parse_price("على السوم") == (None, "negotiable")
    assert parse_price("ممشى 300 الف") == (None, None)


def test_mileage_year():
    assert parse_mileage("ممشى ٣٠٠ ألف") == 300000
    assert parse_mileage("العداد 245000 كم") == 245000
    assert parse_year("شاص موديل 98") == 1998
    assert parse_year("لاندكروزر 2003") == 2003
    assert parse_year("ممشى 90 كم") is None


def test_extract_full():
    raw = {"title": "جيب لاندكروزر 2003 دبل شغال", "city": "جدة",
           "body": "ماكينة شرط قير اوتوماتيك ممشى 320 الف فحص جديد السعر 19 الف"}
    f = extract(raw, CFG)
    assert f["model_key"] == "land_cruiser" and f["year"] == 2003 and f["price"] == 19000
    assert f["mileage_km"] == 320000 and f["is_4x4"] is True and f["distance_km"] == 0
    assert "فحص جديد" in f["green_flags"]
    s = score(f, CFG, {})
    assert s["label"] in ("فرصة", "يستحق السؤال"), s


def test_double_cab_not_4x4():
    f = extract({"title": "هايلكس دبل غمارتين 2008", "body": "سنقل قير عادي", "city": "الرياض"}, CFG)
    assert f["is_4x4"] is False
    assert score(f, CFG, {})["label"] == "مستبعد"


def test_parts_and_budget():
    f = extract({"title": "باترول للتشليح", "body": "قطع غيار", "city": "مكة"}, CFG)
    assert f["parts_car"]
    f2 = extract({"title": "برادو 2015", "body": "السعر 65 الف", "city": "جدة"}, CFG)
    assert "أعلى من الميزانية" in score(f2, CFG, {})["exclude_reasons"][0]


FX = os.path.join(os.path.dirname(__file__), "fixtures")


def _fx(name):
    return open(os.path.join(FX, name), encoding="utf-8").read()


def test_haraj_real_pages():
    a = haraj.parse_listing(_fx("haraj_ad_price.html"), "https://haraj.com.sa/11192127908/")
    assert a["id"] == "haraj:11192127908" and a["price"] == 70000 and a["price_type"] == "asking"
    assert a["city"] == "صبيا" and a["year"] == 2002 and a["mileage_km"] == 400000
    b = haraj.parse_listing(_fx("haraj_ad_bid.html"), "https://haraj.com.sa/11192127633/x/")
    assert b["price"] == 106000 and b["price_type"] == "bid" and b["is_4x4"] and b["transmission"] == "عادي"
    c = haraj.parse_listing(_fx("haraj_ad_fields.html"), "https://haraj.com.sa/11192130098/")
    assert c["price"] is None and c["year"] == 2022 and c["mileage_km"] == 53000
    f = extract(c, CFG)
    assert any("فوق الميزانية" in r for r in score(f, CFG, {})["exclude_reasons"])
    links = haraj.parse_search(_fx("haraj_search.html"))
    assert len(links) >= 15


def test_non_car():
    from finder.extract import is_non_car
    for t in ["صاجه حمايه لاندكروزر 2022", "جنوط برايد لاندكروزر", "دباب سوزوكي 2014 الف مشروط مكينه قير شاص",
              "ايسوزو دينا 13 طن 2025 شاص طويل", "طيس جيب شاص وربع", "جركل ربع بريمي وكاله"]:
        assert is_non_car(t), t
    for t in ["شاص ونش 2010", "لاندكروزر 2003 كفرات جديده", "جيب ربع 2018", "شاص 2002"]:
        assert not is_non_car(t), t
    assert parse_price("ب550ريال")[0] is None

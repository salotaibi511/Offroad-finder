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


def test_haraj_parsers():
    html = """<html><head><meta property="og:title" content="لاندكروزر 2013 | موقع حراج">
    <meta property="og:description" content="موتر نظيف جداً جير مكينه شاصي شرط">
    <meta property="og:image" content="https://img/1.jpg"></head><body>
    <h1>لاندكروزر 2013</h1><div>الرياض</div><div>قبل ٥٢ دقيقة</div>
    <div>السوم واصل</div><div>٧٥</div><div>400 ألف كيلو أو أكثر</div>
    <a href="/11192126812/جيب_لاندكروزر_2003_/">جيب لاندكروزر 2003</a></body></html>"""
    L = haraj.parse_listing(html, "https://haraj.com.sa/11192126492/x/")
    assert L["title"] == "لاندكروزر 2013" and L["price"] == 75000 and L["price_type"] == "bid"
    assert L["city"] == "الرياض" and "400" in L["fields_text"]
    links = haraj.parse_search(html)
    assert links[0]["id"] == "11192126812"

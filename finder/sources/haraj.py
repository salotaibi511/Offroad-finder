"""Haraj (haraj.com.sa) search + listing parser."""
import json
import logging
import re
from urllib.parse import quote, unquote, urljoin

from bs4 import BeautifulSoup

from ..http import get_html
from ..textnorm import digits, norm

log = logging.getLogger(__name__)
BASE = "https://haraj.com.sa"
POST_RE = re.compile(r"(?:https?://(?:www\.)?haraj\.com\.sa)?/(11\d{6,})/([^/?#\"'\s]+)/?")


def is_listing_url(url: str) -> bool:
    return bool(re.match(r"https?://(?:www\.)?haraj\.com\.sa/11\d{6,}", url))


def is_haraj(url: str) -> bool:
    return "haraj.com.sa" in url


def search_url(query: str) -> str:
    return f"{BASE}/search/{quote(query)}"


def canonical(post_id: str, slug: str = "") -> str:
    return f"{BASE}/{post_id}/{slug}/" if slug else f"{BASE}/{post_id}/"


def parse_search(html: str) -> list:
    """Return [{id, url, title}] for listing links on a search/tag/city page."""
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        m = POST_RE.match(a["href"]) or POST_RE.match(urljoin(BASE, a["href"]))
        if not m:
            continue
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        title = a.get_text(" ", strip=True) or unquote(m.group(2)).replace("_", " ")
        out.append({"id": pid, "url": canonical(pid, m.group(2)), "title": title})
    if not out:  # links may only exist inside embedded JSON
        for m in POST_RE.finditer(html):
            pid = m.group(1)
            if pid not in seen:
                seen.add(pid)
                out.append({"id": pid, "url": canonical(pid, m.group(2)),
                            "title": unquote(m.group(2)).replace("_", " ")})
    return out


def _meta(soup, prop):
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return tag.get("content", "").strip() if tag else ""


def _json_hint(html: str, post_id: str) -> dict:
    """Best-effort read of embedded post JSON (price/city/body) if the page ships it."""
    out = {}
    i = html.find(post_id)
    window = html[max(0, i - 4000): i + 8000] if i >= 0 else ""
    for key, field in (("price", r'"price"\s*:\s*"?(\d+)'), ("city", r'"city"\s*:\s*"([^"]+)"'),
                       ("body", r'"bodyTEXT"\s*:\s*"((?:[^"\\]|\\.)*)"')):
        m = re.search(field, window)
        if m:
            val = m.group(1)
            if key == "body":
                try:
                    val = json.loads(f'"{val}"')
                except ValueError:
                    pass
            out[key] = val
    return out


def parse_listing(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    m = POST_RE.search(url)
    pid = m.group(1) if m else url
    title = re.sub(r"\s*\|\s*موقع حراج\s*$", "", _meta(soup, "og:title") or (soup.title.string if soup.title else ""))
    body = _meta(soup, "og:description")
    images = [t.get("content") for t in soup.find_all("meta", attrs={"property": "og:image"}) if t.get("content")]

    for s in soup(["script", "style", "noscript", "svg"]):
        s.extract()
    text = digits(soup.get_text("\n", strip=True))
    # cut off "similar ads" and footer so they don't pollute extraction
    for marker in ("إعلانات مشابهة", "اعلانات مشابهة", "قد يعجبك", "حراج السيارات\nتويوتا", "الشروط والأحكام"):
        k = text.find(marker)
        if k > 200:
            text = text[:k]
    lines = [l for l in text.split("\n") if l.strip()]

    price, ptype = None, None
    for i, line in enumerate(lines):
        ln = norm(line)
        if "السوم واصل" in ln or ln in ("السعر", "السعر:") or ln.startswith("السعر"):
            win = " ".join(lines[i: i + 3])
            nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", win)]
            nums = [x for x in nums if x > 0]
            if nums:
                v = nums[0]
                v = v * 1000 if v < 1000 else v
                price, ptype = int(v), ("bid" if "السوم" in ln else "asking")
                break

    city = None
    known = ["جدة", "مكة", "الرياض", "الدمام", "الطائف", "المدينة", "ينبع", "رابغ", "تبوك", "حائل", "أبها",
             "جازان", "نجران", "الخبر", "القصيم", "بريدة", "الأحساء", "الباحة", "الليث", "القنفذة", "سكاكا",
             "الجوف", "عرعر", "بيشة", "خميس مشيط", "الخرج", "الجبيل", "حفر الباطن", "القريات", "العلا"]
    for line in lines[:40]:
        if line.strip() in known:
            city = line.strip()
            break

    mileage_line = next((l for l in lines if re.search(r"(?:ألف|الف)\s*كيلو|كيلومتر", l)), "")
    hint = _json_hint(html, str(pid))
    if not price and hint.get("price"):
        v = int(hint["price"])
        price, ptype = (v * 1000 if 0 < v < 1000 else v), "asking"
    if not body and hint.get("body"):
        body = hint["body"]

    return {
        "id": f"haraj:{pid}",
        "source": "haraj",
        "url": url,
        "title": title.strip(),
        "body": body,
        "fields_text": mileage_line,
        "city": city or hint.get("city"),
        "price": price,
        "price_type": ptype,
        "images": images[:6],
    }


def search(query: str) -> list:
    html = get_html(search_url(query))
    items = parse_search(html) if html else []
    log.info("haraj '%s': %d links", query, len(items))
    return items


def fetch(url: str) -> dict:
    html = get_html(url)
    if not html:
        return {}
    return parse_listing(html, url)

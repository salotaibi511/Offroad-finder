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
POST_RE = re.compile(r"(?:https?://(?:www\.)?haraj\.com\.sa)?/(11\d{6,})(?:/([^/?#\"'\s]+))?/?")


def is_listing_url(url: str) -> bool:
    return bool(re.match(r"https?://(?:www\.)?haraj\.com\.sa/11\d{6,}", url))


def is_haraj(url: str) -> bool:
    return "haraj.com.sa" in url


def search_url(query: str, city: str = "") -> str:
    return f"{BASE}/search/{quote(query)}" + (f"/city/{quote(city)}" if city else "")


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
        slug = m.group(2) or ""
        title = a.get_text(" ", strip=True) or unquote(slug).replace("_", " ")
        out.append({"id": pid, "url": canonical(pid, slug), "title": title})
    if not out:  # links may only exist inside embedded JSON
        for m in POST_RE.finditer(html):
            pid = m.group(1)
            if pid not in seen:
                seen.add(pid)
                out.append({"id": pid, "url": canonical(pid, m.group(2) or ""),
                            "title": unquote(m.group(2) or "").replace("_", " ")})
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


SPEC_TRANS = {"قير عادي": "عادي", "قير اوتوماتيك": "أوتوماتيك", "قير أوتوماتيك": "أوتوماتيك"}


def parse_listing(html: str, url: str) -> dict:
    """Haraj ad page layout (Nov 2026):
    breadcrumb (حراج السيارات / تويوتا / شاص / شاص 2002) → title → city → time → author →
    [price line] → spec line (تويوتا شاص 2002 مستخدم) → [قير عادي] [بنزين] [الممشى: 400 ألف كيلو] [دبل]
    → body lines → تواصل
    """
    soup = BeautifulSoup(html, "html.parser")
    m = POST_RE.search(url)
    pid = m.group(1) if m else url
    title = re.sub(r"\s*\|\s*موقع حراج\s*$", "", _meta(soup, "og:title") or (soup.title.string if soup.title else "")).strip()
    og_body = _meta(soup, "og:description")
    images = [t.get("content") for t in soup.find_all("meta", attrs={"property": "og:image"}) if t.get("content")]

    for t in soup(["script", "style", "noscript", "svg"]):
        t.extract()
    lines = [l.strip().replace("\xa0", " ").strip() for l in digits(soup.get_text("\n", strip=True)).split("\n")]
    lines = [l for l in lines if l]

    out = {"id": f"haraj:{pid}", "source": "haraj", "url": url, "title": title, "images": images[:6],
           "price": None, "price_type": None}
    # locate the title that follows the breadcrumb
    t_idx = None
    for i in range(1, len(lines)):
        if lines[i] == title and i > 3 and lines[i - 1] != "/":
            t_idx = i
            break
    try:
        b0 = lines.index("حراج السيارات")
        out["category"] = " / ".join(x for x in lines[b0:(t_idx or b0 + 8)] if x != "/")
    except ValueError:
        out["category"] = ""
    if t_idx is None:
        out["body"] = og_body
        return out

    out["city"] = lines[t_idx + 1] if len(lines) > t_idx + 1 else None
    k = t_idx + 4  # skip city, time, author
    fields, body = [], []
    while k < len(lines):
        l = lines[k]
        if l in ("تواصل", "مراسلة"):
            break
        if not body:
            if re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d{3,7}", l) and out["price"] is None:
                out["price"], out["price_type"] = int(l.replace(",", "")), "asking"
                k += 1
                continue
            if l.startswith("الممشى"):
                fields.append(l)
                mk = re.search(r"(\d[\d,]*)\s*(ألف|الف)?", l)
                if mk:
                    v = int(mk.group(1).replace(",", ""))
                    out["mileage_km"] = v * 1000 if mk.group(2) or v < 1000 else v
                k += 1
                continue
            if l in SPEC_TRANS:
                out["transmission"] = SPEC_TRANS[l]
                k += 1
                continue
            if l in ("بنزين", "ديزل", "هايبرد", "كهرباء"):
                out["fuel"] = l
                k += 1
                continue
            if l == "دبل":
                out["is_4x4"], out["is_4x4_source"] = True, "حقل الإعلان"
                k += 1
                continue
            if re.search(r"(?:19|20)\d{2}", l) and (l.endswith("مستخدم") or l.endswith("جديد") or len(fields) == 0) \
                    and len(l) < 60 and not body and k <= t_idx + 6:
                fields.append(l)
                my = re.search(r"(?:19|20)\d{2}", l)
                out["year"] = int(my.group(0))
                k += 1
                continue
        body.append(l)
        k += 1
    out["fields_text"] = " | ".join(fields)
    out["body"] = "\n".join(body) or og_body
    if out["price"] is None:
        mb = re.search(r"السوم\s*(?:واصل|وصل)\s*(\d[\d,]*)", out["body"])
        if mb:
            v = int(mb.group(1).replace(",", ""))
            out["price"], out["price_type"] = (v * 1000 if v < 1000 else v), "bid"
    return out


def search(query: str, city: str = "") -> list:
    html = get_html(search_url(query, city))
    items = parse_search(html) if html else []
    log.info("haraj '%s' [%s]: %d links", query, city or "كل المدن", len(items))
    return items


def fetch(url: str) -> dict:
    html = get_html(url)
    if not html:
        return {}
    return parse_listing(html, url)

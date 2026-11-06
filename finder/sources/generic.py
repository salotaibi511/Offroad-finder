"""Generic parser for any used-car site (OpenSooq, YallaMotor, Motory, Syarah, ...).

Reads Open Graph tags, JSON-LD (schema.org Car/Vehicle/Product) and visible text.
"""
import hashlib
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import get_html
from ..textnorm import digits

# per-site listing-link patterns used when a *search* page is submitted
LISTING_PATTERNS = {
    "opensooq.com": r"/ar/search/\d{6,}",
    "yallamotor.com": r"/used-cars/[^\"'#?]+?\d{5,}",
    "motory.com": r"/(?:ar/)?(?:used-cars|cars)/[^\"'#?]*\d{4,}",
    "syarah.com": r"/(?:ar/)?(?:car|cars)/[^\"'#?]*\d{3,}",
    "mstaml.com": r"/\d{5,}/",
    "dubizzle": r"/[^\"'#?]*---\w+|/item/\d+",
}


def _site(url):
    return urlparse(url).netloc.replace("www.", "")


def make_id(url: str) -> str:
    u = url.split("#")[0].split("?")[0].rstrip("/")
    return f"{_site(u)}:{hashlib.md5(u.encode()).hexdigest()[:10]}"


def looks_like_listing(url: str) -> bool:
    path = urlparse(url).path
    return bool(re.search(r"\d{5,}", path)) and "search" not in path.lower().replace("/ar/search/", "/x/")


def _ld_items(soup):
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "@graph" in d:
                    stack.extend(d["@graph"])
                yield d


def parse_listing(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    def meta(p):
        t = soup.find("meta", attrs={"property": p}) or soup.find("meta", attrs={"name": p})
        return (t.get("content") or "").strip() if t else ""

    out = {"id": make_id(url), "source": _site(url), "url": url,
           "title": meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else ""),
           "body": meta("og:description") or meta("description"),
           "images": [meta("og:image")] if meta("og:image") else []}

    for d in _ld_items(soup):
        typ = str(d.get("@type", "")).lower()
        if any(k in typ for k in ("car", "vehicle", "product", "offer")):
            off = d.get("offers") or {}
            if isinstance(off, list):
                off = off[0] if off else {}
            p = off.get("price") or d.get("price")
            try:
                if p:
                    out["price"], out["price_type"] = int(float(str(p).replace(",", ""))), "asking"
            except ValueError:
                pass
            mo = d.get("mileageFromOdometer")
            if isinstance(mo, dict) and mo.get("value"):
                try:
                    out["mileage_km"] = int(float(str(mo["value"]).replace(",", "")))
                except ValueError:
                    pass
            for yk in ("vehicleModelDate", "modelDate", "productionDate"):
                if d.get(yk):
                    m = re.search(r"(19|20)\d{2}", str(d[yk]))
                    if m:
                        out["year"] = int(m.group(0))
            if d.get("description") and len(d["description"]) > len(out["body"] or ""):
                out["body"] = d["description"]

    for s in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        s.extract()
    text = digits(soup.get_text("\n", strip=True))
    out["fields_text"] = text[:2500]
    return out


def parse_search(html: str, url: str) -> list:
    site = _site(url)
    pat = next((p for k, p in LISTING_PATTERNS.items() if k in site), None)
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        full = urljoin(url, a["href"]).split("#")[0]
        if _site(full) != site or full.rstrip("/") == url.rstrip("/"):
            continue
        path = urlparse(full).path
        ok = re.search(pat, path) if pat else looks_like_listing(full)
        if ok and full not in seen:
            seen.add(full)
            out.append({"id": make_id(full), "url": full, "title": a.get_text(" ", strip=True)})
    return out[:40]


def fetch(url: str) -> dict:
    html = get_html(url)
    return parse_listing(html, url) if html else {}


def search(url: str) -> list:
    html = get_html(url)
    return parse_search(html, url) if html else []

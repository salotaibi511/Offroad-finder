"""HTTP fetching with polite delays and an optional headless-browser fallback."""
import logging
import random
import time

import requests

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

_session = requests.Session()
_session.headers.update({
    "User-Agent": UA,
    "Accept-Language": "ar-SA,ar;q=0.9,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

_browser = None
_last = 0.0
DELAY = 2.0


def _polite():
    global _last
    wait = DELAY + random.uniform(0, 1.0) - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.time()


def _browser_get(url: str) -> str:
    global _browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ""
    if _browser is None:
        pw = sync_playwright().start()
        _browser = pw.chromium.launch(headless=True)
    page = _browser.new_page(user_agent=UA, locale="ar-SA")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        return page.content()
    except Exception as e:  # noqa: BLE001
        log.warning("browser failed %s: %s", url, e)
        return ""
    finally:
        page.close()


def get_html(url: str, browser_fallback: bool = True) -> str:
    """Fetch a page. Falls back to headless Chromium when blocked or rendered client-side."""
    _polite()
    html = ""
    try:
        r = _session.get(url, timeout=30)
        if r.status_code == 200:
            r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
            html = r.text
        else:
            log.warning("HTTP %s for %s", r.status_code, url)
    except requests.RequestException as e:
        log.warning("request failed %s: %s", url, e)
    if (not html or len(html) < 3000) and browser_fallback:
        log.info("browser fallback for %s", url)
        html = _browser_get(url) or html
    return html

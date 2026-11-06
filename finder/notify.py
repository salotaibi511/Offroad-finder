"""Telegram notifications. Active only when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set."""
import html
import logging
import os

import requests

log = logging.getLogger(__name__)


def _fmt(L: dict, why: str) -> str:
    price = f"{L['price']:,} ريال" if L.get("price") else "السعر غير مذكور"
    km = f"{L['mileage_km']:,} كم" if L.get("mileage_km") else "الممشى ؟"
    lines = [
        f"<b>{why} — {L['score']}/100</b>",
        html.escape(L.get("title") or ""),
        f"🚙 {html.escape(L.get('model_name') or '؟')} {L.get('year') or ''} | {km}",
        f"💰 {price} | 📍 {html.escape(L.get('city') or '؟')}",
    ]
    if L.get("reasons_pos"):
        lines.append("✅ " + html.escape("؛ ".join(L["reasons_pos"][:3])))
    if L.get("reasons_neg"):
        lines.append("⚠️ " + html.escape("؛ ".join(L["reasons_neg"][:3])))
    if L.get("ai_summary"):
        lines.append("🤖 " + html.escape(L["ai_summary"]))
    lines.append(L["url"])
    return "\n".join(lines)


def send(L: dict, why: str):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": _fmt(L, why), "parse_mode": "HTML",
                                "disable_web_page_preview": False}, timeout=20)
        return r.ok
    except requests.RequestException as e:
        log.warning("telegram failed: %s", e)
        return False

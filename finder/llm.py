"""Optional AI extraction with Claude. Active only when ANTHROPIC_API_KEY is set."""
import json
import logging
import os
import re

import requests

log = logging.getLogger(__name__)

PROMPT = """أنت محلل إعلانات سيارات مستعملة في السعودية. حلّل الإعلان التالي وأعد JSON فقط بدون أي نص آخر، بالمفاتيح:
model (اسم الماركة والموديل بالعربي أو null), year (رقم أو null), price (بالريال كرقم كامل أو null؛ "15 الف" = 15000),
price_type ("asking" أو "bid" أو "negotiable" أو null), mileage_km (رقم أو null),
is_4x4 (true/false/null — انتبه: "دبل قمارة/غمارتين" تعني كابينة مزدوجة وليست دفع رباعي),
transmission ("أوتوماتيك"/"عادي"/null), fuel ("بنزين"/"ديزل"/null), city (أو null),
red_flags (قائمة مختصرة بالعيوب أو المخاطر المذكورة), green_flags (قائمة مختصرة بالإيجابيات),
parts_car (true إذا كانت للتشليح أو قطع غيار), summary (سطر عربي واحد يلخص حالة السيارة وأهم ما يجب سؤال البائع عنه).

العنوان: {title}
المدينة: {city}
السعر المعروض في الصفحة: {price}
النص:
{body}
"""


def available(cfg) -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and cfg.get("llm", {}).get("enabled", False)


def analyse(raw: dict, cfg: dict) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {}
    body = ((raw.get("body") or "") + "\n" + (raw.get("fields_text") or ""))[:3500]
    prompt = PROMPT.format(title=raw.get("title", ""), city=raw.get("city") or "", price=raw.get("price") or "",
                           body=body)
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": cfg["llm"]["model"], "max_tokens": 700,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        log.warning("LLM failed for %s: %s", raw.get("url"), e)
        return {}


def merge(fields: dict, ai: dict, cfg: dict) -> dict:
    """Overlay AI answers onto rule-based fields (AI wins where it is confident)."""
    if not ai:
        return fields
    from .extract import CITY_KM, detect_model
    from .textnorm import norm

    if ai.get("model") and not fields.get("model_key"):
        mk = detect_model(norm(ai["model"]), cfg["models"])
        if mk:
            fields["model_key"], fields["model_name"] = mk, cfg["models"][mk]["name"]
    if not fields.get("model_name") and ai.get("model"):
        fields["model_name"] = ai["model"]
    for k in ("year", "mileage_km", "transmission", "fuel"):
        if ai.get(k) and not fields.get(k):
            fields[k] = ai[k]
    if ai.get("price") and not fields.get("price"):
        fields["price"], fields["price_type"] = int(ai["price"]), ai.get("price_type") or "asking"
    if ai.get("is_4x4") is not None and fields.get("is_4x4_source") != "نص الإعلان":
        fields["is_4x4"], fields["is_4x4_source"] = ai["is_4x4"], "تحليل AI"
    if ai.get("city") and not fields.get("city"):
        fields["city"] = ai["city"]
        fields["distance_km"] = CITY_KM.get(ai["city"])
    known = set(fields.get("red_flags", [])) | set(fields.get("red_flags_severe", []))
    fields["red_flags"] = fields.get("red_flags", []) + [f for f in ai.get("red_flags") or [] if f not in known][:4]
    gk = set(fields.get("green_flags", []))
    fields["green_flags"] = fields.get("green_flags", []) + [f for f in ai.get("green_flags") or [] if f not in gk][:4]
    if ai.get("parts_car"):
        fields["parts_car"] = True
    fields["ai_summary"] = ai.get("summary")
    return fields

"""Handle a GitHub issue (or comment): add offers by URL, change status, add notes.

Reads ISSUE_BODY / ISSUE_USER from env, writes a Markdown reply to reply.md.

Supported inputs
- "أضف عرض" issue form  (field: روابط العروض + ملاحظات)
- "تحديث حالة" issue form (field: رقم العرض + الحالة + ملاحظة)
- free commands in any issue/comment:
    /add <url> [<url> ...]
    /status <offer-id> <الحالة>
    /note <offer-id> <نص>
"""
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finder.pipeline import Pipeline  # noqa: E402
from finder import store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("issue")

STATUSES = ["جديد", "تواصلت", "بانتظار رد", "معاينة", "فحص", "تفاوض", "مستبعد يدويًا", "تم الشراء", "مباع"]
URL_RE = re.compile(r"https?://[^\s<>\")\]]+")


def form_fields(body: str) -> dict:
    out, cur = {}, None
    for line in body.splitlines():
        h = re.match(r"^###\s+(.+?)\s*$", line)
        if h:
            cur = h.group(1).strip()
            out[cur] = ""
        elif cur:
            out[cur] += line + "\n"
    return {k: ("" if v.strip() == "_No response_" else v.strip()) for k, v in out.items()}


def find_listing(p, ref: str):
    ref = ref.strip()
    if ref in p.idx:
        return p.idx[ref]
    for L in p.idx.values():  # accept URL or bare number
        if ref and (ref == L.get("url") or L["id"].endswith(":" + ref) or ref in (L.get("url") or "")):
            return L
    return None


def fmt(L):
    price = f"{L['price']:,} ريال" if L.get("price") else "السعر ؟"
    flags = ""
    if L.get("exclude_reasons"):
        flags = "\n   ⛔ " + "؛ ".join(L["exclude_reasons"])
    else:
        if L.get("reasons_pos"):
            flags += "\n   ✅ " + "؛ ".join(L["reasons_pos"][:3])
        if L.get("reasons_neg"):
            flags += "\n   ⚠️ " + "؛ ".join(L["reasons_neg"][:3])
    ai = f"\n   🤖 {L['ai_summary']}" if L.get("ai_summary") else ""
    return (f"- **{L['score']}/100 — {L['label']}** · [{L['title']}]({L['url']})\n"
            f"   {L.get('model_name') or 'موديل ؟'} {L.get('year') or ''} · {price} · "
            f"{L.get('city') or 'مدينة ؟'} · رقم العرض: `{L['id']}`{flags}{ai}")


def main():
    body = os.environ.get("ISSUE_BODY", "")
    user = os.environ.get("ISSUE_USER", "github")
    p = Pipeline()
    f = form_fields(body)
    reply, touched = [], []

    urls, note = [], None
    if "روابط العروض" in f:
        urls = URL_RE.findall(f["روابط العروض"])
        note = f.get("ملاحظات") or None
    for m in re.finditer(r"^/add\s+(.+)$", body, re.M):
        urls += URL_RE.findall(m.group(1))

    for u in dict.fromkeys(urls):
        try:
            ads = p.expand(u)
        except Exception as e:  # noqa: BLE001
            reply.append(f"- ❌ تعذر فتح الرابط {u}: {e}")
            continue
        if not ads:
            reply.append(f"- ⚠️ لم أجد إعلانات في {u}")
        for ad in ads[:40]:
            try:
                rec = p.ingest(p.fetch(ad), added_by=user, note=note)
            except Exception as e:  # noqa: BLE001
                rec = None
                log.warning("failed %s: %s", ad, e)
            if rec:
                touched.append(rec["id"])
            else:
                reply.append(f"- ❌ تعذر قراءة الإعلان {ad}")

    status_cmds = []
    if "رقم العرض" in f and f.get("الحالة"):
        status_cmds.append((f["رقم العرض"], f["الحالة"], f.get("ملاحظة")))
    for m in re.finditer(r"^/status\s+(\S+)\s+(.+)$", body, re.M):
        status_cmds.append((m.group(1), m.group(2).strip(), None))
    for m in re.finditer(r"^/note\s+(\S+)\s+(.+)$", body, re.M):
        status_cmds.append((m.group(1), None, m.group(2).strip()))

    for ref, st, nt in status_cmds:
        L = find_listing(p, ref)
        if not L:
            reply.append(f"- ❌ لم أجد عرضًا بالرقم `{ref}`")
            continue
        if st:
            if st not in STATUSES:
                reply.append(f"- ❌ حالة غير معروفة «{st}». المتاح: {'، '.join(STATUSES)}")
                continue
            L["status"] = st
        if nt:
            L.setdefault("notes", []).append({"by": user, "date": store.now()[:10], "text": nt})
        touched.append(L["id"])

    p.finish({"trigger": "issue", "by": user})
    p.idx = store.index(p.db)
    done = [fmt(p.idx[i]) for i in dict.fromkeys(touched) if i in p.idx]
    out = []
    if done:
        out.append("### ✅ تمت المعالجة\n" + "\n".join(done))
    if reply:
        out.append("### ملاحظات\n" + "\n".join(reply))
    if not out:
        out.append("لم أجد روابط أو أوامر في الطلب. استخدم نموذج «أضف عرض» أو الأوامر `/add` و `/status` و `/note`.")
    with open("reply.md", "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(out))
    print("\n\n".join(out))


if __name__ == "__main__":
    main()

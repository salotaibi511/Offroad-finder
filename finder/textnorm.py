"""Arabic text normalisation helpers."""
import re

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def digits(text: str) -> str:
    return (text or "").translate(_AR_DIGITS).replace("٬", ",").replace("٫", ".")


def norm(text: str) -> str:
    """Normalise for matching: digits, alef/yaa/taa forms, diacritics, case, spacing."""
    t = digits(text or "")
    t = _DIACRITICS.sub("", t)
    t = re.sub("[إأآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = t.replace("×", "x").replace("_", " ")
    t = t.lower()
    return re.sub(r"\s+", " ", t).strip()


def contains_any(text_n: str, words) -> list:
    """Return the words (normalised) that occur in already-normalised text as whole-ish tokens."""
    hits = []
    for w in words:
        wn = norm(w)
        if not wn:
            continue
        # allow common Arabic prefixes (و، ب، ال، بال...) before the word
        pat = r"(?<![\w])(?:و|ف|ب|ل|ال|وال|بال|لل)?" + re.escape(wn) + r"(?![\w])"
        if re.search(pat, text_n):
            hits.append(w)
    return hits

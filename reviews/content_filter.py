import re
from unicodedata import normalize as unicode_normalize


HOMOGLYPHS = str.maketrans(
    {
        "a": "а",
        "c": "с",
        "e": "е",
        "o": "о",
        "p": "р",
        "x": "х",
        "y": "у",
        "ё": "е",
    }
)

PROFANITY_PATTERNS = [
    r"ху[йеияю]",
    r"п[ие]зд",
    r"бл[яиа](?:д|т|)",
    r"^еб(?:$|[а-я])",
    r"(?:за|на|вы|по|до|про|от|раз|съ|у|пере|при)еб",
    r"долбоеб",
    r"муда(?:к|ч)",
    r"гандон",
]


def normalize_text(text):
    normalized = unicode_normalize("NFKC", text or "").lower().translate(HOMOGLYPHS)
    normalized = re.sub(r"(.)\1{2,}", r"\1\1", normalized)
    return normalized


def contains_profanity(text):
    normalized = normalize_text(text)
    compact = re.sub(r"[^а-яa-z0-9]+", "", normalized)
    words = re.findall(r"[а-яa-z0-9]+", normalized)
    candidates = words + ([compact] if compact else [])

    for candidate in candidates:
        for pattern in PROFANITY_PATTERNS:
            if re.search(pattern, candidate):
                return True
    return False

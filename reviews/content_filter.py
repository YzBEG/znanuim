import re
from unicodedata import normalize as unicode_normalize


# Latin lookalikes are converted to Cyrillic letters so simple obfuscation
# like "xyй" or "blя" is still caught by the review filter.
HOMOGLYPHS = str.maketrans(
    {
        "a": "\u0430",
        "c": "\u0441",
        "e": "\u0435",
        "o": "\u043e",
        "p": "\u0440",
        "x": "\u0445",
        "y": "\u0443",
        "\u0451": "\u0435",
    }
)


PROFANITY_PATTERNS = [
    r"\u0445\u0443[\u0439\u0435\u0438\u044f\u044e]",
    r"\u043f[\u0438\u0435]\u0437\u0434",
    r"\u0431\u043b[\u044f\u0438\u0430](?:\u0434|\u0442|)",
    r"^\u0435\u0431(?:$|[\u0430-\u044f])",
    r"(?:\u0437\u0430|\u043d\u0430|\u0432\u044b|\u043f\u043e|\u0434\u043e|\u043f\u0440\u043e|\u043e\u0442|\u0440\u0430\u0437|\u0441\u044a|\u0443|\u043f\u0435\u0440\u0435|\u043f\u0440\u0438)\u0435\u0431",
    r"\u0434\u043e\u043b\u0431\u043e\u0435\u0431",
    r"\u043c\u0443\u0434\u0430(?:\u043a|\u0447)",
    r"\u0433\u0430\u043d\u0434\u043e\u043d",
]


def normalize_text(text):
    normalized = unicode_normalize("NFKC", text or "").lower().translate(HOMOGLYPHS)
    normalized = re.sub(r"(.)\1{2,}", r"\1\1", normalized)
    return normalized


def contains_profanity(text):
    normalized = normalize_text(text)
    compact = re.sub(r"[^\u0430-\u044fa-z0-9]+", "", normalized)
    words = re.findall(r"[\u0430-\u044fa-z0-9]+", normalized)
    candidates = words + ([compact] if compact else [])

    for candidate in candidates:
        for pattern in PROFANITY_PATTERNS:
            if re.search(pattern, candidate):
                return True
    return False

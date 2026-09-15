"""Optional embedding hook; local TF-IDF/cosine fallback lives in duplicate_detector."""


def available() -> bool:
    return False

from .priority_engine import analyze_priority


def extract_keywords(text: str) -> list[str]:
    words = text.lower().split()
    return sorted({word.strip('.,!?') for word in words if len(word.strip('.,!?')) >= 4})


__all__ = ['analyze_priority', 'extract_keywords']

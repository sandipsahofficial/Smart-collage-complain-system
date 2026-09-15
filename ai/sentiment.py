def analyze_sentiment(text: str) -> tuple[str, str]:
    normalized = text.lower()
    if any(word in normalized for word in ('unbearable', 'distressed', 'afraid', 'dangerous')):
        return 'Distressed', 'High'
    if any(word in normalized for word in ('again', 'nobody', 'still', 'frustrated')):
        return 'Frustrated', 'Medium'
    return 'Neutral', 'Normal'

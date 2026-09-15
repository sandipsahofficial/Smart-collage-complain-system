import re

from .schemas import ComplaintAnalysis

CRITICAL_PATTERNS = {
    'fire': 'Detected fire-related danger',
    'sparking': 'Detected electrical sparking',
    'exposed wire': 'Detected exposed wiring',
    'gas leak': 'Detected a possible gas leak',
    'emergency': 'Detected emergency language',
    'flood': 'Detected flooding risk',
    'security threat': 'Detected a security threat',
    'dangerous': 'Detected dangerous conditions',
    'injury': 'Detected possible injury',
    'medical emergency': 'Detected a medical emergency',
}
HIGH_PATTERNS = {
    'no water': 'Detected an essential water outage',
    'major electrical': 'Detected a major electrical failure',
    'completely unavailable': 'Detected a complete service outage',
    'room unusable': 'Detected an unusable room',
    'repeated': 'Detected a repeated unresolved issue',
}
LOW_PATTERNS = {
    'cosmetic': 'Detected a cosmetic issue',
    'minor inconvenience': 'Detected a minor inconvenience',
    'suggestion': 'Detected a suggestion',
    'non-urgent': 'Detected non-urgent language',
}


def analyze_priority(text: str) -> tuple[str, float, list[str], bool]:
    normalized = re.sub(r'\s+', ' ', text.lower()).strip()
    critical = [reason for pattern, reason in CRITICAL_PATTERNS.items() if pattern in normalized]
    if critical:
        return 'Urgent', min(0.96, 0.78 + len(critical) * 0.06), critical, True
    high = [reason for pattern, reason in HIGH_PATTERNS.items() if pattern in normalized]
    if high:
        return 'High', min(0.92, 0.72 + len(high) * 0.06), high, False
    low = [reason for pattern, reason in LOW_PATTERNS.items() if pattern in normalized]
    if low:
        return 'Low', 0.82, low, False
    return 'Medium', 0.65, ['No critical urgency signal detected'], False


def analyze_safety(text: str) -> tuple[bool, str | None]:
    priority, _, reasons, critical = analyze_priority(text)
    if critical:
        return True, 'Potential Safety-Critical Complaint: immediate human attention recommended.'
    return False, None

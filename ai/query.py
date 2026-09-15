import re
from collections import Counter


def parse_admin_question(question: str) -> dict:
    text = re.sub(r'\s+', ' ', question.lower()).strip()
    if not text:
        return {'intent': 'help', 'filters': {}}

    filters = {}
    if any(word in text for word in ('urgent', 'critical', 'emergency', 'तत्काल', 'जरूरी')):
        filters['priority'] = 'Urgent'
    elif 'high priority' in text or 'high complaints' in text:
        filters['priority'] = 'High'
    if any(word in text for word in ('unresolved', 'open', 'pending', 'लंबित')):
        filters['status'] = 'open'
    elif any(word in text for word in ('resolved', 'solved', 'हल')):
        filters['status'] = 'Resolved'

    for keyword in ('water', 'internet', 'wifi', 'electrical', 'cleaning', 'security', 'पानी', 'इंटरनेट'):
        if keyword in text:
            filters['category_keyword'] = keyword
            break

    if any(word in text for word in ('total', 'how many', 'count', 'number', 'कितने', 'कुल')) or filters:
        intent = 'count'
    elif any(word in text for word in ('most', 'highest', 'सबसे अधिक', 'ज्यादा')):
        intent = 'top'
    elif any(word in text for word in ('complaint', 'complaints', 'शिकायत')):
        intent = 'summary'
    else:
        intent = 'help'
    return {'intent': intent, 'filters': filters}


def answer_question(question: str, complaints) -> dict:
    parsed = parse_admin_question(question)
    filters = parsed['filters']
    matching = list(complaints)
    if filters.get('priority'):
        matching = [item for item in matching if item.priority == filters['priority']]
    if filters.get('status') == 'open':
        matching = [item for item in matching if item.status not in {'Resolved', 'Closed'}]
    elif filters.get('status') == 'Resolved':
        matching = [item for item in matching if item.status == 'Resolved']
    keyword = filters.get('category_keyword')
    if keyword:
        matching = [item for item in matching if keyword in f'{item.category} {item.title} {item.description}'.lower()]

    if parsed['intent'] == 'top':
        field = 'campus_area' if any(word in question.lower() for word in ('hostel', 'area', 'block')) else 'category'
        counts = Counter(getattr(item, field) for item in matching)
        top = counts.most_common(1)[0] if counts else ('No matching data', 0)
        return {'answer': f'{top[0]}: {top[1]} complaint(s)', 'count': top[1], 'query': parsed}

    if parsed['intent'] in {'count', 'summary'}:
        label = 'matching complaint' if filters else 'complaint'
        return {'answer': f'{len(matching)} {label}{"s" if len(matching) != 1 else ""} found.', 'count': len(matching), 'query': parsed}

    return {'answer': 'I can answer verified complaint questions about total, urgent, high priority, unresolved, resolved, water, internet, electrical, cleaning, security, or most affected areas.', 'count': 0, 'query': parsed}

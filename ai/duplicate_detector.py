import math
import re
from collections import Counter

from .schemas import RelatedComplaint


TOKEN_ALIASES = {
    'wifi': 'internet',
    'wi-fi': 'internet',
    'leaking': 'leak',
    'leakage': 'leak',
    'rooms': 'room',
}


def _tokens(text: str) -> Counter:
    tokens = re.findall(r'[a-z0-9-]+', text.lower())
    return Counter(TOKEN_ALIASES.get(token, token) for token in tokens)


def cosine_similarity(left: str, right: str) -> float:
    first, second = _tokens(left), _tokens(right)
    if not first or not second:
        return 0.0
    common = set(first) & set(second)
    numerator = sum(first[token] * second[token] for token in common)
    denominator = math.sqrt(sum(value * value for value in first.values())) * math.sqrt(sum(value * value for value in second.values()))
    return round(numerator / denominator, 3) if denominator else 0.0


def find_related(title: str, description: str, complaints, threshold: float = 0.65) -> list[RelatedComplaint]:
    source = f'{title} {description}'
    results = []
    for complaint in complaints:
        similarity = cosine_similarity(source, f'{complaint.title} {complaint.description}')
        if similarity >= threshold:
            results.append(RelatedComplaint(complaint.id, complaint.ticket_number or f'#{complaint.id}', similarity, 'Shared complaint terms and context.'))
    return sorted(results, key=lambda result: result.similarity, reverse=True)

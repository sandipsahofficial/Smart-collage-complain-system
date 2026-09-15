import re


def complaint_context(title: str, description: str, location_type: str, campus_area: str = '') -> dict[str, str]:
    """Build the minimum complaint context; identity and room details never leave this function."""
    return {
        'title': title[:200],
        'description': re.sub(r'\s+', ' ', description).strip()[:2000],
        'location_type': location_type[:30],
        'campus_area': campus_area[:100],
    }

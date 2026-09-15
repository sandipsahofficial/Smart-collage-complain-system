from collections import Counter


def summarize(complaints) -> dict:
    categories = Counter(complaint.category for complaint in complaints)
    areas = Counter(complaint.campus_area for complaint in complaints)
    return {
        'total': len(complaints),
        'open_count': sum(complaint.status != 'Resolved' for complaint in complaints),
        'resolved_count': sum(complaint.status == 'Resolved' for complaint in complaints),
        'critical_count': sum(complaint.priority == 'Urgent' for complaint in complaints),
        'top_category': categories.most_common(1)[0][0] if categories else None,
        'top_area': areas.most_common(1)[0][0] if areas else None,
    }

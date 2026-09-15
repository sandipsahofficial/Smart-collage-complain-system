DEPARTMENT_BY_CATEGORY = {
    'Electrical': 'Electrical Maintenance',
    'Water Supply': 'Hostel Maintenance',
    'Hostel Internet': 'IT Support',
    'College Internet': 'IT Support',
    'Cleaning': 'Housekeeping',
    'Hostel Cleaning': 'Housekeeping',
    'Security': 'Security Department',
}


def recommend_department(category: str) -> str:
    return DEPARTMENT_BY_CATEGORY.get(category, 'Campus Facilities')

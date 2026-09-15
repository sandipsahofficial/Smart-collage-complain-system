from .priority_engine import analyze_priority
from .schemas import ComplaintAnalysis

CATEGORY_RULES = {
    'water': ('Water Supply', 'Hostel Maintenance'),
    'tap': ('Water Supply', 'Hostel Maintenance'),
    'leak': ('Room Maintenance', 'Hostel Maintenance'),
    'wifi': ('Hostel Internet', 'IT Support'),
    'internet': ('Hostel Internet', 'IT Support'),
    'electrical': ('Electrical', 'Electrical Maintenance'),
    'sparking': ('Electrical', 'Electrical Maintenance'),
    'light': ('Electrical', 'Electrical Maintenance'),
    'clean': ('Hostel Cleaning', 'Housekeeping'),
    'garbage': ('Hostel Cleaning', 'Housekeeping'),
    'security': ('Security', 'Security Department'),
    'food': ('Food & Dining', 'Catering'),
    'classroom': ('Classroom', 'Campus Facilities'),
    'laboratory': ('Laboratory', 'Campus Facilities'),
    'library': ('Library', 'Campus Facilities'),
}


def classify_complaint(title: str, description: str, location_type: str) -> ComplaintAnalysis:
    text = f'{title} {description}'.lower()
    category, department = ('Other Hostel Issue', 'Hostel Maintenance') if location_type == 'Hostel' else ('Other College Issue', 'Campus Facilities')
    matched = []
    for keyword, result in CATEGORY_RULES.items():
        if keyword in text:
            category, department = result
            if keyword == 'internet' and location_type == 'College':
                category, department = 'College Internet', 'IT Support'
            matched.append(keyword)
            break
    priority, confidence, reasons, safety_critical = analyze_priority(text)
    if matched:
        reasons.insert(0, f'Detected {matched[0]} complaint keyword')
        confidence = min(0.94, confidence + 0.12)
    safety_message = 'Potential Safety-Critical Complaint: immediate human attention recommended.' if safety_critical else None
    sentiment = 'Distressed' if safety_critical else ('Frustrated' if any(word in text for word in ('again', 'nobody', 'unbearable', 'still')) else 'Neutral')
    urgency = 'High' if priority in {'High', 'Urgent'} else 'Normal'
    return ComplaintAnalysis(category, department, priority, confidence, reasons, safety_critical, safety_message, sentiment, urgency)

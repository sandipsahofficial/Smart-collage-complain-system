from .classifier import classify_complaint


def safe_analyze(title: str, description: str, location_type: str):
    try:
        return classify_complaint(title, description, location_type)
    except Exception:
        return None

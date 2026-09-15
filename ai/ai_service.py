import os

from .classifier import classify_complaint
from .duplicate_detector import find_related
from .fallback import safe_analyze
from .openai_provider import OpenAIProvider
from .schemas import ComplaintAnalysis


class AIService:
    """AI facade with an optional OpenAI provider and local fallback."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = enabled if enabled is not None else os.getenv('AI_ENABLED', 'false').lower() == 'true'
        self.provider_name = os.getenv('AI_PROVIDER', 'local').lower()
        self.last_error = None
        self.provider = OpenAIProvider() if self.provider_name == 'openai' else None

    def analyze_complaint(self, title: str, description: str, location_type: str, campus_area: str = '') -> ComplaintAnalysis | None:
        if not self.enabled:
            return None
        if not self.enabled:
            return None
        try:
            if self.provider:
                value = self.provider.analyze_complaint(title, description, location_type, campus_area)
                return ComplaintAnalysis.from_provider(value)
            return classify_complaint(title, description, location_type)
        except Exception as error:
            self.last_error = type(error).__name__
            return safe_analyze(title, description, location_type)

    def related_complaints(self, title: str, description: str, complaints) -> list:
        if not self.enabled:
            return []
        return find_related(title, description, complaints, float(os.getenv('RELATED_THRESHOLD', '0.65')))

    def status(self) -> str:
        if not self.enabled:
            return 'AI disabled'
        if self.provider_name == 'openai' and (self.last_error or not os.getenv('OPENAI_API_KEY') or not self.provider.model):
            return 'OpenAI unavailable; local fallback active'
        return 'OpenAI active' if self.provider else 'Local AI active'

    def answer_admin_question(self, question: str, context: dict, fallback_answer: str) -> str:
        if not self.enabled or not self.provider:
            return fallback_answer
        try:
            return self.provider.answer_question(question, context)
        except Exception as error:
            self.last_error = type(error).__name__
            return fallback_answer

    def status_details(self) -> dict[str, object]:
        configured = bool(os.getenv('OPENAI_API_KEY'))
        return {
            'enabled': self.enabled,
            'provider': self.provider_name,
            'configured': configured if self.provider_name == 'openai' else True,
            'available': self.enabled and (
                self.provider_name != 'openai' or configured
            ),
            'mode': self.status(),
        }

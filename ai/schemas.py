from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComplaintAnalysis:
    category: str
    department: str
    priority: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    safety_critical: bool = False
    safety_message: str | None = None
    sentiment: str = 'Neutral'
    urgency: str = 'Normal'
    summary: str = ''
    insufficient_information: bool = False

    @classmethod
    def from_provider(cls, value: dict[str, Any]) -> 'ComplaintAnalysis':
        required = ('category', 'department', 'priority', 'confidence')
        if any(not isinstance(value.get(key), str) for key in required[:3]):
            raise ValueError('Invalid AI analysis fields.')
        confidence = value.get('confidence')
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError('Invalid AI confidence.')
        if value['priority'] not in {'Low', 'Medium', 'High', 'Critical'}:
            raise ValueError('Invalid AI priority.')
        return cls(
            category=value['category'][:80],
            department=value['department'][:80],
            priority='Urgent' if value['priority'] == 'Critical' else value['priority'],
            confidence=float(confidence),
            reasons=[value.get('reason', '')[:500]] if value.get('reason') else [],
            safety_critical=value.get('safety_classification') == 'safety_critical',
            safety_message='Potential Safety-Critical Complaint: immediate human review recommended.' if value.get('safety_classification') == 'safety_critical' else None,
            sentiment='Neutral',
            urgency=value.get('urgency', 'Normal')[:40],
            summary=value.get('summary', '')[:300],
            insufficient_information=bool(value.get('insufficient_information', False)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            'category': self.category,
            'department': self.department,
            'priority': self.priority,
            'confidence': round(self.confidence, 2),
            'reasons': self.reasons,
            'safety_critical': self.safety_critical,
            'safety_message': self.safety_message,
            'sentiment': self.sentiment,
            'urgency': self.urgency,
            'summary': self.summary,
            'insufficient_information': self.insufficient_information,
        }


@dataclass
class RelatedComplaint:
    complaint_id: int
    ticket_number: str
    similarity: float
    reason: str


@dataclass
class Insights:
    total: int
    open_count: int
    resolved_count: int
    critical_count: int
    top_category: str | None
    top_area: str | None
    duplicate_count: int = 0

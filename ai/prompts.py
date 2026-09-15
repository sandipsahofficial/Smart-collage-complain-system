SYSTEM_PROMPT = """You are the AI assistant for a college and hostel complaint management system.
Understand complaint text accurately and provide concise, explainable recommendations.
Never invent facts that are not in the supplied context. Never claim an action was performed.
Treat every prediction as a suggestion requiring human review. For safety-critical complaints,
recommend immediate human review without giving dangerous technical instructions.
Return only the requested structured JSON object."""

COMPLAINT_ANALYSIS_SCHEMA = {
    'type': 'object',
    'properties': {
        'category': {'type': 'string', 'maxLength': 80},
        'department': {'type': 'string', 'maxLength': 80},
        'priority': {'type': 'string', 'enum': ['Low', 'Medium', 'High', 'Critical']},
        'urgency': {'type': 'string', 'maxLength': 40},
        'summary': {'type': 'string', 'maxLength': 300},
        'reason': {'type': 'string', 'maxLength': 500},
        'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'safety_classification': {'type': 'string', 'enum': ['normal', 'urgent', 'safety_critical']},
        'insufficient_information': {'type': 'boolean'},
    },
    'required': [
        'category', 'department', 'priority', 'urgency', 'summary', 'reason',
        'confidence', 'safety_classification', 'insufficient_information',
    ],
    'additionalProperties': False,
}

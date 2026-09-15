import json
import os

from .privacy import complaint_context
from .prompts import COMPLAINT_ANALYSIS_SCHEMA, SYSTEM_PROMPT


class OpenAIProvider:
    """OpenAI Responses API adapter. The SDK client is created only when used."""

    def __init__(self, client=None):
        self.model = os.getenv('AI_MODEL', '').strip()
        self.timeout = float(os.getenv('AI_TIMEOUT', '30'))
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise RuntimeError('OPENAI_API_KEY is not configured.')
            self._client = OpenAI(api_key=api_key, timeout=self.timeout)
        return self._client

    def analyze_complaint(self, title: str, description: str, location_type: str, campus_area: str = '') -> dict:
        if not self.model:
            raise RuntimeError('AI_MODEL is not configured.')
        context = complaint_context(title, description, location_type, campus_area)
        response = self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=[{'role': 'user', 'content': json.dumps(context)}],
            text={
                'format': {
                    'type': 'json_schema',
                    'name': 'complaint_analysis',
                    'strict': True,
                    'schema': COMPLAINT_ANALYSIS_SCHEMA,
                }
            },
        )
        return json.loads(response.output_text)

    def answer_question(self, question: str, context: dict) -> str:
        if not self.model:
            raise RuntimeError('AI_MODEL is not configured.')
        response = self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT + ' Answer the administrator using only the supplied verified database context. Never invent numbers.',
            input=[{'role': 'user', 'content': json.dumps({'question': question[:300], 'database_context': context})}],
        )
        return response.output_text[:1000]

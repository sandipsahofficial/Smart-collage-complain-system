from ai.ai_service import AIService
from ai.classifier import classify_complaint
from ai.duplicate_detector import cosine_similarity
from ai.query import answer_question, parse_admin_question


def test_ai_disabled_is_safe_and_returns_no_external_result():
    service = AIService(enabled=False)
    assert service.status() == 'AI disabled'
    assert service.analyze_complaint('Water leak', 'Tap is leaking', 'Hostel') is None


def test_ai_is_disabled_by_default_without_configuration(monkeypatch):
    monkeypatch.delenv('AI_ENABLED', raising=False)
    service = AIService()
    assert service.enabled is False


def test_openai_provider_parses_structured_responses():
    from ai.openai_provider import OpenAIProvider

    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs['text']['format']['type'] == 'json_schema'
            return type('Response', (), {'output_text': '{"category":"Hostel Water Supply","department":"Hostel Maintenance","priority":"Medium","urgency":"Moderate","summary":"A leaking tap","reason":"Continuous water leakage","confidence":0.91,"safety_classification":"normal","insufficient_information":false}'})()

    fake_client = type('Client', (), {'responses': FakeResponses()})()
    provider = OpenAIProvider(client=fake_client)
    provider.model = 'test-model'
    result = provider.analyze_complaint('Leaking tap', 'Tap leaks continuously', 'Hostel')
    assert result['category'] == 'Hostel Water Supply'


def test_openai_status_never_exposes_api_key(monkeypatch):
    monkeypatch.setenv('AI_ENABLED', 'true')
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'secret-test-key')
    service = AIService(enabled=True)
    details = service.status_details()
    assert details['configured'] is True
    assert 'secret-test-key' not in str(details)


def test_local_classifier_is_explainable_and_location_aware():
    result = classify_complaint(
        'Internet outage',
        'College internet is completely unavailable.',
        'College',
    )
    assert result.category == 'College Internet'
    assert result.department == 'IT Support'
    assert result.priority == 'High'
    assert result.reasons
    assert 0 <= result.confidence <= 1


def test_priority_engine_flags_safety_complaint():
    result = classify_complaint(
        'Electrical problem',
        'There is electrical sparking from an exposed wire.',
        'Hostel',
    )
    assert result.priority == 'Urgent'
    assert result.safety_critical is True
    assert result.safety_message


def test_duplicate_detector_uses_similarity_not_exact_match():
    score = cosine_similarity(
        'Hostel WiFi is not working',
        'Internet is not working in hostel block A',
    )
    assert score >= 0.65


def test_admin_query_parser_handles_priority_questions():
    parsed = parse_admin_question('How many urgent complaints are there?')
    assert parsed['intent'] == 'count'
    assert parsed['filters']['priority'] == 'Urgent'


def test_admin_query_answer_counts_filtered_complaints():
    class ComplaintStub:
        def __init__(self, priority, status, category='Electrical', title='Issue', description='Issue'):
            self.priority = priority
            self.status = status
            self.category = category
            self.title = title
            self.description = description

    result = answer_question('total urgent complaints', [
        ComplaintStub('Urgent', 'Pending'),
        ComplaintStub('Medium', 'Resolved'),
    ])
    assert result['count'] == 1


def test_admin_query_does_not_guess_unknown_questions():
    result = answer_question('What is the weather today?', [])
    assert result['query']['intent'] == 'help'
    assert 'verified complaint questions' in result['answer']


def test_admin_query_understands_hindi_urgent_question():
    parsed = parse_admin_question('कितनी जरूरी शिकायतें हैं?')
    assert parsed['intent'] == 'count'
    assert parsed['filters']['priority'] == 'Urgent'

import os

AI_ENABLED = os.getenv('AI_ENABLED', 'false').lower() == 'true'
AI_PROVIDER = os.getenv('AI_PROVIDER', 'local')
AI_MODEL = os.getenv('AI_MODEL', '')
AI_TIMEOUT = float(os.getenv('AI_TIMEOUT', '30'))
AI_EXTERNAL_DATA_ALLOWED = os.getenv('AI_EXTERNAL_DATA_ALLOWED', 'false').lower() == 'true'
DUPLICATE_THRESHOLD = float(os.getenv('DUPLICATE_THRESHOLD', '0.80'))
RELATED_THRESHOLD = float(os.getenv('RELATED_THRESHOLD', '0.65'))

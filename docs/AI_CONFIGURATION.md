# AI Configuration

AI is disabled by default to prevent accidental API usage. The local provider makes no external network calls.

```env
AI_ENABLED=false
AI_PROVIDER=local
OPENAI_API_KEY=
AI_MODEL=
AI_TIMEOUT=30
RELATED_THRESHOLD=0.65
DUPLICATE_THRESHOLD=0.80
AI_EXTERNAL_DATA_ALLOWED=false
```

Set `AI_ENABLED=true` to enable analysis. Set `AI_PROVIDER=local` for offline analysis or `AI_PROVIDER=openai` with `OPENAI_API_KEY` and `AI_MODEL` for the OpenAI Responses API. The application remains functional when AI is disabled or unavailable.

Admins can check the non-secret provider state at `GET /admin/ai/status`.

There is currently no external provider implementation. Do not add provider credentials to source control or `.env` files committed to Git.

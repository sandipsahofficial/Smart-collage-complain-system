# AI Architecture

The AI layer is optional and local-first. Flask communicates with `ai.AIService`, rather than importing classification rules into route handlers.

`AIService` returns structured `ComplaintAnalysis` data. The current local provider uses explainable keyword rules for category, department, priority, safety signals, and sentiment, plus token cosine similarity for related complaints. No network call or external API key is required.

AI analysis is stored as an audit record when `AI_ENABLED=true`. Suggestions are informational: the existing complaint priority, assignment, and status remain human-controlled.

Future providers can implement the same service contract. External providers must be disabled unless explicitly configured and privacy-approved.

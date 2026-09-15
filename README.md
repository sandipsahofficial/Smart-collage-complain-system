# Smart College & Hostel Complaint System

Flask-based complaint management for college and hostel operations.

## Local Setup

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000`.

The admin login is available at `http://127.0.0.1:5000/admin/login`.

For production, set `APP_ENV=production` and provide a strong `SECRET_KEY`.
Demo staff and student accounts are enabled by default only for local development;
set `SEED_DEMO_DATA=false` explicitly in production.

The deployment health check is available at `http://127.0.0.1:5000/health`.

## Production Configuration

Set `SECRET_KEY` and `DATABASE_URL`. For persistent complaint images, configure:

```env
S3_BUCKET=your-bucket
S3_REGION=us-east-1
S3_PREFIX=complaint-images
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

Without `S3_BUCKET`, local development stores validated images in `static/uploads/`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers CSRF rejection, route health, upload signature validation, UUID filenames, and staff assignment authorization.

## Optional AI assistance

The optional AI layer is disabled by default and never required for the core complaint workflow. Set `AI_ENABLED=true` to enable it. Use `AI_PROVIDER=local` for offline analysis or `AI_PROVIDER=openai` with `OPENAI_API_KEY` and `AI_MODEL` for the real OpenAI Responses API. Suggestions are stored for audit and remain subject to human review.

Supported settings include `AI_PROVIDER=local`, `RELATED_THRESHOLD=0.65`, `DUPLICATE_THRESHOLD=0.80`, and `AI_EXTERNAL_DATA_ALLOWED=false`. The current implementation makes no external API calls; external data sharing remains disabled by default.

See [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md), [docs/AI_CONFIGURATION.md](docs/AI_CONFIGURATION.md), and [docs/AI_PRIVACY.md](docs/AI_PRIVACY.md).
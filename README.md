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

## Architecture Overview

`app.py` owns Flask configuration, authentication, route handlers, CSRF, rate limits, Socket.IO events, and the application-level error boundaries. `database.py` defines the SQLAlchemy models. Domain helpers are kept in `services/`: `sla.py` contains idempotent SLA evaluation and escalation, while `query_tools.py` contains admin filtering and CSV serialization. `storage/service.py` abstracts local development storage and private S3 object storage. Templates are rendered server-side and use the authenticated session identity for all student data.

Request flow for a state-changing browser request:

```text
Browser form / fetch
	-> Flask-WTF CSRF validation
	-> authentication and role/ownership check
	-> route validation and SQLAlchemy mutation
	-> notification, audit, and Socket.IO event (when applicable)
	-> redirect or JSON response
```

## API and Route Reference

All POST routes require a valid CSRF token. Student and staff complaint routes also enforce ownership or assignment checks server-side.

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| GET/POST | `/`, `/login` | Public | Student/staff login |
| GET/POST | `/admin/login` | Public | Administrator login |
| GET/POST | `/register` | Public | Student registration |
| GET | `/student_dashboard` | Student | Student overview |
| GET | `/student/complaints` | Student | Search, filter, and sort own complaints |
| GET | `/student/complaint/<id>` | Complaint owner | Complaint detail and recorded timeline |
| GET | `/student/notifications` | Student | Own notifications |
| GET | `/student/announcements` | Student | Published campus announcements |
| GET | `/student/<page>` | Student | New complaint, help, contact, profile, settings, password views |
| POST | `/student/profile` | Student | Update safe profile fields |
| POST | `/student/settings` | Student | Persist notification and theme preferences |
| POST | `/submit_complaint` | Student | Create a complaint and optional validated image |
| POST | `/add_comment/<id>` | Owner/assigned staff/admin | Add an authorized complaint comment |
| POST | `/close_complaint/<id>` | Complaint owner | Close a resolved complaint |
| POST | `/notifications/read/<id>` | Notification owner | Mark one notification read |
| POST | `/notifications/read-all` | Authenticated user | Mark own notifications read |
| POST | `/api/student/ai` | Student | Answer questions using own complaint context |
| GET | `/staff_dashboard` | Staff | Assigned complaint queue |
| POST | `/update_status/<id>` | Assigned staff | Update complaint status and notify student |
| POST | `/assign/<id>` | Admin | Assign complaint to staff |
| GET | `/admin_dashboard` | Admin | System dashboard and filters |
| POST | `/admin/announcements` | Admin | Publish a database-backed announcement |
| GET | `/admin/complaints/export.csv` | Admin | Export filtered complaints as CSV |
| GET | `/admin/complaints/export.pdf` | Admin | Export filtered complaints as PDF |
| POST | `/admin/ai-query` | Admin | Query system-wide complaint context |
| POST | `/api/ai/analyze/<id>` | Staff/Admin | Generate AI analysis for an authorized work item |
| POST | `/logout` | Authenticated user | CSRF-protected session logout |
| GET | `/health` | Public | Liveness check |

JSON error conventions: API CSRF failures return HTTP 400 with `{"error": "Invalid or missing CSRF token."}`. Unauthorized API access returns HTTP 403. Browser routes generally redirect to login for an absent session and return HTTP 403 for an authenticated but unauthorized role or resource.

## Database Schema

The application uses SQLAlchemy models and calls `db.create_all()` plus a small SQLite compatibility migration at startup. Production deployments should use a real migration tool before making destructive schema changes.

| Model | Important fields and relationships |
|---|---|
| `User` | `username`, password hash, `role`, profile fields, login lockout fields, notification/theme preferences. Owns complaints, comments, notifications, audit events, and announcements. |
| `Complaint` | Ticket number, title, description, category, location, priority, status, student and assigned-staff foreign keys, image storage key, AI fields, SLA fields. |
| `Comment` | Message, author, complaint foreign key, timestamp. |
| `Notification` | Recipient, optional complaint, title/message, read flag, timestamp. |
| `Announcement` | Title, description, category, importance, author, timestamp. Visible to students after admin publication. |
| `AuditEvent` | Complaint, optional actor, event type, details, timestamp. Used by submission, assignment, status, closing, and SLA escalation flows. |
| `AIAnalysis` | Complaint, analysis type, input hash, prediction, confidence, provider/model, review fields. |
| `ComplaintSimilarity` | Complaint pair, similarity score, relationship, timestamp. |
| `AIFeedback` | Analysis, reviewer, correctness flag, timestamp. |

Ownership rules are expressed through `Complaint.student_id` and `Complaint.assigned_to`. Never query a student complaint by ID alone; always add `student_id=session['user_id']` or perform an explicit ownership check before rendering or mutating it.

## SLA, Real-Time Updates, and Reports

The application exposes `run_sla_check()` for cron, Celery, or a worker process. When launched with `python app.py`, an optional background thread runs the scan every `SLA_CHECK_INTERVAL_SECONDS` (default 300 seconds). SLA thresholds are Urgent 4 hours, High 12 hours, Medium 48 hours, and Low 72 hours. Overdue open complaints become `Escalated`, receive an `AuditEvent`, and notify administrators.

Authenticated dashboards connect to Flask-SocketIO. Staff status changes emit `complaint_updated` to the affected student's private session room, updating the visible status badge without a page refresh.

Administrators can filter complaints by status, category, block, and date range in the assignment panel. The same query parameters are supported by `/admin/complaints/export.csv` and `/admin/complaints/export.pdf`; both endpoints require an administrator session.

## Production Configuration

Set `SECRET_KEY` and `DATABASE_URL`. For persistent complaint images, configure:

```env
S3_BUCKET=your-bucket
S3_REGION=us-east-1
S3_PREFIX=complaint-images
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

Set `STORAGE_PROVIDER=s3` and `STORAGE_BUCKET` (or `S3_BUCKET`) in deployed environments. Objects are private and are served only after complaint authorization through short-lived presigned URLs. Local disk storage is retained only as a development fallback.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers CSRF rejection, route health, authentication and lockout, role authorization, student ownership, complaint lifecycle, upload signature validation, UUID filenames, storage access, SLA escalation, audit events, CSV/PDF exports, Socket.IO authentication, and student portal rendering.

### Test Layout

| File | Coverage |
|---|---|
| `tests/conftest.py` | In-memory SQLite fixture, isolated Flask client, users, and image factory |
| `tests/test_auth.py` | Registration, login, CSRF, password lockout, default admin behavior |
| `tests/test_authorization.py` | Student/admin/staff route and complaint ownership boundaries |
| `tests/test_app.py` | Core routes, complaint lifecycle, notifications, uploads, and dashboard compatibility |
| `tests/test_uploads.py` | Valid images, invalid signatures, traversal names, and size limits |
| `tests/test_security_storage.py` | CSRF logout, MIME/signature-derived UUID names, and protected image retrieval |
| `tests/test_sla_and_reporting.py` | Idempotent escalation, audit events, admin exports, and anonymous Socket.IO rejection |

### Focused Test Commands

```powershell
# Full regression suite
.\.venv\Scripts\python.exe -m pytest -q

# One module with verbose assertion output
.\.venv\Scripts\python.exe -m pytest -q tests/test_sla_and_reporting.py -vv

# One behavior while iterating
.\.venv\Scripts\python.exe -m pytest -q tests/test_auth.py::test_missing_csrf_is_rejected
```

Tests use an in-memory SQLite database and disable rate limiting for determinism. They should not rely on the developer's `college.db`, local uploads, S3 credentials, SMTP server, or external AI provider. Provider-backed behavior should be tested with a fake storage/service boundary rather than live credentials.

## Error Boundaries and Failure Behavior

The application has explicit boundaries for the most common operational failures:

| Boundary | Behavior |
|---|---|
| CSRF failure | Logs the request path and returns HTTP 400; API routes receive JSON while browser routes receive a plain error response. |
| Upload over limit | Handles HTTP 413, flashes a user-facing message, and redirects to the referring page or student dashboard. |
| Missing route | Returns the login template with HTTP 404 to avoid exposing internal route details. |
| Unhandled server exception | Logs the stack trace server-side and returns a generic login/error page with HTTP 500. |
| Invalid report dates | Returns HTTP 400 for exports; the admin dashboard falls back to the unfiltered list and flashes a validation message. |
| Missing storage object | Returns HTTP 404 after authorization; it does not reveal whether another user's object exists. |
| Unavailable AI provider | Returns a controlled unavailable response; complaint submission and core workflows continue without AI. |
| SLA worker failure | Logs the exception and leaves the worker alive so the next scheduled scan can retry. |

Do not include passwords, access keys, storage URLs, raw exception text, or database connection strings in client responses. Add a route-specific JSON error handler when introducing a new API namespace so clients receive stable error shapes.

## Documentation and Review Checklist

When adding a feature, update the route table and schema table if the public surface or persistence model changes. Add a focused pytest covering the success path, authentication boundary, authorization boundary, validation failure, and the relevant empty/error state. For background jobs, test idempotency and retry behavior. For templates, verify the real authenticated user's data is rendered and that a second user's resource cannot be reached by changing a URL ID.

## Optional AI assistance

The optional AI layer is disabled by default and never required for the core complaint workflow. Set `AI_ENABLED=true` to enable it. Use `AI_PROVIDER=local` for offline analysis or `AI_PROVIDER=openai` with `OPENAI_API_KEY` and `AI_MODEL` for the real OpenAI Responses API. Suggestions are stored for audit and remain subject to human review.

Supported settings include `AI_PROVIDER=local`, `RELATED_THRESHOLD=0.65`, `DUPLICATE_THRESHOLD=0.80`, and `AI_EXTERNAL_DATA_ALLOWED=false`. The current implementation makes no external API calls; external data sharing remains disabled by default.

See [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md), [docs/AI_CONFIGURATION.md](docs/AI_CONFIGURATION.md), and [docs/AI_PRIVACY.md](docs/AI_PRIVACY.md).
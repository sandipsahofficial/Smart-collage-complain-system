# Smart College & Hostel Complaint System

Flask-based complaint management for college and hostel operations.

## Local Setup

```powershell
\.venv\Scripts\python.exe -m pip install -r requirements.txt
\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000`.

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
\.venv\Scripts\python.exe -m pytest -q
```

The suite covers CSRF rejection, route health, upload signature validation, UUID filenames, and staff assignment authorization.
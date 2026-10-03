import hashlib
import io
import json
import logging
import mimetypes
import os
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO, join_room
from flask_wtf.csrf import CSRFProtect, CSRFError
from PIL import Image, UnidentifiedImageError
from sqlalchemy import inspect, text
from werkzeug.datastructures import FileStorage
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from ai import AIService
from ai.query import answer_question
from ai.summarizer import summarize
from database import AIAnalysis, Announcement, AuditEvent, Complaint, Comment, ComplaintSimilarity, Notification, User, db
from storage.service import get_storage_service
from services.query_tools import complaints_csv, filtered_complaints
from services.sla import evaluate_sla

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('sccs')

app = Flask(__name__)

app_environment = os.getenv('APP_ENV', 'development').lower()
secret_key = os.getenv('SECRET_KEY')
if app_environment == 'production' and not secret_key:
    raise RuntimeError('SECRET_KEY must be configured in production.')
app.config['SECRET_KEY'] = secret_key or 'dev-only-secret-key-change-me'
app.config['WTF_CSRF_TIME_LIMIT'] = 3600
app.config['SESSION_COOKIE_SECURE'] = app_environment == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['RATELIMIT_ENABLED'] = os.getenv('RATELIMIT_ENABLED', 'true').lower() == 'true'
database_url = os.getenv('DATABASE_URL', 'sqlite:///college.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_SIZE', 5 * 1024 * 1024))
app.config['UPLOAD_FOLDER'] = os.path.join('instance', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['MAX_UPLOAD_BYTES'] = app.config['MAX_CONTENT_LENGTH']
app.config['S3_BUCKET'] = os.getenv('STORAGE_BUCKET') or os.getenv('S3_BUCKET')
app.config['S3_REGION'] = os.getenv('STORAGE_REGION') or os.getenv('S3_REGION', 'us-east-1')
app.config['S3_PREFIX'] = os.getenv('STORAGE_PREFIX') or os.getenv('S3_PREFIX', 'complaint-images')
app.config['STORAGE_PROVIDER'] = (os.getenv('STORAGE_PROVIDER') or ('s3' if app.config['S3_BUCKET'] else 'local')).lower()
app.config['ALLOWED_UPLOAD_TYPES'] = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
app.config['WTF_CSRF_CHECK_DEFAULT'] = True
if app_environment == 'production' and app.config['STORAGE_PROVIDER'] == 'local':
    raise RuntimeError('Persistent object storage must be configured in production.')
ai_service = AIService()

csrf = CSRFProtect()
csrf.init_app(app)
socketio = SocketIO(app, cors_allowed_origins=[], async_mode='threading')
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
)
limiter.enabled = app.config['RATELIMIT_ENABLED']


@app.before_request
def sync_limiter_state():
    limiter.enabled = app.config.get('RATELIMIT_ENABLED', True)


LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15
COLLEGE_CATEGORIES = {
    'Classroom', 'Laboratory', 'Library', 'Cafeteria', 'College Internet',
    'Electrical', 'Cleaning', 'Security', 'Other College Issue',
}
HOSTEL_CATEGORIES = {
    'Room Maintenance', 'Water Supply', 'Electrical', 'Hostel Cleaning',
    'Hostel Internet', 'Security', 'Food & Dining', 'Other Hostel Issue',
}
VALID_PRIORITIES = {'Low', 'Medium', 'High', 'Urgent'}
ALLOWED_UPLOAD_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    # Keep browser and API clients on stable response shapes while never echoing validation details.
    logger.warning('CSRF validation failed for %s from %s', request.path, request.remote_addr)
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Invalid or missing CSRF token.'}), 400
    return ('Invalid or missing CSRF token.', 400)


@app.errorhandler(413)
def handle_entity_too_large(error):
    flash('The uploaded file is too large. Please upload a smaller image (max 5 MB).', 'error')
    return redirect(request.referrer or url_for('student_dashboard'))


@app.errorhandler(404)
def handle_not_found(error):
    return render_template('login.html'), 404


@app.errorhandler(500)
def handle_internal_error(error):
    logger.exception('Unhandled server error on %s', request.path)
    return render_template('login.html', error='An unexpected error occurred. Please try again later.'), 500


def utc_now():
    return datetime.now(timezone.utc)


def ensure_default_admin():
    admin = User.query.filter_by(username='admin').first()
    if admin is None:
        default_password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'change-me-in-production')
        db.session.add(User(
            username='admin',
            password=generate_password_hash(default_password),
            role='admin',
            full_name='Hostel Administrator',
            email='admin@college.edu',
            phone='9000000001',
            hostel_name='Main Hostel'
        ))
        db.session.commit()
        return

    if admin.role != 'admin':
        admin.role = 'admin'
        admin.full_name = admin.full_name or 'Hostel Administrator'
        admin.email = admin.email or 'admin@college.edu'
        admin.phone = admin.phone or '9000000001'
        admin.hostel_name = admin.hostel_name or 'Main Hostel'
        db.session.commit()


def seed_demo_data():
    default_seed_value = 'false' if app_environment == 'production' else 'true'
    should_seed_demo_data = os.getenv('SEED_DEMO_DATA', default_seed_value).lower() == 'true'

    ensure_default_admin()

    if not should_seed_demo_data:
        return

    demo_staff_password = os.getenv('DEMO_STAFF_PASSWORD', 'staff123')
    demo_student_password = os.getenv('DEMO_STUDENT_PASSWORD', 'student123')

    demo_staff = User.query.filter_by(username='staff').first()
    if demo_staff is None:
        db.session.add(User(
            username='staff',
            password=generate_password_hash(demo_staff_password),
            role='staff',
            full_name='Maintenance Staff',
            email='staff@college.edu',
            phone='9000000002',
            hostel_name='Main Hostel'
        ))

    demo_student = User.query.filter_by(username='student').first()
    if demo_student is None:
        db.session.add(User(
            username='student',
            password=generate_password_hash(demo_student_password),
            role='student',
            full_name='Student User',
            email='student@college.edu',
            phone='9000000003',
            hostel_name='Main Hostel',
            block='A',
            room_number='101'
        ))
    db.session.commit()


def enforce_single_admin():
    admin_accounts = User.query.filter_by(role='admin').order_by(User.id).all()
    for extra_admin in admin_accounts[1:]:
        extra_admin.role = 'staff'
    db.session.commit()


def detect_file_mime(file_bytes: bytes, filename: str):
    if file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if file_bytes.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if file_bytes.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if file_bytes.startswith(b'RIFF') and file_bytes[8:12] == b'WEBP':
        return 'image/webp'
    lower_name = filename.lower()
    if lower_name.endswith('.pdf'):
        return 'application/pdf'
    return None


def validate_uploaded_file(file_storage: FileStorage, allowed_mime_types=None):
    allowed_mime_types = allowed_mime_types or app.config['ALLOWED_UPLOAD_TYPES']
    if file_storage is None or not getattr(file_storage, 'filename', None):
        return None

    original_name = file_storage.filename or 'upload'
    safe_name = secure_filename(original_name)
    if not safe_name or safe_name in {'.', '..'} or '/' in safe_name or '\\' in safe_name:
        return None

    file_storage.stream.seek(0)
    data = file_storage.stream.read()
    if not data:
        return None
    if len(data) > app.config['MAX_UPLOAD_BYTES']:
        return None

    mime_type = detect_file_mime(data, safe_name)
    if mime_type not in allowed_mime_types:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            mime_type = 'image/' + (image.format or 'png').lower()
        except (UnidentifiedImageError, OSError):
            return None
        if mime_type not in allowed_mime_types:
            return None

    extension_map = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/webp': '.webp',
    }
    safe_storage_name = f"{uuid.uuid4().hex}{extension_map.get(mime_type, '.png')}"

    storage_service = get_storage_service()
    result = storage_service.save_upload(io.BytesIO(data), safe_storage_name, content_type=mime_type)
    if not result or not result.get('storage_key'):
        return None
    return {
        'storage_key': result['storage_key'],
        'original_name': result['original_name'],
        'mime_type': mime_type,
        'size': len(data),
        'public_url': result.get('public_url', ''),
    }


def store_complaint_image(uploaded_file: FileStorage):
    """Validate file bytes and store them in a provider-backed upload store."""
    if uploaded_file is None:
        return None
    result = validate_uploaded_file(uploaded_file)
    if result is None:
        return None
    return result['storage_key']


@app.context_processor
def inject_upload_helpers():
    return {}


@app.context_processor
def inject_notifications():
    if 'user_id' not in session:
        return {'notifications': [], 'unread_notification_count': 0}
    user_notifications = Notification.query.filter_by(
        recipient_id=session['user_id']
    ).order_by(Notification.created_at.desc()).limit(20).all()
    unread_count = Notification.query.filter_by(
        recipient_id=session['user_id'], is_read=False
    ).count()
    return {
        'notifications': user_notifications,
        'unread_notification_count': unread_count,
    }


@app.context_processor
def inject_ai_status():
    if 'user_id' not in session:
        return {'ai_status': ai_service.status(), 'ai_suggestions': []}

    query = Complaint.query.order_by(Complaint.created_at.desc())
    if session.get('role') == 'student':
        query = query.filter_by(student_id=session['user_id'])
    elif session.get('role') == 'staff':
        query = query.filter_by(assigned_to=session['user_id'])
    suggestions = query.filter(Complaint.ai_category.isnot(None)).limit(5).all()
    return {'ai_status': ai_service.status(), 'ai_suggestions': suggestions}


import smtplib
from email.message import EmailMessage

def send_email_async(to_email, subject, body):
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = os.getenv('SMTP_PORT', 587)
    smtp_user = os.getenv('SMTP_USERNAME')
    smtp_pass = os.getenv('SMTP_PASSWORD')
    
    if not smtp_server or not smtp_user or not smtp_pass:
        return
        
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = to_email
        
        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")

def create_notification(recipient_id, title, message, complaint=None):
    recipient = db.session.get(User, recipient_id)
    if not recipient: return
    
    db.session.add(Notification(
        recipient_id=recipient_id,
        complaint_id=complaint.id if complaint else None,
        title=title,
        message=message,
    ))
    
    if recipient.email:
        threading.Thread(
            target=send_email_async,
            args=(recipient.email, title, message),
            daemon=True
        ).start()


def notify_admins(title, message, complaint):
    for admin in User.query.filter_by(role='admin').all():
        create_notification(admin.id, title, message, complaint)


def record_audit_event(complaint, event_type, details, actor_id=None):
    db.session.add(AuditEvent(
        complaint_id=complaint.id,
        actor_id=actor_id,
        event_type=event_type,
        details=details,
    ))


def ticket_number_for(complaint):
    return f'SCCS-{complaint.created_at.year}-{complaint.id:06d}'


def authenticate_user(user, password):
    if not user:
        return False

    now = utc_now()
    if user.locked_until:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            return False
        user.failed_login_attempts = 0
        user.locked_until = None

    if user.password == password or check_password_hash(user.password, password):
        user.failed_login_attempts = 0
        user.locked_until = None
        if user.password == password and not (user.password.startswith('pbkdf2:') or user.password.startswith('scrypt:')):
            user.password = generate_password_hash(password)
        db.session.commit()
        return True

    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= LOGIN_MAX_ATTEMPTS:
        user.locked_until = now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
    db.session.commit()
    return False


def require_authentication():
    if 'user_id' not in session:
        abort(401)


def require_role(*roles):
    if session.get('role') not in roles:
        abort(403)


def roles_required(*roles):
    """Decorator for routes whose authorization must fail closed with 403."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            require_authentication()
            require_role(*roles)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def emit_complaint_update(event_name, payload, user_ids=None):
    recipients = set(user_ids or [])
    recipients.update(user.id for user in User.query.filter_by(role='admin').all())
    for user_id in recipients:
        socketio.emit(event_name, payload, to=f'user:{user_id}')


@socketio.on('connect')
def socket_connect():
    if 'user_id' not in session:
        return False
    join_room(f'user:{session["user_id"]}')


def run_sla_check():
    """Run one idempotent SLA scan; suitable for cron, Celery, or a thread."""
    with app.app_context():
        return evaluate_sla(notify_admins=notify_admins, emit_event=emit_complaint_update)


def start_sla_scheduler(interval_seconds=None):
    interval_seconds = interval_seconds or int(os.getenv('SLA_CHECK_INTERVAL_SECONDS', '300'))
    stop_event = threading.Event()

    def worker():
        while not stop_event.wait(interval_seconds):
            try:
                run_sla_check()
            except Exception:
                logger.exception('SLA scan failed')

    thread = threading.Thread(target=worker, name='sla-scheduler', daemon=True)
    thread.start()
    return stop_event


def get_complaint_or_403(complaint_id, role=None):
    complaint = db.get_or_404(Complaint, complaint_id)
    if role == 'admin':
        return complaint
    if role == 'student':
        if complaint.student_id != session.get('user_id'):
            abort(403)
        return complaint
    if role == 'staff':
        if complaint.assigned_to != session.get('user_id'):
            abort(403)
        return complaint
    return complaint


db.init_app(app)


def migrate_sqlite_schema():
    """Add columns introduced after the initial SQLite database was created."""
    # This compatibility migration is intentionally additive; production schema changes should use migrations.
    inspector = inspect(db.engine)
    migrations = {
        'user': {
            'failed_login_attempts': 'INTEGER DEFAULT 0',
            'locked_until': 'DATETIME',
            'full_name': 'VARCHAR(120)',
            'phone': 'VARCHAR(30)',
            'hostel_name': 'VARCHAR(80)',
            'block': 'VARCHAR(50)',
            'room_number': 'VARCHAR(20)',
            'department': 'VARCHAR(100)',
            'year': 'VARCHAR(20)',
            'section': 'VARCHAR(20)',
            'notifications_enabled': 'BOOLEAN DEFAULT 1',
            'announcement_notifications_enabled': 'BOOLEAN DEFAULT 1',
            'theme': "VARCHAR(20) DEFAULT 'light'",
        },
        'complaint': {
            'ticket_number': 'VARCHAR(30)',
            'location_type': "VARCHAR(30) DEFAULT 'Hostel'",
            'campus_area': "VARCHAR(100) DEFAULT 'Main Hostel'",
            'hostel_name': "VARCHAR(80) DEFAULT 'Main Hostel'",
            'block': "VARCHAR(50) DEFAULT 'A'",
            'room_number': "VARCHAR(20) DEFAULT '101'",
            'priority': "VARCHAR(20) DEFAULT 'Medium'",
            'image_filename': 'VARCHAR(255)',
            'rating': 'INTEGER',
            'feedback_text': 'TEXT',
            'ai_category': 'VARCHAR(80)',
            'ai_department': 'VARCHAR(80)',
            'ai_priority': 'VARCHAR(20)',
            'ai_confidence': 'FLOAT',
            'ai_reasons': 'TEXT',
            'ai_safety_critical': 'BOOLEAN DEFAULT 0',
            'escalated_at': 'DATETIME',
            'sla_due_at': 'DATETIME',
        },
    }

    for table_name, columns in migrations.items():
        existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
        for column_name, column_definition in columns.items():
            if column_name not in existing_columns:
                db.session.execute(
                    text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}')
                )
    db.session.commit()

    for complaint in Complaint.query.filter_by(ticket_number=None).all():
        complaint.ticket_number = ticket_number_for(complaint)
    db.session.commit()


with app.app_context():
    db.create_all()
    migrate_sqlite_schema()
    seed_demo_data()
    enforce_single_admin()


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def login():
    if request.method == 'POST':
        csrf_token = request.form.get('csrf_token')
        if not csrf_token and app.config.get('WTF_CSRF_ENABLED', True):
            abort(400)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(username=username).first()

        if authenticate_user(user, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role

            if user.role == 'student':
                return redirect(url_for('student_dashboard'))
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('staff_dashboard'))

        flash('Invalid username or password!', 'error')
        if request.endpoint == 'root_login':
            return redirect(url_for('root_login'))
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/', methods=['GET', 'POST'], endpoint='root_login')
@limiter.limit('10 per minute', methods=['POST'], exempt_when=lambda: app.config.get('TESTING', False) or not app.config.get('RATELIMIT_ENABLED', True))
def root_login():
    return login()


@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'], exempt_when=lambda: app.config.get('TESTING', False) or not app.config.get('RATELIMIT_ENABLED', True))
def admin_login():
    if request.method == 'POST':
        csrf_token = request.form.get('csrf_token')
        if not csrf_token and app.config.get('WTF_CSRF_ENABLED', True):
            abort(400)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(username=username, role='admin').first()
        if authenticate_user(user, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            return redirect(url_for('admin_dashboard'))

        flash('Invalid admin username or password!', 'error')
        return redirect(url_for('admin_login'))

    return render_template('admin_login.html')


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'], exempt_when=lambda: app.config.get('TESTING', False) or not app.config.get('RATELIMIT_ENABLED', True))
def register():
    if request.method == 'POST':
        csrf_token = request.form.get('csrf_token')
        if not csrf_token and app.config.get('WTF_CSRF_ENABLED', True):
            abort(400)
        username = request.form.get('username', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        hostel_name = request.form.get('hostel_name', '').strip()
        block = request.form.get('block', '').strip()
        room_number = request.form.get('room_number', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', '').strip()

        if not username or not password or not role or not full_name:
            flash('Please complete the required fields.', 'error')
            return redirect(url_for('register'))

        if role != 'student':
            flash('Staff accounts can only be created by an administrator.', 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists! Please login.', 'error')
            return redirect(url_for('register'))

        new_user = User(
            username=username,
            password=generate_password_hash(password),
            role=role,
            full_name=full_name,
            email=email or None,
            hostel_name=hostel_name or None,
            block=block or None,
            room_number=room_number or None,
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/admin/change-password', methods=['POST'])
@limiter.limit('5 per hour', methods=['POST'])
def change_admin_password():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Only the logged-in administrator can change this password.', 'error')
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    admin = User.query.filter_by(id=session['user_id'], role='admin').first()
    if not admin or not check_password_hash(admin.password, current_password):
        flash('The current admin password is incorrect.', 'error')
        return redirect(url_for('admin_dashboard'))

    if len(new_password) < 8:
        flash('The new password must contain at least 8 characters.', 'error')
        return redirect(url_for('admin_dashboard'))

    if new_password != confirm_password:
        flash('The new passwords do not match.', 'error')
        return redirect(url_for('admin_dashboard'))

    admin.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Admin password changed successfully. You can now sign in.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/create-staff', methods=['POST'])
def create_staff():
    if 'user_id' not in session or session['role'] != 'admin':
        flash('Only an administrator can create staff accounts.', 'error')
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not username or not full_name or not password:
        flash('Complete the required staff account fields.', 'error')
        return redirect(url_for('admin_dashboard'))

    if password != confirm_password:
        flash('Staff passwords do not match.', 'error')
        return redirect(url_for('admin_dashboard'))

    if User.query.filter_by(username=username).first():
        flash('That username is already in use.', 'error')
        return redirect(url_for('admin_dashboard'))

    db.session.add(User(
        username=username,
        password=generate_password_hash(password),
        role='staff',
        full_name=full_name,
        email=email or None,
    ))
    db.session.commit()
    flash('Staff account created successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-staff/<int:staff_id>', methods=['POST'])
def delete_staff(staff_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Only an administrator can delete staff accounts.', 'error')
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    staff = User.query.filter_by(id=staff_id, role='staff').first()
    if not staff:
        flash('Staff account not found.', 'error')
        return redirect(url_for('admin_dashboard'))

    Complaint.query.filter_by(assigned_to=staff.id).update({'assigned_to': None})
    db.session.delete(staff)
    db.session.commit()
    flash('Staff account deleted. Assigned complaints are now unassigned.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Only an administrator can delete student accounts.', 'error')
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    student = User.query.filter_by(id=student_id, role='student').first()
    if not student:
        flash('Student account not found.', 'error')
        return redirect(url_for('admin_dashboard'))

    student_complaints = Complaint.query.filter_by(student_id=student.id).all()
    for complaint in student_complaints:
        Comment.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        AIAnalysis.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        ComplaintSimilarity.query.filter(
            (ComplaintSimilarity.complaint_id == complaint.id)
            | (ComplaintSimilarity.related_complaint_id == complaint.id)
        ).delete(synchronize_session=False)
        db.session.delete(complaint)
    db.session.delete(student)
    db.session.commit()
    flash('Student account deleted along with its complaint history.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    user = db.get_or_404(User, session['user_id'])
    complaints = Complaint.query.filter_by(student_id=user.id).order_by(Complaint.created_at.desc()).all()
    return render_student_portal(user, 'overview', complaints=complaints)


def student_categories():
    return sorted(COLLEGE_CATEGORIES | HOSTEL_CATEGORIES)


def student_filters(user):
    return Complaint.query.filter_by(student_id=user.id)


def student_portal_context(user, active_page, complaints=None, **extra):
    all_complaints = student_filters(user).order_by(Complaint.created_at.desc()).all()
    if complaints is None:
        complaints = all_complaints
    stats = {
        'total': len(all_complaints),
        'pending': sum(item.status == 'Pending' for item in all_complaints),
        'in_progress': sum(item.status in {'Assigned', 'In Progress', 'Escalated'} for item in all_complaints),
        'resolved': sum(item.status in {'Resolved', 'Closed'} for item in all_complaints),
    }
    now_hour = datetime.now().hour
    greeting = 'Good morning' if now_hour < 12 else 'Good afternoon' if now_hour < 18 else 'Good evening'
    return {
        'current_user': user,
        'active_page': active_page,
        'complaints': complaints,
        'recent_complaints': all_complaints[:5],
        'stats': stats,
        'greeting': greeting,
        'announcements': Announcement.query.order_by(Announcement.created_at.desc()).limit(20).all(),
        'category_options': student_categories(),
        'faqs': [
            ('How do I submit a complaint?', 'Open New Complaint, choose College or Hostel, complete the details, and submit the form.'),
            ('How do I track my complaint?', 'Open My Complaints to see its current status, assigned staff, comments, and timeline.'),
            ('What does Pending mean?', 'Your complaint has been received and is waiting for assignment or review.'),
            ('What does In Progress mean?', 'A support team member is actively working on the reported issue.'),
            ('How do I attach evidence?', 'Add a JPG, PNG, GIF, or WEBP image in the New Complaint form. Files are validated securely.'),
            ('What happens after submitting?', 'The complaint receives a ticket number and is sent to the support team for assignment.'),
        ],
        'support_contacts': {
            'email': os.getenv('SUPPORT_EMAIL', 'Not configured'),
            'phone': os.getenv('SUPPORT_PHONE', 'Not configured'),
            'hours': os.getenv('SUPPORT_HOURS', 'Not configured'),
            'emergency': os.getenv('EMERGENCY_CONTACT', 'Use your institution\'s emergency channel.'),
        },
        **extra,
    }


def render_student_portal(user, active_page, complaints=None, **extra):
    return render_template('student_portal.html', **student_portal_context(user, active_page, complaints, **extra))


@app.route('/student/complaints')
def student_complaints():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    user = db.get_or_404(User, session['user_id'])
    filters = {key: request.args.get(key, '').strip() for key in ('q', 'status', 'category', 'location_type', 'date_from', 'date_to', 'sort')}
    query = student_filters(user)
    if filters['q']:
        term = f"%{filters['q']}%"
        query = query.filter((Complaint.title.ilike(term)) | (Complaint.description.ilike(term)) | (Complaint.ticket_number.ilike(term)))
    if filters['status']:
        query = query.filter_by(status=filters['status'])
    if filters['category']:
        query = query.filter_by(category=filters['category'])
    if filters['location_type']:
        query = query.filter_by(location_type=filters['location_type'])
    for key, operator in (('date_from', '>='), ('date_to', '<=')):
        if filters[key]:
            try:
                boundary = datetime.strptime(filters[key], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                if key == 'date_to':
                    boundary += timedelta(days=1)
                    query = query.filter(Complaint.created_at < boundary)
                else:
                    query = query.filter(Complaint.created_at >= boundary)
            except ValueError:
                flash('Dates must use YYYY-MM-DD.', 'error')
    order = Complaint.created_at.asc() if filters['sort'] == 'oldest' else Complaint.created_at.desc()
    complaints = query.order_by(order).all()
    return render_student_portal(user, 'complaints', complaints=complaints, filters=filters, categories=student_categories())


@app.route('/student/notifications')
def student_notifications():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    user = db.get_or_404(User, session['user_id'])
    return render_student_portal(user, 'notifications', complaints=[])


@app.route('/student/announcements')
def student_announcements():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    user = db.get_or_404(User, session['user_id'])
    return render_student_portal(user, 'announcements', complaints=[])


@app.route('/student/<page>', methods=['GET'])
def student_page(page):
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    if page not in {'new-complaint', 'help', 'contact', 'profile', 'settings', 'password'}:
        abort(404)
    user = db.get_or_404(User, session['user_id'])
    return render_student_portal(user, page, complaints=[])


@app.route('/student/profile', methods=['POST'])
def student_profile():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    user = db.get_or_404(User, session['user_id'])
    user.full_name = request.form.get('full_name', '').strip() or user.username
    user.email = request.form.get('email', '').strip() or None
    user.phone = request.form.get('phone', '').strip() or None
    user.department = request.form.get('department', '').strip() or None
    user.year = request.form.get('year', '').strip() or None
    user.section = request.form.get('section', '').strip() or None
    user.hostel_name = request.form.get('hostel_name', '').strip() or None
    db.session.commit()
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('student_page', page='profile'))


@app.route('/student/settings', methods=['POST'])
def student_settings():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    user = db.get_or_404(User, session['user_id'])
    user.notifications_enabled = 'notifications_enabled' in request.form
    user.announcement_notifications_enabled = 'announcement_notifications_enabled' in request.form
    user.theme = request.form.get('theme', 'light') if request.form.get('theme') in {'light', 'dark'} else 'light'
    db.session.commit()
    flash('Settings saved.', 'success')
    return redirect(url_for('student_page', page='settings'))


@app.route('/student/change-password', methods=['POST'])
@limiter.limit('5 per hour', methods=['POST'])
def change_student_password():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Only a logged-in student can change this password.', 'error')
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    student = db.get_or_404(User, session['user_id'])

    if not check_password_hash(student.password, current_password):
        flash('The current password is incorrect.', 'error')
        return redirect(url_for('student_dashboard'))
    if len(new_password) < 8:
        flash('The new password must contain at least 8 characters.', 'error')
        return redirect(url_for('student_dashboard'))
    if new_password != confirm_password:
        flash('The new passwords do not match.', 'error')
        return redirect(url_for('student_dashboard'))

    student.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Password changed successfully.', 'success')
    return redirect(url_for('student_dashboard'))


@app.route('/complaint/<int:complaint_id>')
def complaint_detail(complaint_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    complaint = db.get_or_404(Complaint, complaint_id)
    role = session.get('role')

    if role == 'student':
        if complaint.student_id != session['user_id']:
            abort(403)
        return redirect(url_for('student_complaint_detail', complaint_id=complaint.id))

    if role == 'staff':
        if complaint.assigned_to != session['user_id']:
            abort(403)
        user = db.get_or_404(User, session['user_id'])
        return render_template('staff_dashboard.html', current_user=user, complaints=[complaint])

    if role == 'admin':
        complaints = [complaint]
        staff_list = User.query.filter_by(role='staff').all()
        student_list = User.query.filter_by(role='student').order_by(User.username.asc()).all()
        return render_template(
            'admin_dashboard.html',
            complaints=complaints,
            staff_list=staff_list,
            student_list=student_list,
            insights=summarize(complaints),
            filter_values={},
            filter_categories=db.session.query(Complaint.category).distinct().order_by(Complaint.category).all(),
            filter_blocks=db.session.query(Complaint.block).distinct().order_by(Complaint.block).all(),
            announcements=Announcement.query.order_by(Announcement.created_at.desc()).limit(20).all(),
        )

    abort(403)


@app.route('/student/complaint/<int:complaint_id>')
def student_complaint_detail(complaint_id):
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    complaint = db.get_or_404(Complaint, complaint_id)
    if complaint.student_id != session['user_id']:
        abort(403)
    timeline_labels = [('submitted', 'Submitted'), ('assigned', 'Assigned'), ('in_progress', 'In Progress'), ('resolved', 'Resolved')]
    events = {event.event_type: event for event in complaint.audit_events}
    timeline = []
    for event_type, label in timeline_labels:
        event = events.get(event_type)
        if event:
            timeline.append({'label': label, 'date': event.created_at.strftime('%d %b %Y, %H:%M')})
    return render_template(
        'student_complaint_detail.html',
        current_user=db.get_or_404(User, session['user_id']),
        complaint=complaint,
        timeline=timeline or [{'label': 'Submitted', 'date': complaint.created_at.strftime('%d %b %Y, %H:%M')}],
    )


@app.route('/complaint/<int:complaint_id>/image')
def complaint_image(complaint_id):
    if 'user_id' not in session:
        abort(401)
    complaint = db.get_or_404(Complaint, complaint_id)
    role = session.get('role')
    if role == 'student' and complaint.student_id != session['user_id']:
        abort(403)
    if role == 'staff' and complaint.assigned_to != session['user_id']:
        abort(403)
    if role not in {'student', 'staff', 'admin'}:
        abort(403)
    if not complaint.image_filename:
        abort(404)

    storage_service = get_storage_service()
    if storage_service.provider == 's3':
        return redirect(storage_service.private_url(complaint.image_filename))
    payload = storage_service.read_upload(complaint.image_filename)
    if payload is None:
        abort(404)
    mime_type = mimetypes.guess_type(complaint.image_filename)[0] or 'application/octet-stream'
    return send_file(io.BytesIO(payload), mimetype=mime_type, download_name=complaint.image_filename)


@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    try:
        complaints = filtered_complaints(request.args).all()
    except ValueError:
        flash('Invalid date filter. Use YYYY-MM-DD.', 'error')
        complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    staff_list = User.query.filter_by(role='staff').all()
    student_list = User.query.filter_by(role='student').order_by(User.username.asc()).all()
    return render_template(
        'admin_dashboard.html',
        complaints=complaints,
        staff_list=staff_list,
        student_list=student_list,
        insights=summarize(complaints),
        filter_values=request.args,
        filter_categories=db.session.query(Complaint.category).distinct().order_by(Complaint.category).all(),
        filter_blocks=db.session.query(Complaint.block).distinct().order_by(Complaint.block).all(),
        announcements=Announcement.query.order_by(Announcement.created_at.desc()).limit(20).all(),
    )


@app.route('/admin/announcements', methods=['POST'])
def create_announcement():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    if not title or not description:
        flash('Announcement title and description are required.', 'error')
        return redirect(url_for('admin_dashboard'))
    announcement = Announcement(
        title=title,
        description=description,
        category=request.form.get('category', '').strip() or None,
        importance=request.form.get('importance', 'normal') if request.form.get('importance') in {'normal', 'important'} else 'normal',
        created_by=session['user_id'],
    )
    db.session.add(announcement)
    db.session.commit()
    for student in User.query.filter_by(role='student', announcement_notifications_enabled=True).all():
        create_notification(student.id, 'New campus announcement', announcement.title)
    db.session.commit()
    flash('Announcement published.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/complaints/export.csv')
@roles_required('admin')
def export_complaints_csv():
    try:
        complaints = filtered_complaints(request.args).all()
    except ValueError:
        abort(400, description='Dates must use YYYY-MM-DD.')
    return Response(
        complaints_csv(complaints),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=complaints.csv'},
    )


@app.route('/admin/complaints/export.pdf')
@roles_required('admin')
def export_complaints_pdf():
    try:
        complaints = filtered_complaints(request.args).all()
    except ValueError:
        abort(400, description='Dates must use YYYY-MM-DD.')
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    output = io.BytesIO()
    canvas = Canvas(output, pagesize=A4)
    width, height = A4
    y = height - 48
    canvas.setFont('Helvetica-Bold', 14)
    canvas.drawString(40, y, 'Smart College Complaint Report')
    y -= 28
    canvas.setFont('Helvetica', 9)
    for complaint in complaints:
        line = f'{complaint.ticket_number or "-"} | {complaint.status} | {complaint.priority} | {complaint.category} | {complaint.title}'
        canvas.drawString(40, y, line[:130])
        y -= 14
        if y < 40:
            canvas.showPage()
            canvas.setFont('Helvetica', 9)
            y = height - 40
    canvas.save()
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment; filename=complaints.pdf'},
    )


@app.route('/admin/ai-query', methods=['POST'])
@limiter.limit('30 per minute', methods=['POST'])
def admin_ai_query():
    if 'user_id' not in session or session.get('role') != 'admin':
        return {'error': 'Admin access required.'}, 403
    question = request.form.get('question', '').strip()
    if not question or len(question) > 300:
        return {'error': 'Please enter a question up to 300 characters.'}, 400
    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    fallback_result = answer_question(question, complaints)
    context = {
        'total_complaints': len(complaints),
        'urgent_complaints': sum(item.priority == 'Urgent' for item in complaints),
        'open_complaints': sum(item.status not in {'Resolved', 'Closed'} for item in complaints),
        'resolved_complaints': sum(item.status == 'Resolved' for item in complaints),
        'categories': dict(Counter(item.category for item in complaints)),
        'areas': dict(Counter(item.campus_area for item in complaints)),
    }
    fallback_result['answer'] = ai_service.answer_admin_question(
        question, context, fallback_result['answer']
    )
    return fallback_result


@app.route('/api/student/ai', methods=['POST'])
@limiter.limit('30 per minute', methods=['POST'])
def student_ai_query():
    if 'user_id' not in session or session.get('role') != 'student':
        return {'error': 'Student access required.'}, 403
    question = request.form.get('question', '').strip()
    if not question or len(question) > 300:
        return {'error': 'Please enter a question up to 300 characters.'}, 400
    complaints = Complaint.query.filter_by(student_id=session['user_id']).order_by(Complaint.created_at.desc()).all()
    result = answer_question(question, complaints)
    result['answer'] = ai_service.answer_admin_question(
        question,
        {
            'total_complaints': len(complaints),
            'open_complaints': sum(item.status not in {'Resolved', 'Closed'} for item in complaints),
            'resolved_complaints': sum(item.status in {'Resolved', 'Closed'} for item in complaints),
        },
        result['answer'],
    )
    return result


@app.route('/admin/ai/status')
def admin_ai_status():
    if 'user_id' not in session or session.get('role') != 'admin':
        return {'error': 'Admin access required.'}, 403
    return ai_service.status_details()


@app.route('/staff_dashboard')
def staff_dashboard():
    if 'user_id' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    complaints = Complaint.query.filter_by(assigned_to=session['user_id']).order_by(Complaint.created_at.desc()).all()
    current_user = db.get_or_404(User, session['user_id'])
    return render_template('staff_dashboard.html', complaints=complaints, current_user=current_user)


@app.route('/staff/change-password', methods=['POST'])
@limiter.limit('5 per hour', methods=['POST'])
def change_staff_password():
    if 'user_id' not in session or session.get('role') != 'staff':
        flash('Only a logged-in staff member can change this password.', 'error')
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    staff = db.get_or_404(User, session['user_id'])

    if not check_password_hash(staff.password, current_password):
        flash('The current password is incorrect.', 'error')
        return redirect(url_for('staff_dashboard'))
    if len(new_password) < 8:
        flash('The new password must contain at least 8 characters.', 'error')
        return redirect(url_for('staff_dashboard'))
    if new_password != confirm_password:
        flash('The new passwords do not match.', 'error')
        return redirect(url_for('staff_dashboard'))

    staff.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Password changed successfully.', 'success')
    return redirect(url_for('staff_dashboard'))


@app.route('/submit_complaint', methods=['POST'])
@limiter.limit('10 per hour', methods=['POST'])
def submit_complaint():
    if 'user_id' not in session or session['role'] != 'student':
        flash('Please login first.', 'error')
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    title = request.form.get('title', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    location_type = request.form.get('location_type', 'Hostel').strip()
    campus_area = request.form.get('campus_area', 'Main Hostel').strip()
    hostel_name = request.form.get('hostel_name', 'Main Hostel').strip()
    block = request.form.get('block', 'A').strip()
    room_number = request.form.get('room_number', '').strip()
    priority = request.form.get('priority', 'Medium').strip()

    valid_categories = COLLEGE_CATEGORIES if location_type == 'College' else HOSTEL_CATEGORIES

    if location_type not in {'College', 'Hostel'}:
        flash('Please select either a college or hostel location.', 'error')
        return redirect(url_for('student_dashboard'))

    if not title or not category or not description or not campus_area:
        flash('Please complete the complaint details and location.', 'error')
        return redirect(url_for('student_dashboard'))

    if category not in valid_categories:
        flash('Please select a category that matches the chosen location.', 'error')
        return redirect(url_for('student_dashboard'))

    if priority not in VALID_PRIORITIES:
        flash('Please select a valid priority.', 'error')
        return redirect(url_for('student_dashboard'))

    uploaded_file = request.files.get('image')
    image_filename = None
    if uploaded_file and uploaded_file.filename:
        image_filename = store_complaint_image(uploaded_file)
        if not image_filename:
            flash('Please upload a valid JPG, PNG, GIF, or WEBP image.', 'error')
            return redirect(url_for('student_dashboard'))

    complaint = Complaint(
        title=title,
        description=description,
        category=category,
        location_type=location_type or 'Hostel',
        campus_area=campus_area or 'Main Hostel',
        hostel_name=hostel_name or 'Main Hostel',
        block=block or 'A',
        room_number=room_number,
        priority=priority or 'Medium',
        student_id=session['user_id'],
        image_filename=image_filename,
        status='Pending'
    )
    db.session.add(complaint)
    db.session.commit()
    complaint.ticket_number = ticket_number_for(complaint)
    record_audit_event(complaint, 'submitted', 'Complaint submitted by student.', session['user_id'])
    notify_admins(
        'New complaint received',
        f'{complaint.ticket_number}: {complaint.title}',
        complaint,
    )
    db.session.commit()
    
    # Run AI analysis in background, but execute synchronously under test mode so assertions see the result immediately.
    def run_ai_analysis(app_instance, comp_id, c_title, c_desc, c_loc, c_area):
        with app_instance.app_context():
            comp = db.session.get(Complaint, comp_id)
            if not comp:
                return

            combined_text = f"{c_title}: {c_desc}"
            valid_cats = COLLEGE_CATEGORIES if c_loc == 'College' else HOSTEL_CATEGORIES

            analysis = None
            if ai_service.enabled:
                analysis = ai_service.analyze_complaint(c_title, c_desc, c_loc, c_area)
                if analysis:
                    comp.ai_category = analysis.category
                    comp.ai_department = analysis.department
                    comp.ai_priority = analysis.priority
                    comp.ai_confidence = analysis.confidence
                    comp.ai_reasons = ' | '.join(analysis.reasons) if analysis.reasons else None
                    comp.ai_safety_critical = bool(analysis.safety_critical)
                    db.session.add(AIAnalysis(
                        complaint_id=comp.id,
                        analysis_type='complaint_analysis',
                        input_hash=hashlib.sha256(combined_text.encode()).hexdigest(),
                        prediction=json.dumps(analysis.as_dict()),
                        confidence=analysis.confidence,
                        reason=' | '.join(analysis.reasons) if analysis.reasons else None,
                        provider='local',
                        model_name='local-classifier'
                    ))

            if not analysis:
                from services.gemini_service import gemini_service
                if not gemini_service.is_available():
                    db.session.commit()
                    return

                analysis = gemini_service.analyze_category_and_priority(combined_text, c_loc, valid_cats)
                if analysis:
                    comp.ai_category = analysis.get('category')
                    comp.ai_department = None
                    comp.ai_priority = analysis.get('priority')
                    comp.ai_confidence = analysis.get('confidence')
                    comp.ai_reasons = analysis.get('reason')
                    comp.ai_safety_critical = False
                    db.session.add(AIAnalysis(
                        complaint_id=comp.id,
                        analysis_type='complaint_analysis',
                        input_hash=hashlib.sha256(combined_text.encode()).hexdigest(),
                        prediction=json.dumps(analysis),
                        confidence=analysis.get('confidence'),
                        reason=analysis.get('reason'),
                        provider='gemini',
                        model_name='gemini-2.5-flash'
                    ))

            recent_complaints = Complaint.query.filter(
                Complaint.id != comp.id,
                Complaint.status.in_(['Pending', 'In Progress', 'Assigned'])
            ).order_by(Complaint.created_at.desc()).limit(20).all()

            if recent_complaints and gemini_service.is_available() if 'gemini_service' in locals() else False:
                existing = [{'id': c.id, 'text': f"{c.title} {c.description}"} for c in recent_complaints]
                duplicate_info = gemini_service.check_duplicate(combined_text, existing)
                if duplicate_info and duplicate_info.get('possible_duplicate') and duplicate_info.get('similar_complaint_id'):
                    db.session.add(ComplaintSimilarity(
                        complaint_id=comp.id,
                        related_complaint_id=duplicate_info['similar_complaint_id'],
                        similarity_score=0.9,
                        relationship='duplicate_suspect'
                    ))

            db.session.commit()

    if app.config.get('TESTING'):
        run_ai_analysis(app, complaint.id, title, description, location_type, campus_area)
    else:
        threading.Thread(
            target=run_ai_analysis,
            args=(app, complaint.id, title, description, location_type, campus_area),
            daemon=True
        ).start()

    flash(f'Complaint submitted successfully. Ticket: {complaint.ticket_number}', 'success')
    return redirect(url_for('student_dashboard'))


@app.route('/assign/<int:complaint_id>', methods=['POST'])
def assign_complaint(complaint_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    complaint = db.get_or_404(Complaint, complaint_id)
    staff_id = request.form.get('staff_id')

    if not staff_id:
        flash('Please select a staff member to assign.', 'error')
        return redirect(url_for('admin_dashboard'))

    staff = User.query.filter_by(id=staff_id, role='staff').first()
    if not staff:
        flash('Please select a valid staff account.', 'error')
        return redirect(url_for('admin_dashboard'))

    previous_staff_id = complaint.assigned_to
    complaint.assigned_to = staff.id
    complaint.status = 'Assigned'
    record_audit_event(complaint, 'assigned', f'Assigned to {staff.username}.', session['user_id'])
    create_notification(
        staff.id,
        'Complaint assigned to you',
        f'{complaint.ticket_number}: {complaint.title}',
        complaint,
    )
    create_notification(
        complaint.student_id,
        'Complaint assigned',
        f'{complaint.ticket_number} is assigned to {staff.full_name or staff.username}.',
        complaint,
    )
    if previous_staff_id and previous_staff_id != staff.id:
        create_notification(
            previous_staff_id,
            'Complaint reassigned',
            f'{complaint.ticket_number} has been reassigned.',
            complaint,
        )
    db.session.commit()

    flash('Complaint assigned successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/ai/analyze/<int:complaint_id>', methods=['POST'])
@limiter.limit('10 per minute', methods=['POST'])
def api_ai_analyze(complaint_id):
    if 'user_id' not in session or session.get('role') not in ('staff', 'admin'):
        return {'error': 'Unauthorized'}, 403
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        return {'error': 'Invalid or missing CSRF token.'}, 400
        
    complaint = db.get_or_404(Complaint, complaint_id)
    from services.gemini_service import gemini_service
    
    if not gemini_service.is_available():
        return {'error': 'AI service is currently unavailable.'}, 503
        
    valid_cats = COLLEGE_CATEGORIES if complaint.location_type == 'College' else HOSTEL_CATEGORIES
    text = f"{complaint.title}: {complaint.description}"
    
    result = gemini_service.generate_full_analysis(text, complaint.location_type, valid_cats)
    if not result:
        return {'error': 'AI generation failed. Please try again.'}, 500
        
    return result

@app.route('/update_status/<int:complaint_id>', methods=['POST'])
def update_status(complaint_id):
    if 'user_id' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)

    complaint = db.get_or_404(Complaint, complaint_id)
    if complaint.assigned_to != session['user_id']:
        flash('You can only update complaints assigned to you.', 'error')
        return redirect(url_for('staff_dashboard'))

    new_status = request.form.get('status', complaint.status)
    if new_status not in {'Pending', 'In Progress', 'Resolved'}:
        flash('Please select a valid complaint status.', 'error')
        return redirect(url_for('staff_dashboard'))

    complaint.status = new_status
    record_audit_event(complaint, 'in_progress' if new_status == 'In Progress' else new_status.lower(), f'Status changed to {new_status}.', session['user_id'])
    create_notification(
        complaint.student_id,
        'Complaint status updated',
        f'{complaint.ticket_number} is now {new_status}.',
        complaint,
    )
    notify_admins(
        'Complaint status updated',
        f'{complaint.ticket_number} is now {new_status}.',
        complaint,
    )
    db.session.commit()
    emit_complaint_update('complaint_updated', {
        'complaint_id': complaint.id,
        'status': complaint.status,
        'ticket_number': complaint.ticket_number,
    }, [complaint.student_id])

    flash('Complaint status updated successfully.', 'success')
    return redirect(url_for('staff_dashboard'))


@app.route('/add_comment/<int:complaint_id>', methods=['POST'])
@limiter.limit('20 per hour', methods=['POST'])
def add_comment(complaint_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)
        
    complaint = db.get_or_404(Complaint, complaint_id)
    text = request.form.get('text', '').strip()
    
    if not text:
        flash('Comment cannot be empty.', 'error')
        return redirect(request.referrer or url_for('login'))
        
    comment = Comment(text=text, complaint_id=complaint.id, sender_id=session['user_id'])
    db.session.add(comment)
    
    # Notify appropriate parties
    if session['role'] == 'student':
        if complaint.assigned_to:
            create_notification(complaint.assigned_to, 'New comment on complaint', f'Student commented on {complaint.ticket_number}', complaint)
    elif session['role'] == 'staff' or session['role'] == 'admin':
        create_notification(complaint.student_id, 'New comment on your complaint', f'Staff/Admin commented on {complaint.ticket_number}', complaint)
        
    db.session.commit()
    flash('Comment added successfully.', 'success')
    return redirect(request.referrer or url_for('login'))


@app.route('/close_complaint/<int:complaint_id>', methods=['POST'])
def close_complaint(complaint_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)
        
    complaint = db.get_or_404(Complaint, complaint_id)
    if complaint.student_id != session['user_id']:
        flash('You can only close your own complaints.', 'error')
        return redirect(url_for('student_dashboard'))
        
    if complaint.status != 'Resolved':
        flash('You can only close complaints that have been marked Resolved.', 'error')
        return redirect(url_for('student_dashboard'))
        
    complaint.status = 'Closed'
    record_audit_event(complaint, 'closed', 'Complaint closed by student.', session['user_id'])
    if complaint.assigned_to:
        create_notification(complaint.assigned_to, 'Complaint closed', f'Student closed {complaint.ticket_number}', complaint)
    notify_admins('Complaint closed', f'Student closed {complaint.ticket_number}', complaint)
    db.session.commit()
    
    flash('Complaint closed successfully.', 'success')
    return redirect(url_for('student_dashboard'))



@app.route('/notifications/read/<int:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not request.form.get('csrf_token') and app.config.get('WTF_CSRF_ENABLED', True):
        abort(400)
    notification = Notification.query.filter_by(
        id=notification_id,
        recipient_id=session['user_id'],
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(request.referrer or url_for('login'))


@app.route('/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    Notification.query.filter_by(
        recipient_id=session['user_id'], is_read=False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return redirect(request.referrer or url_for('login'))


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/health')
def health():
    return {'status': 'healthy'}, 200


if __name__ == '__main__':
    if os.getenv('SLA_SCHEDULER_ENABLED', 'true').lower() == 'true':
        start_sla_scheduler()
    socketio.run(app, debug=True)

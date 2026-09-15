import os
import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from PIL import Image, UnidentifiedImageError
from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.datastructures import FileStorage

from ai import AIService
from ai.query import answer_question
from database import AIAnalysis, Complaint, Comment, ComplaintSimilarity, Notification, User, db
from ai.summarizer import summarize

load_dotenv()

app = Flask(__name__)

app_environment = os.getenv('APP_ENV', 'development').lower()
secret_key = os.getenv('SECRET_KEY')
if app_environment == 'production' and not secret_key:
    raise RuntimeError('SECRET_KEY must be configured in production.')
app.config['SECRET_KEY'] = secret_key or 'development-only-change-this-secret-key'
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

app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['S3_BUCKET'] = os.getenv('S3_BUCKET')
app.config['S3_REGION'] = os.getenv('S3_REGION', 'us-east-1')
app.config['S3_PREFIX'] = os.getenv('S3_PREFIX', 'complaint-images')
ai_service = AIService()

csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
)

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


def utc_now():
    return datetime.now(timezone.utc)


def ensure_default_admin():
    admin = User.query.filter_by(username='admin').first()
    if admin is None:
        db.session.add(User(
            username='admin',
            password=generate_password_hash('admin123'),
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

    demo_staff = User.query.filter_by(username='staff').first()
    if demo_staff is None:
        db.session.add(User(
            username='staff',
            password=generate_password_hash('staff123'),
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
            password=generate_password_hash('student123'),
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


def store_complaint_image(uploaded_file: FileStorage):
    """Validate image bytes and store them locally or in S3 under a UUID key."""
    try:
        uploaded_file.stream.seek(0)
        with Image.open(uploaded_file.stream) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError):
        return None

    extension_by_format = {'JPEG': 'jpg', 'PNG': 'png', 'GIF': 'gif', 'WEBP': 'webp'}
    extension = extension_by_format.get(image_format)
    if not extension:
        return None

    filename = f'{uuid.uuid4().hex}.{extension}'
    uploaded_file.stream.seek(0)
    if app.config['S3_BUCKET']:
        import boto3

        key = f"{app.config['S3_PREFIX'].strip('/')}/{filename}"
        boto3.client('s3', region_name=app.config['S3_REGION']).upload_fileobj(
            uploaded_file.stream,
            app.config['S3_BUCKET'],
            key,
            ExtraArgs={'ContentType': f'image/{"jpeg" if extension == "jpg" else extension}'},
        )
        return key

    uploaded_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


def complaint_image_url(filename):
    if app.config['S3_BUCKET']:
        import boto3

        return boto3.client('s3', region_name=app.config['S3_REGION']).generate_presigned_url(
            'get_object',
            Params={'Bucket': app.config['S3_BUCKET'], 'Key': filename},
            ExpiresIn=900,
        )
    return url_for('static', filename=f'uploads/{filename}')


@app.context_processor
def inject_upload_helpers():
    return {'complaint_image_url': complaint_image_url}


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


def create_notification(recipient_id, title, message, complaint=None):
    db.session.add(Notification(
        recipient_id=recipient_id,
        complaint_id=complaint.id if complaint else None,
        title=title,
        message=message,
    ))


def notify_admins(title, message, complaint):
    for admin in User.query.filter_by(role='admin').all():
        create_notification(admin.id, title, message, complaint)


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
        if user.password == password and not user.password.startswith('pbkdf2:'):
            user.password = generate_password_hash(password)
        db.session.commit()
        return True

    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= LOGIN_MAX_ATTEMPTS:
        user.locked_until = now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
    db.session.commit()
    return False

db.init_app(app)


def migrate_sqlite_schema():
    """Add columns introduced after the initial SQLite database was created."""
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


@app.route('/', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def login():
    if request.method == 'POST':
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
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def admin_login():
    if request.method == 'POST':
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
@limiter.limit('5 per minute', methods=['POST'])
def register():
    if request.method == 'POST':
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
    return render_template('student_dashboard.html', current_user=user, complaints=complaints)


@app.route('/student/change-password', methods=['POST'])
@limiter.limit('5 per hour', methods=['POST'])
def change_student_password():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Only a logged-in student can change this password.', 'error')
        return redirect(url_for('login'))

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


@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    staff_list = User.query.filter_by(role='staff').all()
    student_list = User.query.filter_by(role='student').order_by(User.username.asc()).all()
    return render_template(
        'admin_dashboard.html',
        complaints=complaints,
        staff_list=staff_list,
        student_list=student_list,
        insights=summarize(complaints),
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
    notify_admins(
        'New complaint received',
        f'{complaint.ticket_number}: {complaint.title}',
        complaint,
    )
    analysis = ai_service.analyze_complaint(title, description, location_type, campus_area)
    if analysis:
        complaint.ai_category = analysis.category
        complaint.ai_department = analysis.department
        complaint.ai_priority = analysis.priority
        complaint.ai_confidence = analysis.confidence
        complaint.ai_reasons = json.dumps(analysis.reasons)
        complaint.ai_safety_critical = analysis.safety_critical
        input_hash = hashlib.sha256(
            f'{title}|{description}|{location_type}'.encode()
        ).hexdigest()
        db.session.add(AIAnalysis(
            complaint_id=complaint.id,
            analysis_type='complaint_analysis',
            input_hash=input_hash,
            prediction=json.dumps(analysis.as_dict()),
            confidence=analysis.confidence,
            reason='; '.join(analysis.reasons),
        ))
        related = ai_service.related_complaints(
            title,
            description,
            Complaint.query.filter(Complaint.id != complaint.id).all(),
        )
        for item in related:
            db.session.add(ComplaintSimilarity(
                complaint_id=complaint.id,
                related_complaint_id=item.complaint_id,
                similarity_score=item.similarity,
                relationship='related',
            ))
    db.session.commit()

    flash(f'Complaint submitted successfully. Ticket: {complaint.ticket_number}', 'success')
    return redirect(url_for('student_dashboard'))


@app.route('/assign/<int:complaint_id>', methods=['POST'])
def assign_complaint(complaint_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

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


@app.route('/update_status/<int:complaint_id>', methods=['POST'])
def update_status(complaint_id):
    if 'user_id' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    complaint = db.get_or_404(Complaint, complaint_id)
    if complaint.assigned_to != session['user_id']:
        flash('You can only update complaints assigned to you.', 'error')
        return redirect(url_for('staff_dashboard'))

    new_status = request.form.get('status', complaint.status)
    if new_status not in {'Pending', 'In Progress', 'Resolved'}:
        flash('Please select a valid complaint status.', 'error')
        return redirect(url_for('staff_dashboard'))

    complaint.status = new_status
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

    flash('Complaint status updated successfully.', 'success')
    return redirect(url_for('staff_dashboard'))


@app.route('/notifications/read/<int:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
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


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/health')
def health():
    return {'status': 'healthy'}, 200


if __name__ == '__main__':
    app.run(debug=True)

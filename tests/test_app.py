import io

import pytest
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash

from app import app, ensure_default_admin
from database import Complaint, Notification, User, db


@pytest.fixture()
def client():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_client() as test_client:
        yield test_client


def make_image():
    image = Image.new('RGB', (2, 2), 'red')
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    stream.seek(0)
    return stream


def create_user(username, role, password='test-password'):
    user = User(
        username=username,
        password=generate_password_hash(password),
        role=role,
        full_name=username.title(),
    )
    db.session.add(user)
    db.session.commit()
    return user


def set_session(client, user):
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role


def test_post_without_csrf_is_rejected():
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        response = app.test_client().post('/', data={'username': 'admin', 'password': 'admin123'})
        assert response.status_code == 400
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_login_and_dashboard_routes(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'href="/admin/login"' in response.data
    assert client.get('/register').status_code == 200
    assert client.get('/health').json == {'status': 'healthy'}


def test_hostel_category_values_match_server_validation(client):
    with app.app_context():
        student = create_user('category-student', 'student')
        set_session(client, student)
        response = client.get('/student_dashboard')
        assert response.status_code == 200
        assert b'class="notification-toggle"' in response.data
        assert b'id="studentNotifications" hidden' in response.data
        assert b'value="Hostel Cleaning"' in response.data
        assert b'value="Hostel Internet"' in response.data
        db.session.delete(student)
        db.session.commit()


def test_admin_login_route_and_redirect(client):
    response = client.get('/admin/login')
    assert response.status_code == 200

    login_response = client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert login_response.status_code == 302
    assert login_response.headers['Location'].endswith('/admin_dashboard')


def test_default_admin_password_is_not_reset_on_startup():
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        original_password = admin.password
        admin.password = generate_password_hash('changed-admin-password')
        db.session.commit()

        try:
            ensure_default_admin()
            db.session.refresh(admin)
            assert check_password_hash(admin.password, 'changed-admin-password')
        finally:
            admin.password = original_password
            db.session.commit()


def test_login_locks_account_after_repeated_failures(client):
    with app.app_context():
        user = create_user('lockout-student', 'student', 'correct-password')

        for _ in range(5):
            response = client.post('/', data={'username': user.username, 'password': 'wrong-password'})
            assert response.status_code == 302

        db.session.refresh(user)
        assert user.failed_login_attempts == 5
        assert user.locked_until is not None

        response = client.post('/', data={'username': user.username, 'password': 'correct-password'})
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/')

        db.session.delete(user)
        db.session.commit()


def test_invalid_image_is_rejected(client):
    with app.app_context():
        student = create_user('invalid-image-student', 'student')
        set_session(client, student)

        response = client.post(
            '/submit_complaint',
            data={
                'title': 'Invalid upload',
                'description': 'Not an image',
                'location_type': 'College',
                'campus_area': 'Library',
                'category': 'Library',
                'priority': 'Medium',
                'image': (io.BytesIO(b'not-an-image'), 'photo.png'),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert Complaint.query.filter_by(title='Invalid upload').count() == 0
        db.session.delete(student)
        db.session.commit()


def test_valid_image_uses_uuid_filename(client):
    with app.app_context():
        student = create_user('valid-image-student', 'student')
        set_session(client, student)

        response = client.post(
            '/submit_complaint',
            data={
                'title': 'Valid upload',
                'description': 'Real image',
                'location_type': 'College',
                'campus_area': 'Library',
                'category': 'Library',
                'priority': 'Medium',
                'image': (make_image(), 'student-supplied.exe'),
            },
            follow_redirects=False,
        )

        complaint = Complaint.query.filter_by(title='Valid upload').first()
        assert response.status_code == 302
        assert complaint is not None
        assert complaint.image_filename.endswith('.png')
        assert 'student-supplied' not in complaint.image_filename
        db.session.delete(complaint)
        db.session.delete(student)
        db.session.commit()


def test_assignment_rejects_non_staff_user(client):
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        student = create_user('assignment-student', 'student')
        complaint = Complaint(
            title='Assignment validation',
            description='Assignment validation',
            category='Library',
            location_type='College',
            campus_area='Library',
            student_id=student.id,
        )
        db.session.add(complaint)
        db.session.commit()
        set_session(client, admin)

        response = client.post(f'/assign/{complaint.id}', data={'staff_id': student.id})
        db.session.refresh(complaint)
        assert response.status_code == 302
        assert complaint.assigned_to is None
        db.session.delete(complaint)
        db.session.delete(student)
        db.session.commit()


def test_ticket_and_notifications_follow_complaint_lifecycle(client):
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        student = create_user('notification-student', 'student')
        staff = create_user('notification-staff', 'staff')
        set_session(client, student)

        response = client.post('/submit_complaint', data={
            'title': 'Water leak',
            'description': 'Leak near the room entrance.',
            'location_type': 'Hostel',
            'campus_area': 'Main Hostel',
            'hostel_name': 'Main Hostel',
            'block': 'A',
            'room_number': '101',
            'category': 'Water Supply',
            'priority': 'High',
        })
        assert response.status_code == 302
        complaint = Complaint.query.filter_by(title='Water leak').first()
        assert complaint is not None
        assert complaint.ticket_number.startswith('SCCS-')
        assert Notification.query.filter_by(recipient_id=admin.id, complaint_id=complaint.id).count() == 1

        set_session(client, admin)
        client.post(f'/assign/{complaint.id}', data={'staff_id': staff.id})
        assert Notification.query.filter_by(recipient_id=staff.id, complaint_id=complaint.id).count() == 1
        assert Notification.query.filter_by(recipient_id=student.id, complaint_id=complaint.id).count() == 1

        set_session(client, staff)
        client.post(f'/update_status/{complaint.id}', data={'status': 'In Progress'})
        status_notifications = Notification.query.filter_by(
            recipient_id=student.id, complaint_id=complaint.id
        ).all()
        assert len(status_notifications) == 2
        assert any('In Progress' in notification.message for notification in status_notifications)

        Notification.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        db.session.delete(complaint)
        db.session.delete(staff)
        db.session.delete(student)
        db.session.commit()

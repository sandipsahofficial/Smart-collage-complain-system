import io

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from app import app
from database import Complaint, User, db


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
    assert client.get('/').status_code == 200
    assert client.get('/register').status_code == 200


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

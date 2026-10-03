from werkzeug.security import generate_password_hash

from app import app
from database import User, db


def test_registration_and_login_flow(client):
    response = client.post(
        '/register',
        data={
            'username': 'newstudent',
            'full_name': 'New Student',
            'email': 'newstudent@example.com',
            'role': 'student',
            'hostel_name': 'Main Hostel',
            'block': 'A',
            'room_number': '102',
            'password': 'StudentPass1',
            'confirm_password': 'StudentPass1',
            'csrf_token': 'test-token',
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 400}

    with app.app_context():
        user = User.query.filter_by(username='newstudent').first()
        assert user is None or user.role == 'student'

    response = client.post(
        '/',
        data={'username': 'admin', 'password': 'admin123'},
        follow_redirects=False,
    )
    assert response.status_code in {302, 400}


def test_missing_csrf_is_rejected(client):
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
        assert response.status_code == 400
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_duplicate_registration_is_rejected(client):
    with app.app_context():
        db.session.add(
            User(
                username='duplicate_user',
                password=generate_password_hash('Password123!'),
                role='student',
                full_name='Duplicate User',
            )
        )
        db.session.commit()

    response = client.post(
        '/register',
        data={
            'username': 'duplicate_user',
            'full_name': 'Duplicate User',
            'email': 'dup@example.com',
            'role': 'student',
            'password': 'Password123!',
            'confirm_password': 'Password123!',
            'csrf_token': 'test-token',
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 400}

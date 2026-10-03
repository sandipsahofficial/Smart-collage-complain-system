import io
import re
from pathlib import Path

from PIL import Image

from app import app
from database import Complaint, db


def csrf_token(client):
    response = client.get('/login')
    return re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()


def make_jpeg():
    stream = io.BytesIO()
    Image.new('RGB', (3, 3), 'green').save(stream, format='JPEG')
    stream.seek(0)
    return stream


def test_csrf_protects_logout_and_accepts_generated_token(client, student_user):
    with client.session_transaction() as session:
        session['user_id'] = student_user.id
        session['role'] = 'student'

    app.config['WTF_CSRF_ENABLED'] = True
    try:
        assert client.post('/logout').status_code == 400
        assert client.post('/logout', data={'csrf_token': csrf_token(client)}).status_code == 302
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_upload_uses_signature_not_client_extension(client, student_user):
    with client.session_transaction() as session:
        session['user_id'] = student_user.id
        session['role'] = 'student'

    response = client.post('/submit_complaint', data={
        'title': 'JPEG with misleading extension',
        'description': 'The content is a real JPEG.',
        'location_type': 'College',
        'campus_area': 'Library',
        'category': 'Library',
        'priority': 'Medium',
        'image': (make_jpeg(), 'not-a-jpeg.png'),
    })

    complaint = Complaint.query.filter_by(title='JPEG with misleading extension').first()
    assert response.status_code == 302
    assert complaint is not None
    assert re.fullmatch(r'[0-9a-f]{32}\.jpg', complaint.image_filename)


def test_complaint_image_requires_authorization(client, student_user):
    image_name = 'security-test.png'
    image_path = Path(app.config['UPLOAD_FOLDER']) / image_name
    image_path.write_bytes(b'\x89PNG\r\n\x1a\n')
    complaint = Complaint(
        title='Private evidence', description='Private evidence', category='Library',
        location_type='College', campus_area='Library', student_id=student_user.id,
        image_filename=image_name,
    )
    db.session.add(complaint)
    db.session.commit()

    try:
        with client.session_transaction() as session:
            session['user_id'] = student_user.id
            session['role'] = 'student'
        assert client.get(f'/complaint/{complaint.id}/image').status_code == 200

        with client.session_transaction() as session:
            session['user_id'] = 999999
            session['role'] = 'student'
        assert client.get(f'/complaint/{complaint.id}/image').status_code == 403
    finally:
        image_path.unlink(missing_ok=True)
        db.session.delete(complaint)
        db.session.commit()
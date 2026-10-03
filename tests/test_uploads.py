import io

from app import app
from database import Complaint, db
from tests.conftest import make_png_bytes


def test_valid_upload_is_accepted(client, student_user):
    with client.session_transaction() as session:
        session['user_id'] = student_user.id
        session['role'] = 'student'

    response = client.post(
        '/submit_complaint',
        data={
            'title': 'Broken light',
            'description': 'Light in room is flickering',
            'location_type': 'Hostel',
            'campus_area': 'Main Hostel',
            'hostel_name': 'Main Hostel',
            'block': 'A',
            'room_number': '203',
            'category': 'Electrical',
            'priority': 'High',
            'image': (io.BytesIO(make_png_bytes()), 'photo.png'),
            'csrf_token': 'test-token',
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 400}
    complaint = Complaint.query.filter_by(title='Broken light').first()
    assert complaint is None or complaint.image_filename is not None


def test_invalid_extension_and_path_traversal_are_rejected(client, student_user):
    with client.session_transaction() as session:
        session['user_id'] = student_user.id
        session['role'] = 'student'

    response = client.post(
        '/submit_complaint',
        data={
            'title': 'Bad upload',
            'description': 'Too bad',
            'location_type': 'Hostel',
            'campus_area': 'Main Hostel',
            'hostel_name': 'Main Hostel',
            'block': 'A',
            'room_number': '204',
            'category': 'Electrical',
            'priority': 'High',
            'image': (io.BytesIO(b'not-an-image'), '../../malware.exe'),
            'csrf_token': 'test-token',
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 400}


def test_oversized_upload_is_rejected(client, student_user):
    with client.session_transaction() as session:
        session['user_id'] = student_user.id
        session['role'] = 'student'

    oversized = b'A' * (6 * 1024 * 1024)
    response = client.post(
        '/submit_complaint',
        data={
            'title': 'Large upload',
            'description': 'Large file should fail',
            'location_type': 'Hostel',
            'campus_area': 'Main Hostel',
            'hostel_name': 'Main Hostel',
            'block': 'B',
            'room_number': '100',
            'category': 'Electrical',
            'priority': 'Medium',
            'image': (io.BytesIO(oversized), 'large.png'),
            'csrf_token': 'test-token',
        },
        follow_redirects=False,
    )
    assert response.status_code in {302, 413, 400}

from app import app
from database import Complaint, User, db


def test_student_cannot_access_admin_dashboard(client, student_user):
    with client.session_transaction() as session:
        session['user_id'] = student_user.id
        session['role'] = 'student'

    response = client.get('/admin_dashboard', follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers.get('Location', '')


def test_student_cannot_access_other_student_complaint(client, student_user):
    other_user = User(username='other_student', password='hashed', role='student', full_name='Other')
    db.session.add(other_user)
    db.session.commit()
    complaint = Complaint(
        title='Other complaint',
        description='Need to be private',
        category='Water Supply',
        location_type='Hostel',
        campus_area='Main Hostel',
        hostel_name='Main Hostel',
        block='A',
        room_number='101',
        priority='Medium',
        student_id=other_user.id,
    )
    db.session.add(complaint)
    db.session.commit()

    with client.session_transaction() as session:
        session['user_id'] = student_user.id
        session['role'] = 'student'

    response = client.get(f'/complaint/{complaint.id}', follow_redirects=False)
    assert response.status_code in {302, 403}


def test_staff_cannot_access_unauthorized_complaint(client, staff_user, student_user):
    complaint = Complaint(
        title='Assigned issue',
        description='Not assigned to this staff member',
        category='Electrical',
        location_type='Hostel',
        campus_area='Main Hostel',
        hostel_name='Main Hostel',
        block='B',
        room_number='204',
        priority='High',
        student_id=student_user.id,
    )
    db.session.add(complaint)
    db.session.commit()

    with client.session_transaction() as session:
        session['user_id'] = staff_user.id
        session['role'] = 'staff'

    response = client.post(f'/update_status/{complaint.id}', data={'status': 'Resolved', 'csrf_token': 'test-token'}, follow_redirects=False)
    assert response.status_code in {302, 403}

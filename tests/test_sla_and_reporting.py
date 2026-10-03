from datetime import datetime, timedelta, timezone

from app import app, socketio
from database import AuditEvent, Complaint, User, db
from services.sla import evaluate_sla


def set_session(client, user):
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role


def test_high_priority_complaint_is_escalated_once(client, student_user):
    created_at = datetime.now(timezone.utc) - timedelta(hours=13)
    complaint = Complaint(
        title='Overdue high priority complaint',
        description='Needs attention',
        category='Electrical',
        location_type='Hostel',
        campus_area='Main Hostel',
        student_id=student_user.id,
        priority='High',
        created_at=created_at,
    )
    db.session.add(complaint)
    db.session.commit()

    escalated = evaluate_sla(now=datetime.now(timezone.utc))
    assert [item.id for item in escalated] == [complaint.id]
    assert complaint.status == 'Escalated'
    assert complaint.escalated_at is not None
    assert AuditEvent.query.filter_by(complaint_id=complaint.id, event_type='sla_escalated').count() == 1
    assert evaluate_sla(now=datetime.now(timezone.utc)) == []


def test_admin_can_filter_and_export_but_student_cannot(client, student_user):
    complaint = Complaint(
        title='Filtered complaint',
        description='Reportable issue',
        category='Electrical',
        location_type='Hostel',
        campus_area='Main Hostel',
        block='B',
        student_id=student_user.id,
        priority='High',
        status='Escalated',
        ticket_number='SCCS-REPORT-1',
    )
    db.session.add(complaint)
    db.session.commit()

    set_session(client, student_user)
    assert client.get('/admin/complaints/export.csv').status_code == 403

    admin = User.query.filter_by(role='admin').first()
    set_session(client, admin)
    query = '?status=Escalated&category=Electrical&block=B'
    csv_response = client.get(f'/admin/complaints/export.csv{query}')
    pdf_response = client.get(f'/admin/complaints/export.pdf{query}')
    assert csv_response.status_code == 200
    assert b'SCCS-REPORT-1' in csv_response.data
    assert csv_response.mimetype == 'text/csv'
    assert pdf_response.status_code == 200
    assert pdf_response.mimetype == 'application/pdf'


def test_socketio_rejects_anonymous_connections(client):
    socket_client = socketio.test_client(app, flask_test_client=client)
    assert not socket_client.is_connected()
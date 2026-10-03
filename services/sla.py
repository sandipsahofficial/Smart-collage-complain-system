"""SLA evaluation and escalation logic for scheduled execution."""

from datetime import datetime, timedelta, timezone

from database import AuditEvent, Complaint, User, db

SLA_THRESHOLDS = {
    'Urgent': timedelta(hours=4),
    'High': timedelta(hours=12),
    'Medium': timedelta(hours=48),
    'Low': timedelta(hours=72),
}
OPEN_STATUSES = {'Pending', 'Assigned', 'In Progress'}


def utc_now():
    return datetime.now(timezone.utc)


def evaluate_sla(now=None, notify_admins=None, emit_event=None):
    """Escalate overdue open complaints once and return the affected IDs."""
    now = now or utc_now()
    escalated = []
    for complaint in Complaint.query.filter(Complaint.status.in_(OPEN_STATUSES)).all():
        created_at = complaint.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        threshold = SLA_THRESHOLDS.get(complaint.priority, SLA_THRESHOLDS['Medium'])
        due_at = created_at + threshold
        complaint.sla_due_at = due_at
        if complaint.escalated_at or now < due_at:
            continue

        complaint.status = 'Escalated'
        complaint.escalated_at = now
        db.session.add(AuditEvent(
            complaint_id=complaint.id,
            event_type='sla_escalated',
            details=f'{complaint.priority} complaint exceeded SLA threshold of {threshold}.',
        ))
        escalated.append(complaint)

    if escalated:
        db.session.commit()
        admins = User.query.filter_by(role='admin').all()
        for complaint in escalated:
            if notify_admins:
                notify_admins(
                    'Complaint SLA escalated',
                    f'{complaint.ticket_number} exceeded its {complaint.priority} SLA.',
                    complaint,
                )
            if emit_event:
                emit_event('complaint_updated', {
                    'complaint_id': complaint.id,
                    'status': complaint.status,
                    'reason': 'sla_escalated',
                }, [admin.id for admin in admins])
        db.session.commit()
    return escalated
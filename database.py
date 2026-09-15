from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    full_name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    hostel_name = db.Column(db.String(80), nullable=True)
    block = db.Column(db.String(50), nullable=True)
    room_number = db.Column(db.String(20), nullable=True)


class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(30), unique=True, nullable=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    location_type = db.Column(db.String(30), nullable=False, default='Hostel')
    campus_area = db.Column(db.String(100), nullable=False, default='Main Hostel')
    hostel_name = db.Column(db.String(80), nullable=False, default='Main Hostel')
    block = db.Column(db.String(50), nullable=False, default='A')
    room_number = db.Column(db.String(20), nullable=False, default='101')
    priority = db.Column(db.String(20), nullable=False, default='Medium')
    status = db.Column(db.String(20), default='Pending')
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    image_filename = db.Column(db.String(255), nullable=True)
    rating = db.Column(db.Integer, nullable=True)
    feedback_text = db.Column(db.Text, nullable=True)

    student = db.relationship(
        'User',
        foreign_keys='[Complaint.student_id]',
        backref=db.backref('complaints', lazy=True),
    )
    assigned_staff = db.relationship(
        'User',
        foreign_keys='[Complaint.assigned_to]',
        backref=db.backref('assigned_complaints', lazy=True),
    )
    comments = db.relationship('Comment', backref='complaint', lazy=True)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    sender = db.relationship('User', backref='comments', foreign_keys='[Comment.sender_id]')


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=True, index=True)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    recipient = db.relationship('User', backref=db.backref('notifications', lazy=True))
    complaint = db.relationship('Complaint', backref=db.backref('notifications', lazy=True))
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
    ai_category = db.Column(db.String(80), nullable=True)
    ai_department = db.Column(db.String(80), nullable=True)
    ai_priority = db.Column(db.String(20), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)
    ai_reasons = db.Column(db.Text, nullable=True)
    ai_safety_critical = db.Column(db.Boolean, nullable=False, default=False)

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
    ai_analyses = db.relationship(
        'AIAnalysis',
        back_populates='complaint',
        cascade='all, delete-orphan',
    )


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


class AIAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False, index=True)
    analysis_type = db.Column(db.String(50), nullable=False)
    input_hash = db.Column(db.String(64), nullable=False, index=True)
    prediction = db.Column(db.Text, nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(40), nullable=False, default='local')
    model_name = db.Column(db.String(80), nullable=False, default='rule-based-local')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    reviewed = db.Column(db.Boolean, nullable=False, default=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    final_decision = db.Column(db.Text, nullable=True)
    override_reason = db.Column(db.Text, nullable=True)

    complaint = db.relationship('Complaint', back_populates='ai_analyses')


class ComplaintSimilarity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False, index=True)
    related_complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False, index=True)
    similarity_score = db.Column(db.Float, nullable=False)
    relationship = db.Column(db.String(20), nullable=False, default='related')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AIFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('ai_analysis.id'), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    is_correct = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    analysis = db.relationship('AIAnalysis', backref=db.backref('feedback', lazy=True))
    reviewer = db.relationship('User', backref=db.backref('ai_feedback', lazy=True))
import io
from typing import Generator

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from app import app, limiter
from database import AIAnalysis, Comment, Complaint, Notification, User, db


@pytest.fixture()
def db_session() -> Generator:
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        SERVER_NAME='localhost',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SECRET_KEY='test-secret-key',
    )
    limiter.enabled = False
    with app.app_context():
        db.drop_all()
        db.create_all()
        default_admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin',
            full_name='Admin User',
            email='admin@example.com',
        )
        db.session.add(default_admin)
        db.session.commit()
        yield db.session
        db.session.remove()


@pytest.fixture()
def client(db_session) -> Generator:
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def student_user(db_session) -> User:
    user = User(
        username='student_user',
        password=generate_password_hash('student123'),
        role='student',
        full_name='Student User',
        email='student@example.com',
    )
    db.session.add(user)
    db.session.commit()
    yield user

    for complaint in Complaint.query.filter_by(student_id=user.id).all():
        Notification.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        AIAnalysis.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        Comment.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        db.session.delete(complaint)
    db.session.flush()
    db.session.delete(user)
    db.session.commit()


@pytest.fixture()
def staff_user(db_session) -> User:
    user = User(
        username='staff_user',
        password=generate_password_hash('staff123'),
        role='staff',
        full_name='Staff User',
        email='staff@example.com',
    )
    db.session.add(user)
    db.session.commit()
    yield user

    for complaint in Complaint.query.filter_by(student_id=user.id).all():
        Notification.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        AIAnalysis.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        Comment.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        db.session.delete(complaint)
    for complaint in Complaint.query.filter_by(assigned_to=user.id).all():
        Notification.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        AIAnalysis.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        Comment.query.filter_by(complaint_id=complaint.id).delete(synchronize_session=False)
        db.session.delete(complaint)
    db.session.flush()
    db.session.delete(user)
    db.session.commit()


def make_png_bytes() -> bytes:
    image = Image.new('RGB', (20, 20), 'blue')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()

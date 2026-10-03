"""Admin complaint filtering and report export helpers."""

import csv
import io
from datetime import datetime, time, timezone

from sqlalchemy import or_

from database import Complaint


def filtered_complaints(args):
    query = Complaint.query
    if args.get('status'):
        query = query.filter(Complaint.status == args['status'])
    if args.get('category'):
        query = query.filter(Complaint.category == args['category'])
    if args.get('block'):
        query = query.filter(Complaint.block == args['block'])
    if args.get('date_from'):
        start = datetime.combine(datetime.strptime(args['date_from'], '%Y-%m-%d').date(), time.min, tzinfo=timezone.utc)
        query = query.filter(Complaint.created_at >= start)
    if args.get('date_to'):
        end = datetime.combine(datetime.strptime(args['date_to'], '%Y-%m-%d').date(), time.max, tzinfo=timezone.utc)
        query = query.filter(Complaint.created_at <= end)
    return query.order_by(Complaint.created_at.desc())


def complaints_csv(complaints):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Ticket', 'Title', 'Status', 'Priority', 'Category', 'Block', 'Created', 'Student'])
    for complaint in complaints:
        writer.writerow([
            complaint.ticket_number, complaint.title, complaint.status, complaint.priority,
            complaint.category, complaint.block, complaint.created_at.isoformat(), complaint.student.username,
        ])
    return output.getvalue()
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

# === QUOTE MODEL ===
class Quote(db.Model):
    __tablename__ = 'quotes'
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    trip_id = db.Column(db.String, nullable=False)
    broker_name = db.Column(db.String, nullable=False)
    operator_name = db.Column(db.String, nullable=False)
    aircraft_type = db.Column(db.String, nullable=False)  # e.g. Turbo, Light, etc.
    price = db.Column(db.String, nullable=False)
    notes = db.Column(db.String, nullable=True)
    submitted_by_email = db.Column(db.String, nullable=True)     # who submitted the quote
    shared_with_emails = db.Column(db.String, nullable=True)     # comma-separated list of shared emails
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# === WINGTRIP MODEL ===
class WingTrip(db.Model):
    __tablename__ = 'wingtrips'
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    route = db.Column(db.String, nullable=False)
    departure_date = db.Column(db.String, nullable=False)
    passenger_count = db.Column(db.String, nullable=True)
    size = db.Column(db.String, nullable=True)
    budget = db.Column(db.String, nullable=True)
    broker_name = db.Column(db.String, nullable=True)
    broker_email = db.Column(db.String, nullable=True)
    planner_name = db.Column(db.String, nullable=True)
    planner_email = db.Column(db.String, nullable=True)
    status = db.Column(db.String, nullable=False, default="pending")  # e.g. pending, quoted, booked, archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

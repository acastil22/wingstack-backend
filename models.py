from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

# Function to generate unique IDs
def generate_uuid():
    return str(uuid.uuid4())

# Quote model with email tracking and sharing
class Quote(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    trip_id = db.Column(db.String, nullable=False, default=generate_uuid)
    broker_name = db.Column(db.String, nullable=False)
    operator_name = db.Column(db.String, nullable=False)
    aircraft_type = db.Column(db.String, nullable=False)  # e.g. Turbo, Light, etc.
    price = db.Column(db.String, nullable=False)
    notes = db.Column(db.String, nullable=True)
    submitted_by_email = db.Column(db.String, nullable=True)  # who submitted the quote
    shared_with_emails = db.Column(db.String, nullable=True)  # comma-separated list of shared emails
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

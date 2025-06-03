from flask_sqlalchemy import SQLAlchemy
import uuid
from datetime import datetime

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

class Account(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Trip(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    account_id = db.Column(db.String, db.ForeignKey('account.id'), nullable=False)
    trip_name = db.Column(db.String(200))
    origin = db.Column(db.String(10))
    destination = db.Column(db.String(10))
    departure_date = db.Column(db.Date)
    return_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Quote(db.Model):
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    trip_id = db.Column(db.String, db.ForeignKey('trip.id'), nullable=False)
    broker_name = db.Column(db.String(100))
    operator_name = db.Column(db.String(100))
    aircraft_type = db.Column(db.String(50))  # Turbo, Light, etc.
    price = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

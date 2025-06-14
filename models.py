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
    aircraft_type = db.Column(db.String, nullable=False)
    price = db.Column(db.String, nullable=False)
    notes = db.Column(db.String, nullable=True)
    submitted_by_email = db.Column(db.String, nullable=True)
    shared_with_emails = db.Column(db.String, nullable=True)
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
    status = db.Column(db.String, nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Chat relationship (optional)
    chat = db.relationship("Chat", backref="trip", uselist=False, cascade="all, delete-orphan")

# === CHAT MODEL ===
class Chat(db.Model):
    __tablename__ = 'chats'
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    trip_id = db.Column(db.String, db.ForeignKey('wingtrips.id'), nullable=False, unique=True)
    summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Messages relationship
    messages = db.relationship("Message", backref="chat", cascade="all, delete-orphan")

# === MESSAGE MODEL ===
class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    chat_id = db.Column(db.String, db.ForeignKey('chats.id'), nullable=False)
    sender_email = db.Column(db.String, nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# === TRIP LEG MODEL ===
class TripLeg(db.Model):
    __tablename__ = 'triplegs'
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    trip_id = db.Column(db.String, db.ForeignKey('wingtrips.id'), nullable=False)
    from_location = db.Column(db.String, nullable=False)
    to_location = db.Column(db.String, nullable=False)
    date = db.Column(db.String, nullable=True)
    time = db.Column(db.String, nullable=True)

    # Relationship (optional, for access from WingTrip)
    trip = db.relationship("WingTrip", backref=db.backref("legs", cascade="all, delete-orphan"))

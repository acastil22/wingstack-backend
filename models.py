from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, time
import uuid

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

# === USER MODEL (for planners and partners) ===
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    email = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String, nullable=True)
    role = db.Column(db.String, nullable=False)  # 'planner', 'partner', etc.
    preferred_partners = db.Column(db.Text, nullable=True)  # JSON-encoded list of emails
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    chat = db.relationship("Chat", backref="trip", uselist=False, cascade="all, delete-orphan")

# === CHAT MODEL ===
class Chat(db.Model):
    __tablename__ = 'chats'
    id = db.Column(db.String, primary_key=True, default=generate_uuid)
    trip_id = db.Column(db.String, db.ForeignKey('wingtrips.id'), nullable=False, unique=True)
    summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    date = db.Column(db.Date, nullable=True)
    time = db.Column(db.Time, nullable=True)

    trip = db.relationship("WingTrip", backref=db.backref("legs", cascade="all, delete-orphan"))

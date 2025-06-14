from flask import Flask, request, jsonify
from models import db, Quote, WingTrip, Chat, Message
import uuid
import os
from datetime import datetime
import openai
import json
from PyPDF2 import PdfReader
import requests
from bs4 import BeautifulSoup

client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return jsonify({"message": "WingStack backend is alive!"})


# === AI Trip Parsing with Time and ICAO Logic ===
@app.route('/parse-trip-input', methods=['POST'])
def parse_trip_input():
    data = request.get_json()
    input_text = data.get("input_text", "").strip()

    if not input_text:
        return jsonify({"error": "No input text provided."}), 400

    prompt = f"""
You are a private jet assistant. A user submitted this freeform request:

"""{input_text}"""

Extract structured JSON in this format:
{{
  "legs": [
    {{ "from": "TEB", "to": "EGLL", "date": "07/12/2025", "time": "14:00" }},
    {{ "from": "EGLL", "to": "OAK", "date": "07/15/2025", "time": "" }}
  ],
  "passenger_count": "5",
  "budget": "60000"
}}

Rules:
- Use FAA codes for U.S. airports (e.g., TEB).
- Use ICAO codes for international airports (e.g., EGLL).
- Date format must be MM/DD/YYYY.
- Time format must be 24-hour (HH:MM). Use "" if unknown.
- Leave any unknown value as an empty string.
- Respond with ONLY valid JSON. No extra text.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You're a smart assistant that converts trip requests into valid structured JSON using ICAO or FAA codes."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            max_tokens=800
        )

        content = response.choices[0].message.content.strip()
        try:
            parsed = json.loads(content)
            return jsonify(parsed), 200
        except json.JSONDecodeError:
            return jsonify({"error": "AI output was not valid JSON", "raw": content}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === TRIP CREATION ===
@app.route('/trips', methods=['POST'])
def create_trip():
    data = request.get_json()
    required = ["route", "departure_date"]
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    trip = WingTrip(
        id=str(uuid.uuid4()),
        route=data["route"],
        departure_date=data["departure_date"],
        passenger_count=data.get("passenger_count", ""),
        size=data.get("size", ""),
        budget=data.get("budget", ""),
        broker_name=data.get("broker_name", ""),
        broker_email=data.get("broker_email", ""),
        planner_name=data.get("planner_name", ""),
        planner_email=data.get("planner_email", ""),
        status=data.get("status", "pending"),
        created_at=datetime.utcnow()
    )
    db.session.add(trip)
    db.session.commit()
    return jsonify({"status": "success", "id": trip.id}), 200


# === LIST ALL TRIPS ===
@app.route('/trips', methods=['GET'])
def get_trips():
    trips = WingTrip.query.all()
    result = [{
        "id": t.id,
        "route": t.route,
        "departure_date": t.departure_date,
        "passenger_count": t.passenger_count,
        "size": t.size,
        "budget": t.budget,
        "broker_name": t.broker_name,
        "broker_email": t.broker_email,
        "planner_name": t.planner_name,
        "planner_email": t.planner_email,
        "status": t.status,
        "created_at": t.created_at
    } for t in trips]
    return jsonify(result), 200


# === PATCH TRIP ===
@app.route('/trips/<trip_id>', methods=['PATCH'])
def update_trip(trip_id):
    trip = WingTrip.query.get(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json()
    trip.route = data.get("route", trip.route)
    trip.departure_date = data.get("departure_date", trip.departure_date)
    trip.passenger_count = data.get("passenger_count", trip.passenger_count)
    trip.size = data.get("size", trip.size)
    trip.budget = data.get("budget", trip.budget)
    trip.status = data.get("status", trip.status)
    db.session.commit()
    return jsonify({"message": "Trip updated"}), 200


# === QUOTE CREATION ===
@app.route('/submit-quote', methods=['POST'])
def submit_quote():
    data = request.get_json()
    required = ["trip_id", "broker_name", "operator_name", "aircraft_type", "price"]
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    quote = Quote(
        id=str(uuid.uuid4()),
        trip_id=data["trip_id"],
        broker_name=data["broker_name"],
        operator_name=data["operator_name"],
        aircraft_type=data["aircraft_type"],
        price=data["price"],
        notes=data.get("notes", ""),
        submitted_by_email=data.get("submitted_by_email", ""),
        shared_with_emails=data.get("shared_with_emails", ""),
        created_at=datetime.utcnow()
    )
    db.session.add(quote)
    db.session.commit()
    return jsonify({"status": "success", "id": quote.id}), 200


# === GET QUOTES ===
@app.route('/quotes', methods=['GET'])
def get_quotes():
    quotes = Quote.query.all()
    result = [{
        "id": q.id,
        "trip_id": q.trip_id,
        "broker_name": q.broker_name,
        "operator_name": q.operator_name,
        "aircraft_type": q.aircraft_type,
        "price": q.price,
        "notes": q.notes,
        "submitted_by_email": q.submitted_by_email,
        "shared_with_emails": q.shared_with_emails,
        "created_at": q.created_at
    } for q in quotes]
    return jsonify(result), 200


@app.route('/quotes/by-email', methods=['GET'])
def get_quotes_by_email():
    email = request.args.get('email')
    if not email:
        return jsonify({"error": "Email is required"}), 400

    quotes = Quote.query.filter(
        (Quote.submitted_by_email == email) |
        (Quote.shared_with_emails.like(f"%{email}%"))
    ).all()

    result = [{
        "id": q.id,
        "trip_id": q.trip_id,
        "broker_name": q.broker_name,
        "operator_name": q.operator_name,
        "aircraft_type": q.aircraft_type,
        "price": q.price,
        "notes": q.notes,
        "submitted_by_email": q.submitted_by_email,
        "shared_with_emails": q.shared_with_emails,
        "created_at": q.created_at
    } for q in quotes]
    return jsonify(result), 200


# === CHAT FEATURES ===
@app.route('/chat/<trip_id>', methods=['GET'])
def get_or_create_chat(trip_id):
    chat = Chat.query.filter_by(trip_id=trip_id).first()
    if not chat:
        chat = Chat(trip_id=trip_id)
        db.session.add(chat)
        db.session.commit()
    return jsonify({
        "chat_id": chat.id,
        "trip_id": chat.trip_id,
        "summary": chat.summary or "",
        "created_at": chat.created_at.isoformat()
    })


@app.route('/messages/<chat_id>', methods=['GET'])
def get_messages(chat_id):
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp).all()
    return jsonify([{ 
        "id": m.id, 
        "sender_email": m.sender_email, 
        "content": m.content, 
        "timestamp": m.timestamp.isoformat() 
    } for m in messages])


@app.route('/messages', methods=['POST'])
def post_message():
    data = request.get_json()
    required = ['chat_id', 'sender_email', 'content']
    if not all(k in data for k in required):
        return jsonify({"error": "Missing required field"}), 400

    msg = Message(
        chat_id=data['chat_id'],
        sender_email=data['sender_email'],
        content=data['content'],
        timestamp=datetime.utcnow()
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({"message": "Message posted", "id": msg.id}), 200


# === CHAT SUMMARY (AI) ===
@app.route('/summarize-chat/<chat_id>', methods=['POST'])
def summarize_chat(chat_id):
    chat = Chat.query.get(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp).all()
    if not messages:
        return jsonify({"error": "No messages found"}), 400

    content = "\n".join([f"{m.sender_email}: {m.content}" for m in messages])
    prompt = f"Summarize this private jet trip conversation:\n\n{content}\n\nSummary:"

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                { "role": "system", "content": "You're a helpful assistant that summarizes private jet trip chat logs." },
                { "role": "user", "content": prompt }
            ],
            temperature=0.5,
            max_tokens=100
        )
        summary_text = response.choices[0].message.content.strip()
        chat.summary = summary_text
        db.session.commit()
        return jsonify({"summary": summary_text}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

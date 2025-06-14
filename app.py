from flask import Flask, request, jsonify
from models import db, Quote, WingTrip, Chat, Message, TripLeg
import uuid
import os
from datetime import datetime
import openai
import json

# Initialize OpenAI
openai_api_key = os.environ.get('OPENAI_API_KEY')
if not openai_api_key:
    raise ValueError("Missing OPENAI_API_KEY environment variable.")
client = openai.OpenAI(api_key=openai_api_key)

# Flask setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return jsonify({"message": "WingStack backend is alive!"})


# === AI PARSER ===
@app.route('/parse-trip-input', methods=['POST'])
def parse_trip_input():
    data = request.get_json()
    input_text = data.get("input_text", "").strip()

    if not input_text:
        return jsonify({"error": "No input text provided."}), 400

    prompt = f"""
You are a smart AI assistant for private jet bookings. A user entered the following trip request:

"""{input_text}"""

Your job is to:
1. Detect all airport names, cities, or common travel terms (e.g. "Teterboro", "NYC", "San Jose", "SFO").
2. Convert each airport or city into a proper airport code:
   - Use 3-letter FAA codes for U.S. airports (e.g., Teterboro → TEB, Van Nuys → VNY).
   - Use 4-letter ICAO codes for international airports (e.g., London Heathrow → EGLL).
3. Use your best judgment to correct spelling errors, formatting issues, or abbreviations (e.g. "teeboroh" → TEB). Assume some entries are not autocorrected — match what you believe the user intended.
4. Determine the logical travel sequence — even if the user only lists destinations or uses shorthand.
5. Match dates/times to legs in order. For example, if 3 destinations and 2 dates are listed, assume 2 legs. Use local timezone based on departure airport.
6. Time format must be 24-hour (e.g. 14:30). Dates must be MM/DD/YYYY.
7. Extract passenger count and budget as strings if mentioned.

Examples:
- "teeboroh to oakland and then sjc"
- "Fly from Van Nuys to Vegas June 12 at 3pm, back on June 14"
- "TEB to OAK to SJC June 20 at 0900 and June 21 at 1000, 5 pax, budget 70k"

Return only valid JSON like this:
{{
  "legs": [
    {{ "from": "KTEB", "to": "KOAK", "date": "06/20/2025", "time": "09:00" }},
    {{ "from": "KOAK", "to": "KSJC", "date": "06/21/2025", "time": "10:00" }}
  ],
  "passenger_count": "5",
  "budget": "70000"
}}

If any part is missing or unclear, return it as an empty string (""). No commentary or explanation — just valid JSON.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You convert messy human trip requests into structured JSON with FAA/ICAO codes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )

        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)
        return jsonify(parsed), 200

    except json.JSONDecodeError:
        return jsonify({"error": "AI output was not valid JSON", "raw_output": content}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === CREATE TRIP + LEGS ===
@app.route('/trips', methods=['POST'])
def create_trip():
    data = request.get_json()
    required = ["route", "departure_date"]
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    trip_id = str(uuid.uuid4())
    trip = WingTrip(
        id=trip_id,
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

    for leg in data.get("legs", []):
        try:
            date_obj = datetime.strptime(leg.get("date", ""), "%m/%d/%Y").date() if leg.get("date") else None
            time_obj = datetime.strptime(leg.get("time", ""), "%H:%M").time() if leg.get("time") else None
        except ValueError:
            return jsonify({"error": f"Invalid leg date/time format: {leg}"}), 400

        db.session.add(TripLeg(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            from_location=leg.get("from", ""),
            to_location=leg.get("to", ""),
            date=date_obj,
            time=time_obj
        ))

    db.session.commit()
    return jsonify({"status": "success", "id": trip_id}), 200


# === GET ALL TRIPS ===
@app.route('/trips', methods=['GET'])
def get_trips():
    trips = WingTrip.query.all()
    return jsonify([{
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
        "created_at": t.created_at.isoformat()
    } for t in trips]), 200


# === GET TRIP LEGS ===
@app.route('/trips/<trip_id>/legs', methods=['GET'])
def get_trip_legs(trip_id):
    legs = TripLeg.query.filter_by(trip_id=trip_id).all()
    if not legs:
        return jsonify({"message": "No legs found"}), 404

    return jsonify([{
        "id": leg.id,
        "from": leg.from_location,
        "to": leg.to_location,
        "date": leg.date.isoformat() if leg.date else "",
        "time": leg.time.strftime("%H:%M") if leg.time else ""
    } for leg in legs]), 200


# === SUBMIT QUOTE ===
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


# === GET QUOTES BY EMAIL ===
@app.route('/quotes/by-email', methods=['GET'])
def get_quotes_by_email():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    quotes = Quote.query.filter(
        (Quote.submitted_by_email == email) |
        (Quote.shared_with_emails.like(f"%{email}%"))
    ).all()

    return jsonify([{
        "id": q.id,
        "trip_id": q.trip_id,
        "broker_name": q.broker_name,
        "operator_name": q.operator_name,
        "aircraft_type": q.aircraft_type,
        "price": q.price,
        "notes": q.notes,
        "submitted_by_email": q.submitted_by_email,
        "shared_with_emails": q.shared_with_emails,
        "created_at": q.created_at.isoformat()
    } for q in quotes]), 200


# === CHAT LOGS & MESSAGES ===
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
    } for m in messages]), 200


@app.route('/messages', methods=['POST'])
def post_message():
    data = request.get_json()
    required = ["chat_id", "sender_email", "content"]
    if not all(k in data for k in required):
        return jsonify({"error": "Missing required field"}), 400

    msg = Message(
        chat_id=data["chat_id"],
        sender_email=data["sender_email"],
        content=data["content"],
        timestamp=datetime.utcnow()
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({"message": "Message posted", "id": msg.id}), 200


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
                { "role": "system", "content": "You summarize jet charter trip logs." },
                { "role": "user", "content": prompt }
            ],
            temperature=0.5,
            max_tokens=100
        )
        chat.summary = response.choices[0].message.content.strip()
        db.session.commit()
        return jsonify({"summary": chat.summary}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

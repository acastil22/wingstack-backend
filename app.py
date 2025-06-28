from flask import Flask, request, jsonify
from models import db, Quote, WingTrip, Chat, Message, TripLeg, User
import uuid
import os
import json
import re
from datetime import datetime
import openai
import base64
import io
import pdfplumber

# === OpenAI Setup ===
openai_api_key = os.environ.get('OPENAI_API_KEY')
if not openai_api_key:
    raise ValueError("Missing OPENAI_API_KEY environment variable.")
client = openai.OpenAI(api_key=openai_api_key)

# === Flask Setup ===
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return jsonify({"message": "WingStack backend is alive!"})

# === Fallback Regex Parser ===
def fallback_regex_parser(text):
    legs = []
    date_pattern = r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"
    airport_pattern = r"\b([A-Z]{3})[- ]+([A-Z]{3})\b"
    pax_pattern = r"(\d+)\s*(pax|passengers|adults)"
    budget_pattern = r"\$?(\d{1,3}(?:,\d{3})*|\d+)(k|K| thousand)?\s*(USD|usd|\$)?"

    leg_matches = re.findall(rf"{airport_pattern}.*?{date_pattern}", text)
    for match in leg_matches:
        from_airport, to_airport, date_str = match
        try:
            formatted_date = datetime.strptime(date_str, "%m/%d/%Y").strftime("%m/%d/%Y")
            legs.append({"from": from_airport, "to": to_airport, "date": formatted_date, "time": ""})
        except:
            continue

    pax_match = re.search(pax_pattern, text.lower())
    passenger_count = pax_match.group(1) if pax_match else ""

    budget_match = re.search(budget_pattern, text)
    if budget_match:
        raw_amount = budget_match.group(1).replace(",", "")
        if budget_match.group(2) in ["k", "K", " thousand"]:
            budget = str(int(float(raw_amount) * 1000))
        else:
            budget = raw_amount
    else:
        budget = ""

    return {
        "legs": legs,
        "passenger_count": passenger_count,
        "budget": budget
    }

# === AI Trip Parsing Endpoint ===
@app.route('/parse-trip-input', methods=['POST'])
def parse_trip_input():
    data = request.get_json()
    input_text = data.get("input_text", "").strip()
    if not input_text:
        return jsonify({"error": "No input text provided."}), 400

    system_prompt = (
        "You are an AI assistant for private jet bookings. "
        "Extract trip details from natural language into a strict JSON format. "
        "Correct spelling, infer IATA codes (KOAK = Oakland, MMSD = Cabo), convert dates to MM/DD/YYYY. "
        "Include legs, passenger count, and budget if available. Use empty strings if missing."
    )

    user_prompt = f"""
Input: \"{input_text}\"

Format:
{{
  "legs": [{{ "from": "KTEB", "to": "KOAK", "date": "06/20/2025", "time": "" }}],
  "passenger_count": "5",
  "budget": "50000"
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=600
        )
        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)

        if not isinstance(parsed.get("legs"), list) or not parsed.get("passenger_count"):
            raise ValueError("Missing required fields")

        return jsonify(parsed), 200

    except Exception as e:
        print("❌ AI failed. Falling back to regex parser.")
        fallback = fallback_regex_parser(input_text)

        # Log failed input
        os.makedirs("logs", exist_ok=True)
        with open("logs/failed_parse_logs.txt", "a") as f:
            f.write(f"[{datetime.now()}] Failed AI input:\n{input_text}\nFallback result:\n{json.dumps(fallback)}\n\n")

        return jsonify(fallback), 200

# === Trip Creation ===
@app.route('/trips', methods=['POST'])
def create_trip():
    data = request.get_json()
    print("\U0001F4E6 Received trip data:", data)

    required = ["route", "departure_date"]
    if not all(field in data for field in required):
        print("❌ Missing required fields:", data)
        return jsonify({"error": "Missing required fields"}), 400

    try:
        datetime.strptime(data["departure_date"], "%m/%d/%Y")
    except ValueError:
        print("❌ Invalid date format:", data["departure_date"])
        return jsonify({"error": "Invalid date format. Use MM/DD/YYYY."}), 400

    trip_id = str(uuid.uuid4())
    trip = WingTrip(
        id=trip_id,
        route=data["route"],
        departure_date=data["departure_date"],
        passenger_count=data.get("passenger_count", ""),
        size=data.get("size", ""),
        budget=data.get("budget", ""),
        partner_names=json.dumps(data.get("partner_names", [])),
        partner_emails=json.dumps(data.get("partner_emails", [])),
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
            db.session.add(TripLeg(
                id=str(uuid.uuid4()),
                trip_id=trip_id,
                from_location=leg.get("from", ""),
                to_location=leg.get("to", ""),
                date=date_obj,
                time=time_obj
            ))
        except ValueError:
            print("❌ Invalid leg format:", leg)
            return jsonify({"error": f"Invalid leg date/time format: {leg}"}), 400

    db.session.commit()
    print("✅ Trip created successfully:", trip_id)
    return jsonify({"status": "success", "id": trip_id}), 200
@app.route('/trips', methods=['GET'])
def get_trips():
    try:
        status_filter = request.args.get("status")
        planner_email = request.args.get("planner_email")

        query = WingTrip.query
        if status_filter:
            query = query.filter_by(status=status_filter)
        if planner_email:
            query = query.filter_by(planner_email=planner_email)

        trips = query.all()

        results = []
        for t in trips:
            try:
                results.append({
                    "id": t.id,
                    "route": t.route,
                    "departure_date": t.departure_date,
                    "passenger_count": t.passenger_count,
                    "size": t.size,
                    "budget": t.budget,
                    "partner_names": json.loads(t.partner_names or "[]"),
                    "partner_emails": json.loads(t.partner_emails or "[]"),
                    "planner_name": t.planner_name,
                    "planner_email": t.planner_email,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "broker_name": json.loads(t.partner_names or "[]")[0] if t.partner_names else "",
                    "broker_email": json.loads(t.partner_emails or "[]")[0] if t.partner_emails else ""
                })
            except Exception as trip_err:
                print(f"❌ Error processing trip {t.id}: {trip_err}")

        return jsonify(results), 200

    except Exception as e:
        print(f"❌ Error in /trips GET route: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# You can leave the rest of app.py (PATCH, DELETE, CHAT, etc.) unchanged unless you want to support updates to partner lists.

# (Optional improvements: update PATCH endpoint to support editing partner_emails and partner_names)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

@app.route('/trips/<trip_id>', methods=['PATCH'])
def update_trip(trip_id):
    trip = WingTrip.query.get(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json()
    if "route" in data:
        trip.route = data["route"]
    if "departure_date" in data:
        try:
            datetime.strptime(data["departure_date"], "%m/%d/%Y")
            trip.departure_date = data["departure_date"]
        except ValueError:
            return jsonify({"error": "Invalid date format. Use MM/DD/YYYY."}), 400
    if "passenger_count" in data:
        trip.passenger_count = data["passenger_count"]
    if "budget" in data:
        trip.budget = data["budget"]
    if "status" in data:
        trip.status = data["status"]

    db.session.commit()
    return jsonify({"status": "updated"}), 200

@app.route('/trips/mark-booked/<trip_id>', methods=['POST'])
def mark_trip_as_booked(trip_id):
    trip = WingTrip.query.get(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404
    trip.status = "booked"
    db.session.commit()
    return jsonify({"message": f"Trip {trip_id} marked as booked"}), 200

@app.route('/trips/<trip_id>/legs', methods=['GET'])
def get_trip_legs(trip_id):
    legs = TripLeg.query.filter_by(trip_id=trip_id).all()
    return jsonify([{
        "id": l.id,
        "from": l.from_location,
        "to": l.to_location,
        "date": l.date.isoformat() if l.date else "",
        "time": l.time.strftime("%H:%M") if l.time else ""
    } for l in legs]), 200

@app.route('/trips/archive/<trip_id>', methods=['POST'])
def archive_trip(trip_id):
    trip = WingTrip.query.get(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404
    trip.status = "archived"
    db.session.commit()
    return jsonify({"status": "archived"}), 200

@app.route('/trips/restore/<trip_id>', methods=['POST'])
def restore_trip(trip_id):
    trip = WingTrip.query.get(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404
    trip.status = "pending"
    db.session.commit()
    return jsonify({"status": "restored"}), 200

@app.route('/trips/<trip_id>', methods=['DELETE'])
def delete_trip(trip_id):
    trip = WingTrip.query.get(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    trip.status = "deleted"
    db.session.commit()

    # ✅ Create chat and system message
    chat = Chat.query.filter_by(trip_id=trip_id).first()
    if not chat:
        chat = Chat(trip_id=trip_id)
        db.session.add(chat)
        db.session.commit()

    msg = Message(
        chat_id=chat.id,
        sender_email="system@wingstack.ai",
        content="Planner has deleted this trip request."
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({"status": "deleted", "chat_id": chat.id}), 200

@app.route('/submit-quote', methods=['POST'])
def submit_quote():
    data = request.get_json()
    required = ["trip_id", "broker_name", "operator_name", "aircraft_type", "price"]
    if not all(k in data for k in required):
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

@app.route('/chat/<trip_id>', methods=['GET'])
def get_or_create_chat(trip_id):
    chat = Chat.query.filter_by(trip_id=trip_id).first()
    if not chat:
        chat = Chat(trip_id=trip_id)
        db.session.add(chat)
        db.session.commit()

        # Optional: preload a "deleted" message when chat is first created
        # You can move this elsewhere if you want more control
        deletion_msg = Message(
            chat_id=chat.id,
            sender_email="system@wingstack.ai",
            content="Planner has deleted this trip request.",
        )
        db.session.add(deletion_msg)
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
                {"role": "system", "content": "You summarize jet charter trip logs."},
                {"role": "user", "content": prompt}
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

@app.route('/parse-email-quote', methods=['POST'])
def parse_email_quote():
    data = request.get_json()
    email_body = data.get("email_body", "").strip()

    if not email_body:
        return jsonify({"error": "No email body provided."}), 400

    system_prompt = (
        "You are an expert assistant for parsing private jet charter quotes. "
        "Extract structured information from this email body. "
        "Always respond in JSON. Fields: aircraft, price, category (e.g., Light, Mid, Heavy), broker name, "
        "cancellation policy, Wi-Fi availability, year of make (YOM), year of refurbishment (if available), notes."
    )

    user_prompt = f"""
Email Body:
\"\"\"{email_body}\"\"\"

Return JSON in this format:
{{
  "aircraft": "Citation XLS",
  "price": "23000",
  "category": "Mid",
  "broker_name": "JetLux",
  "cancellation_policy": "25% nonrefundable",
  "wifi": "Yes",
  "yom": "2018",
  "refurbished_year": "2022",
  "notes": "Seats 8, enclosed lav, new interior"
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=800
        )
        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)
        return jsonify(parsed), 200

    except Exception as e:
        print("❌ Failed to parse email quote:", str(e))
        return jsonify({"error": str(e)}), 500
        
@app.route('/parse-quote-pdf', methods=['POST'])
def parse_quote_pdf():
    data = request.get_json()
    b64pdf = data.get("base64_pdf", "").strip()

    if not b64pdf:
        return jsonify({"error": "Missing PDF content"}), 400

    try:
        # Decode PDF and extract text
        pdf_bytes = base64.b64decode(b64pdf)
        pdf_file = io.BytesIO(pdf_bytes)

        with pdfplumber.open(pdf_file) as pdf:
            extracted_text = "\n".join([page.extract_text() or "" for page in pdf.pages])

        if not extracted_text.strip():
            return jsonify({"error": "PDF parsing returned empty content."}), 400

        # Prompt AI with extracted text
        system_prompt = (
            "You are an expert assistant for private jet charter brokers. "
            "Extract structured quote details from this PDF text. Return clean JSON only. "
            "Fields: aircraft, price, category (e.g., Light, Mid, Heavy), broker name, "
            "cancellation policy, Wi-Fi, YOM, refurbished year, and notes."
        )

        user_prompt = f"""
Quote PDF text:
\"\"\"{extracted_text}\"\"\"

Return JSON in this format:
{{
  "aircraft": "Gulfstream G450",
  "price": "39000",
  "category": "Heavy",
  "broker_name": "Monarch Air",
  "cancellation_policy": "50% nonrefundable inside 72h",
  "wifi": "Yes",
  "yom": "2015",
  "refurbished_year": "2021",
  "notes": "Seats 13. Flight attendant included. Pets allowed."
}}
"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=800
        )

        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)
        return jsonify(parsed), 200

    except Exception as e:
        print("❌ PDF parsing or AI failed:", str(e))
        return jsonify({"error": str(e)}), 500

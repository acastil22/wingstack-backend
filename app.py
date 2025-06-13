from flask import Flask, request, jsonify
from models import db, Quote, WingTrip
import uuid
import os
from datetime import datetime
import openai
import json

# PDF and Web scraping:
from PyPDF2 import PdfReader
import requests
from bs4 import BeautifulSoup

# Initialize OpenAI client (v1+ API)
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

# === TRIP CREATION (Planner or Broker can use) ===
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
    result = []
    for t in trips:
        result.append({
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
        })
    return jsonify(result), 200

# === QUOTE CREATION ===
@app.route('/submit-quote', methods=['POST'])
def submit_quote():
    data = request.get_json()
    required = ["trip_id", "broker_name", "operator_name", "aircraft_type", "price"]
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    new_quote = Quote(
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

    db.session.add(new_quote)
    db.session.commit()
    return jsonify({"status": "success", "id": new_quote.id}), 200

# === LIST ALL QUOTES ===
@app.route('/quotes', methods=['GET'])
def get_quotes():
    quotes = Quote.query.all()
    result = []
    for q in quotes:
        result.append({
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
        })
    return jsonify(result), 200

# === QUOTES FILTERED BY EMAIL ===
@app.route('/quotes/by-email', methods=['GET'])
def get_quotes_by_email():
    email = request.args.get('email')
    if not email:
        return jsonify({"error": "Email is required"}), 400

    quotes = Quote.query.filter(
        (Quote.submitted_by_email == email) |
        (Quote.shared_with_emails.like(f"%{email}%"))
    ).all()

    result = []
    for q in quotes:
        result.append({
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
        })
    return jsonify(result), 200

# === OpenAI Extraction for any text ===
@app.route('/extract-quote-info', methods=['POST'])
def extract_quote_info():
    data = request.get_json()
    input_text = data.get("input_text", "")
    input_type = data.get("input_type", "email_body")

    if not input_text:
        return jsonify({"error": "No input_text provided"}), 400

    prompt = f"""
You are a private aviation quote extraction assistant. Extract the following fields from the text below (if available): 
Company, Aircraft Type, Price, Taxes Included (yes/no/amount), Pictures (links or mention), Cancellation Policy, Wi-Fi (yes/no/unknown), Year of Make (YOM), Year of Refurbishment.

Input type: {input_type}
Text:
{input_text}

Return a JSON object with keys: company, aircraft_type, price, taxes_included, pictures, cancellation_policy, wifi, year_of_make, year_of_refurbishment. If not found, set value as null.
"""

    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You extract structured data from messy quote emails or PDFs."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.0,
        )
        response_text = completion.choices[0].message.content

        try:
            response_json = json.loads(response_text)
            return jsonify(response_json), 200
        except Exception:
            return jsonify({"raw_response": response_text}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === PDF UPLOAD QUOTE EXTRACTION ===
@app.route('/extract-quote-from-pdf', methods=['POST'])
def extract_quote_from_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    try:
        reader = PdfReader(file)
        text = ''
        for page in reader.pages:
            text += page.extract_text() or ''
        if not text.strip():
            return jsonify({'error': 'Could not extract text from PDF'}), 400

        # Use the existing extraction logic
        with app.test_request_context(json={
            "input_text": text,
            "input_type": "pdf_text"
        }):
            return extract_quote_info()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === LINK SCRAPE FOR PUBLIC QUOTE LINKS ===
@app.route('/extract-quote-from-link', methods=['POST'])
def extract_quote_from_link():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text(separator="\n")
        # Use the existing extraction logic (AI)
        with app.test_request_context(json={
            "input_text": page_text,
            "input_type": "link"
        }):
            return extract_quote_info()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === PATCH TRIP BY ID ===
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

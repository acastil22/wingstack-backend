from flask import Flask, request, jsonify
from models import db, Quote
import uuid
import os
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return jsonify({"message": "WingStack backend is alive!"})

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
        email=data.get("email", ""),
        shared_with=data.get("shared_with", ""),
        created_at=datetime.utcnow()
    )

    db.session.add(new_quote)
    db.session.commit()

    return jsonify({"status": "success", "id": new_quote.id}), 200

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
            "email": q.email,
            "shared_with": q.shared_with,
            "created_at": q.created_at
        })
    return jsonify(result), 200

@app.route('/quotes/by-email', methods=['GET'])
def get_quotes_by_email():
    email = request.args.get('email')
    if not email:
        return jsonify({"error": "Email is required"}), 400

    quotes = Quote.query.filter(
        (Quote.email == email) |
        (Quote.shared_with.like(f"%{email}%"))
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
            "email": q.email,
            "shared_with": q.shared_with,
            "created_at": q.created_at
        })
    return jsonify(result), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

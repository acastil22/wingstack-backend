from flask import Flask, jsonify, request
import uuid

app = Flask(__name__)

# Store quotes temporarily in memory
quotes_db = []

@app.route('/')
def home():
    return jsonify({"message": "WingStack backend is alive!"})

@app.route('/submit-quote', methods=['POST'])
def submit_quote():
    data = request.get_json()

    required = ["broker", "aircraft", "route", "price", "departure_date"]
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    quote = {
        "id": str(uuid.uuid4()),
        "broker": data["broker"],
        "aircraft": data["aircraft"],
        "route": data["route"],
        "price": data["price"],
        "departure_date": data["departure_date"],
        "notes": data.get("notes", "")
    }
    quotes_db.append(quote)

    return jsonify({"status": "success", "id": quote["id"]}), 200

@app.route('/quotes', methods=['GET'])
def get_quotes():
    return jsonify(quotes_db), 200


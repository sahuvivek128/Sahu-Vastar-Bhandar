
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import random
import time
import cloudinary
import cloudinary.uploader
from pymongo import MongoClient
from bson import ObjectId
import os

app = Flask(__name__, static_folder=".")
CORS(app)

# ─── CONFIG (ENV VARIABLES) ───
FAST2SMS_API_KEY  = os.getenv("FAST2SMS_API_KEY")
ADMIN_MOBILE      = os.getenv("ADMIN_MOBILE", "8948815093")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD")

MONGO_URI         = os.getenv("MONGO_URI")
CLOUDINARY_CLOUD  = os.getenv("CLOUDINARY_CLOUD")
CLOUDINARY_KEY    = os.getenv("CLOUDINARY_KEY")
CLOUDINARY_SECRET = os.getenv("CLOUDINARY_SECRET")

PORT = int(os.environ.get("PORT", 5000))

# ─── MONGODB ───
try:
    client = MongoClient(MONGO_URI, connectTimeoutMS=5000, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db     = client["sahu_vastra_bhandar"]
    users_col    = db["users"]
    products_col = db["products"]
    orders_col   = db["orders"]
    print("✓ MongoDB connected")
except Exception as e:
    print(f"MongoDB error: {e}")
    client = db = users_col = products_col = orders_col = None

# ─── CLOUDINARY ───
cloudinary.config(
    cloud_name = CLOUDINARY_CLOUD,
    api_key    = CLOUDINARY_KEY,
    api_secret = CLOUDINARY_SECRET
)

otp_store = {}

# ─── HELPERS ───
def generate_otp():
    return str(random.randint(100000, 999999))

def clean_expired():
    now = time.time()
    for m in list(otp_store.keys()):
        if otp_store[m]["expiresAt"] < now:
            del otp_store[m]

def send_sms(mobile, otp):
    message = f"Your OTP is {otp}"
    payload = {"route": "q", "message": message, "language": "english", "flash": 0, "numbers": mobile}
    headers = {"authorization": FAST2SMS_API_KEY, "Content-Type": "application/json"}
    r = requests.post("https://www.fast2sms.com/dev/bulkV2", json=payload, headers=headers)
    return r.json()

def serialize(doc):
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

# ─── ROUTES ───
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    try:
        client.admin.command('ping')
        return jsonify({"status": "ok", "db": "connected"})
    except:
        return jsonify({"status": "error"}), 500

# AUTH
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    clean_expired()
    mobile = request.json.get("mobile")
    otp = generate_otp()
    otp_store[mobile] = {"otp": otp, "expiresAt": time.time() + 300}
    send_sms(mobile, otp)
    return jsonify({"success": True})

@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    mobile = request.json.get("mobile")
    otp    = request.json.get("otp")

    record = otp_store.get(mobile)
    if not record or record["otp"] != str(otp):
        return jsonify({"success": False}), 400

    users_col.update_one(
        {"mobile": mobile},
        {"$set": {"mobile": mobile, "role": "customer"}},
        upsert=True
    )

    return jsonify({"success": True})

# PRODUCTS
@app.route("/api/products", methods=["GET"])
def get_products():
    docs = list(products_col.find())
    return jsonify([serialize(d) for d in docs])

@app.route("/api/products", methods=["POST"])
def add_product():
    body = request.json
    result = products_col.insert_one(body)
    body["_id"] = str(result.inserted_id)
    return jsonify(body)

# ORDERS
@app.route("/api/orders", methods=["POST"])
def place_order():
    body = request.json
    orders_col.insert_one(body)
    return jsonify({"success": True})

# ─── RUN ───
if __name__ == "__main__":
    print(f"Running on {PORT}")
    app.run(host="0.0.0.0", port=PORT)

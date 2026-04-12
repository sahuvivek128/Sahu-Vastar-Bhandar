from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import random
import re
import time
import cloudinary
import cloudinary.uploader
from pymongo import MongoClient
from bson import ObjectId
import os
from functools import wraps
from datetime import datetime, timedelta

# ─── LOAD .env ───
load_dotenv()

app = Flask(__name__, static_folder=".")
CORS(app)

# ─── CONFIG — all from environment variables ───
FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY")
ADMIN_MOBILE     = os.getenv("ADMIN_MOBILE")
ADMIN_PASSWORD   = os.getenv("ADMIN_PASSWORD")
ADMIN_TOKEN      = os.getenv("ADMIN_TOKEN", "svb-secret-admin-token")  # set a strong value in .env

MONGO_URI        = os.getenv("MONGO_URI")
CLOUDINARY_CLOUD = os.getenv("CLOUDINARY_CLOUD")
CLOUDINARY_KEY   = os.getenv("CLOUDINARY_KEY")
CLOUDINARY_SECRET= os.getenv("CLOUDINARY_SECRET")

PORT = int(os.environ.get("PORT", 5000))

# ─── MONGODB ───
try:
    if not MONGO_URI:
        raise ValueError("MONGO_URI environment variable is not set!")
    client = MongoClient(MONGO_URI, connectTimeoutMS=5000, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db           = client["sahu_vastra_bhandar"]
    users_col    = db["users"]
    products_col = db["products"]
    orders_col   = db["orders"]
    otps_col     = db["otps"]
    # Performance indexes
    products_col.create_index("ts")
    orders_col.create_index("mobile")
    orders_col.create_index("createdAt")
    users_col.create_index("mobile", unique=True)
    # TTL index — MongoDB auto-deletes expired OTPs
    otps_col.create_index("expiresAt", expireAfterSeconds=0)
    print("✓ MongoDB connected and indexes created")
except Exception as e:
    print(f"✗ MongoDB error: {e}")
    client = db = users_col = products_col = orders_col = otps_col = None

# ─── CLOUDINARY ───
if CLOUDINARY_CLOUD and CLOUDINARY_KEY and CLOUDINARY_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD,
        api_key=CLOUDINARY_KEY,
        api_secret=CLOUDINARY_SECRET
    )
else:
    print("⚠ Cloudinary not configured — image/video uploads will fail.")

# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────
def db_ok():
    return products_col is not None

def generate_otp():
    return str(random.randint(100000, 999999))

def validate_mobile(mobile):
    return bool(re.match(r'^[6-9]\d{9}$', str(mobile).strip()))

def send_sms(mobile, otp):
    if not FAST2SMS_API_KEY:
        print(f"[DEV] OTP for {mobile}: {otp}  (SMS skipped — no API key)")
        return {"return": True}
    message = f"Your OTP for Sahu Vastra Bhandar is {otp}. Valid for 5 minutes."
    payload = {"route": "q", "message": message, "language": "english", "flash": 0, "numbers": mobile}
    headers = {"authorization": FAST2SMS_API_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post("https://www.fast2sms.com/dev/bulkV2", json=payload, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        print(f"SMS error: {e}")
        return {"return": False}

def serialize(doc):
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

def generate_order_id():
    return "SVB" + str(int(time.time()))[-8:]

# ─── ADMIN AUTH DECORATOR ───
def admin_required(f):
    """Protect admin-only routes — frontend must send X-Admin-Token header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Admin-Token")
        if not token or token != ADMIN_TOKEN:
            return jsonify({"success": False, "message": "Unauthorized — admin access only"}), 401
        return f(*args, **kwargs)
    return decorated

# ──────────────────────────────────────────────────────────────
# STATIC
# ──────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

# ──────────────────────────────────────────────────────────────
# HEALTH CHECK
# ──────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    if not db_ok():
        return jsonify({"status": "error", "db": "not connected"}), 503
    try:
        client.admin.command('ping')
        return jsonify({"status": "ok", "db": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "db": str(e)}), 500

# ──────────────────────────────────────────────────────────────
# AUTH — OTP stored in MongoDB with TTL (survives server restarts)
# ──────────────────────────────────────────────────────────────
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503

    mobile = str(request.json.get("mobile", "")).strip()
    if not validate_mobile(mobile):
        return jsonify({"success": False, "message": "Enter a valid 10-digit Indian mobile number"}), 400

    # Rate limit: max 3 OTPs per 10 minutes per mobile
    recent = otps_col.count_documents({
        "mobile": mobile,
        "sentAt": {"$gte": datetime.utcnow() - timedelta(minutes=10)}
    })
    if recent >= 3:
        return jsonify({"success": False, "message": "Too many OTP requests. Please wait 10 minutes."}), 429

    otp = generate_otp()
    otps_col.replace_one(
        {"mobile": mobile},
        {
            "mobile":    mobile,
            "otp":       otp,
            "attempts":  0,
            "sentAt":    datetime.utcnow(),
            "expiresAt": datetime.utcnow() + timedelta(minutes=5)
        },
        upsert=True
    )

    result = send_sms(mobile, otp)
    if result.get("return") == True:
        return jsonify({"success": True, "message": "OTP sent successfully!"})
    else:
        otps_col.delete_one({"mobile": mobile})
        return jsonify({"success": False, "message": "Failed to send SMS. Please try again."}), 500

@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503

    mobile = str(request.json.get("mobile", "")).strip()
    otp    = str(request.json.get("otp", "")).strip()

    if not validate_mobile(mobile) or not otp:
        return jsonify({"success": False, "message": "Invalid request"}), 400

    record = otps_col.find_one({"mobile": mobile})
    if not record:
        return jsonify({"success": False, "message": "No OTP found. Please request a new one."}), 400
    if record["expiresAt"] < datetime.utcnow():
        otps_col.delete_one({"mobile": mobile})
        return jsonify({"success": False, "message": "OTP has expired. Please request a new one."}), 400

    attempts = record.get("attempts", 0) + 1
    if attempts > 5:
        otps_col.delete_one({"mobile": mobile})
        return jsonify({"success": False, "message": "Too many wrong attempts. Request a new OTP."}), 429

    if record["otp"] != otp:
        otps_col.update_one({"mobile": mobile}, {"$set": {"attempts": attempts}})
        remaining = 5 - attempts
        return jsonify({"success": False, "message": f"Wrong OTP. {remaining} attempt(s) left."}), 400

    # OTP correct
    otps_col.delete_one({"mobile": mobile})
    users_col.update_one(
        {"mobile": mobile},
        {"$set": {"mobile": mobile, "role": "customer", "lastLogin": time.time()}},
        upsert=True
    )
    return jsonify({
        "success": True,
        "message": "Login successful!",
        "user":    {"mobile": mobile, "role": "customer", "isAdmin": False}
    })

@app.route("/api/admin-login", methods=["POST"])
def admin_login():
    mobile   = str(request.json.get("mobile", "")).strip()
    password = str(request.json.get("password", ""))
    if mobile == ADMIN_MOBILE and password == ADMIN_PASSWORD:
        return jsonify({
            "success": True,
            "message": "Admin login successful!",
            "token":   ADMIN_TOKEN,   # frontend stores this and sends as X-Admin-Token
            "user":    {"mobile": mobile, "role": "admin", "isAdmin": True}
        })
    return jsonify({"success": False, "message": "Invalid admin credentials"}), 401

# ──────────────────────────────────────────────────────────────
# PRODUCTS — GET is public; POST/PUT/DELETE require admin token
# ──────────────────────────────────────────────────────────────
@app.route("/api/products", methods=["GET"])
def get_products():
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        docs = list(products_col.find().sort("ts", -1))
        return jsonify({"success": True, "products": [serialize(d) for d in docs]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/products", methods=["POST"])
@admin_required
def add_product():
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        body = request.json
        if not body.get("name") or not body.get("orig"):
            return jsonify({"success": False, "message": "Name and price are required"}), 400
        doc = {
            "name":      str(body["name"]).strip(),
            "desc":      str(body.get("desc", "")).strip(),
            "orig":      float(body["orig"]),
            "sale":      float(body["sale"]) if body.get("sale") else None,
            "cat":       str(body.get("cat", "")).strip(),
            "color":     str(body.get("color", "")).lower().strip(),
            "badge":     str(body.get("badge", "")).strip(),
            "available": bool(body.get("available", True)),
            "rating":    float(body.get("rating", 0)),
            "reviews":   int(body.get("reviews", 0)),
            "photos":    body.get("photos", []),
            "video":     body.get("video", None),
            "ts":        int(time.time() * 1000)
        }
        result = products_col.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return jsonify({"success": True, "product": doc}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/products/<id>", methods=["PUT"])
@admin_required
def update_product(id):
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        oid  = ObjectId(id)
        body = request.json
        body.pop("_id", None)
        update = {
            "name":      str(body.get("name", "")).strip(),
            "desc":      str(body.get("desc", "")).strip(),
            "orig":      float(body["orig"]),
            "sale":      float(body["sale"]) if body.get("sale") else None,
            "cat":       str(body.get("cat", "")).strip(),
            "color":     str(body.get("color", "")).lower().strip(),
            "badge":     str(body.get("badge", "")).strip(),
            "available": bool(body.get("available", True)),
            "rating":    float(body.get("rating", 0)),
            "reviews":   int(body.get("reviews", 0)),
            "photos":    body.get("photos", []),
            "video":     body.get("video", None),
        }
        products_col.update_one({"_id": oid}, {"$set": update})
        updated = products_col.find_one({"_id": oid})
        return jsonify({"success": True, "product": serialize(updated)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/products/<id>", methods=["DELETE"])
@admin_required
def delete_product(id):
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        products_col.delete_one({"_id": ObjectId(id)})
        return jsonify({"success": True, "message": "Product deleted"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ──────────────────────────────────────────────────────────────
# UPLOAD — admin only
# ──────────────────────────────────────────────────────────────
@app.route("/api/upload-image", methods=["POST"])
@admin_required
def upload_image():
    try:
        data_url = request.json.get("dataUrl")
        if not data_url:
            return jsonify({"success": False, "message": "No image data provided"}), 400
        result = cloudinary.uploader.upload(data_url, folder="sahu_vastra_bhandar/photos")
        return jsonify({"success": True, "url": result["secure_url"], "publicId": result["public_id"]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/upload-video", methods=["POST"])
@admin_required
def upload_video():
    try:
        data_url = request.json.get("dataUrl")
        if not data_url:
            return jsonify({"success": False, "message": "No video data provided"}), 400
        result = cloudinary.uploader.upload(
            data_url, resource_type="video", folder="sahu_vastra_bhandar/videos"
        )
        return jsonify({"success": True, "url": result["secure_url"], "publicId": result["public_id"]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ──────────────────────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────────────────────
@app.route("/api/orders", methods=["POST"])
def place_order():
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        body = request.json
        if not body.get("mobile") or not body.get("items"):
            return jsonify({"success": False, "message": "mobile and items are required"}), 400
        doc = {
            "orderId":   generate_order_id(),
            "mobile":    body["mobile"],
            "items":     body["items"],
            "total":     float(body.get("total", 0)),
            "payMethod": body.get("payMethod", ""),
            "address":   body.get("address", None),
            "status":    "placed",
            "createdAt": time.time()
        }
        result = orders_col.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return jsonify({"success": True, "orderId": doc["orderId"], "order": doc}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/orders", methods=["GET"])
@admin_required
def get_orders():
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        mobile = request.args.get("mobile")
        query  = {"mobile": mobile} if mobile else {}
        docs   = list(orders_col.find(query).sort("createdAt", -1))
        return jsonify({"success": True, "orders": [serialize(d) for d in docs]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/orders/<order_id>/status", methods=["PUT"])
@admin_required
def update_order_status(order_id):
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        valid_statuses = ["placed", "confirmed", "shipped", "delivered", "cancelled"]
        status = request.json.get("status")
        if status not in valid_statuses:
            return jsonify({"success": False, "message": f"Invalid status. Use: {valid_statuses}"}), 400
        orders_col.update_one({"orderId": order_id}, {"$set": {"status": status}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ──────────────────────────────────────────────────────────────
# CUSTOMERS — admin only, fast aggregation pipeline
# ──────────────────────────────────────────────────────────────
@app.route("/api/customers", methods=["GET"])
@admin_required
def get_customers():
    if not db_ok():
        return jsonify({"success": False, "message": "Database not connected"}), 503
    try:
        pipeline = [
            {"$match": {"role": "customer"}},
            {"$lookup": {
                "from": "orders",
                "localField": "mobile",
                "foreignField": "mobile",
                "as": "orders"
            }},
            {"$addFields": {
                "orderCount": {"$size": "$orders"},
                "totalSpent": {"$sum": "$orders.total"}
            }},
            {"$project": {"orders": 0}},
            {"$sort": {"lastLogin": -1}}
        ]
        customers = list(users_col.aggregate(pipeline))
        return jsonify({"success": True, "customers": [serialize(c) for c in customers]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ──────────────────────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"✅ Sahu Vastra Bhandar — starting on port {PORT}")
    print(f"   Debug mode: {debug_mode}")
    app.run(host="0.0.0.0", port=PORT, debug=debug_mode)

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
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "admin@svb123")

MONGO_URI         = os.getenv("MONGO_URI")
CLOUDINARY_CLOUD  = os.getenv("CLOUDINARY_CLOUD")
CLOUDINARY_KEY    = os.getenv("CLOUDINARY_KEY")
CLOUDINARY_SECRET = os.getenv("CLOUDINARY_SECRET")

PORT = int(os.environ.get("PORT", 5000))

# ─── MONGODB ───
try:
    client = MongoClient(MONGO_URI, connectTimeoutMS=5000, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db           = client["sahu_vastra_bhandar"]
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

# ─── STATIC ───
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

# ─── AUTH ───
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    clean_expired()
    mobile = request.json.get("mobile")
    if not mobile:
        return jsonify({"success": False, "message": "Mobile number required"}), 400
    otp = generate_otp()
    otp_store[mobile] = {"otp": otp, "expiresAt": time.time() + 300}
    send_sms(mobile, otp)
    print(f"OTP for {mobile}: {otp}")  # visible in Render logs for debugging
    return jsonify({"success": True, "message": "OTP sent successfully!"})

@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    mobile = request.json.get("mobile")
    otp    = request.json.get("otp")

    record = otp_store.get(mobile)
    if not record or record["otp"] != str(otp):
        return jsonify({"success": False, "message": "Invalid or expired OTP"}), 400

    if record["expiresAt"] < time.time():
        return jsonify({"success": False, "message": "OTP has expired"}), 400

    del otp_store[mobile]

    users_col.update_one(
        {"mobile": mobile},
        {"$set": {"mobile": mobile, "role": "customer", "lastLogin": time.time()}},
        upsert=True
    )
    return jsonify({
        "success": True,
        "message": "Login successful!",
        "user": {"mobile": mobile, "role": "customer", "isAdmin": False}
    })

@app.route("/api/admin-login", methods=["POST"])
def admin_login():
    mobile   = request.json.get("mobile")
    password = request.json.get("password")
    if mobile == ADMIN_MOBILE and password == ADMIN_PASSWORD:
        return jsonify({
            "success": True,
            "message": "Admin login successful!",
            "user": {"mobile": mobile, "role": "admin", "isAdmin": True}
        })
    return jsonify({"success": False, "message": "Invalid admin credentials"}), 401

# ─── PRODUCTS ───
@app.route("/api/products", methods=["GET"])
def get_products():
    try:
        docs = list(products_col.find())
        return jsonify({"success": True, "products": [serialize(d) for d in docs]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/products", methods=["POST"])
def add_product():
    try:
        body = request.json
        result = products_col.insert_one(body)
        body["_id"] = str(result.inserted_id)
        return jsonify({"success": True, "product": body})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/products/<id>", methods=["PUT"])
def update_product(id):
    try:
        body = request.json
        body.pop("_id", None)
        products_col.update_one({"_id": ObjectId(id)}, {"$set": body})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/products/<id>", methods=["DELETE"])
def delete_product(id):
    try:
        products_col.delete_one({"_id": ObjectId(id)})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ─── UPLOAD ───
@app.route("/api/upload-image", methods=["POST"])
def upload_image():
    try:
        data_url = request.json.get("dataUrl")
        result   = cloudinary.uploader.upload(data_url, folder="sahu_vastra_bhandar/photos")
        return jsonify({"success": True, "url": result["secure_url"], "publicId": result["public_id"]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/upload-video", methods=["POST"])
def upload_video():
    try:
        data_url = request.json.get("dataUrl")
        result   = cloudinary.uploader.upload(data_url, resource_type="video", folder="sahu_vastra_bhandar/videos")
        return jsonify({"success": True, "url": result["secure_url"], "publicId": result["public_id"]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ─── ORDERS ───
@app.route("/api/orders", methods=["POST"])
def place_order():
    try:
        body = request.json
        body["orderId"]   = generate_order_id()
        body["status"]    = "placed"
        body["createdAt"] = time.time()
        orders_col.insert_one(body)
        return jsonify({"success": True, "orderId": body["orderId"]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/orders", methods=["GET"])
def get_orders():
    try:
        docs = list(orders_col.find().sort("createdAt", -1))
        return jsonify({"success": True, "orders": [serialize(d) for d in docs]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/orders/<order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    try:
        status = request.json.get("status")
        orders_col.update_one({"orderId": order_id}, {"$set": {"status": status}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ─── CUSTOMERS ───
@app.route("/api/customers", methods=["GET"])
def get_customers():
    try:
        customers = list(users_col.find())
        result = []
        for c in customers:
            mobile      = c.get("mobile")
            order_count = orders_col.count_documents({"mobile": mobile})
            orders      = list(orders_col.find({"mobile": mobile}))
            total_spent = sum(o.get("total", 0) for o in orders)
            result.append({
                "mobile":     mobile,
                "role":       c.get("role", "customer"),
                "lastLogin":  c.get("lastLogin"),
                "orderCount": order_count,
                "totalSpent": total_spent
            })
        return jsonify({"success": True, "customers": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ─── RUN ───
if __name__ == "__main__":
    print(f"Running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)

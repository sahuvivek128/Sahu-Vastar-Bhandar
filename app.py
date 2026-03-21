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

# ─── CONFIG ─── (replace these with your actual values)
FAST2SMS_API_KEY  = "DWSF6crmIfy0oGvJub7xDQv2FZqeJYBhrEWVBbt0Ltrviwi6WHK4tmNKen7C"
ADMIN_MOBILE      = "8948815093"
ADMIN_PASSWORD    = "admin@svb123"

MONGO_URI         = "mongodb+srv://sahuvivek128_db_user:tfFdor05dR3BJPPV@sahu128.rprem98.mongodb.net/?appName=SAHU128"   # e.g. mongodb+srv://user:pass@cluster.mongodb.net/
CLOUDINARY_CLOUD  = "dstvuwvoi"
CLOUDINARY_KEY    = "752152349487326"
CLOUDINARY_SECRET = "7hPOva3QCBilzoUv9woEJzBPIP0"

PORT = 5000

# ─── MONGODB ───
client = MongoClient(MONGO_URI)
db     = client["sahu_vastra_bhandar"]

users_col    = db["users"]
products_col = db["products"]
orders_col   = db["orders"]

# ─── CLOUDINARY ───
cloudinary.config(
    cloud_name = CLOUDINARY_CLOUD,
    api_key    = CLOUDINARY_KEY,
    api_secret = CLOUDINARY_SECRET
)

# ─── OTP STORE (in-memory is fine — OTPs are short-lived) ───
otp_store = {}

# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────
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
    r = requests.post("https://www.fast2sms.com/dev/bulkV2", json=payload, headers=headers)
    return r.json()

def serialize(doc):
    """Convert MongoDB _id to string so we can return it as JSON."""
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc

# ──────────────────────────────────────────────────────────────
# STATIC
# ──────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

# ──────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    clean_expired()
    mobile = request.json.get("mobile")
    if not mobile:
        return jsonify({"success": False, "message": "Mobile required"}), 400

    otp = generate_otp()
    otp_store[mobile] = {"otp": otp, "expiresAt": time.time() + 300, "attempts": 0}

    try:
        data = send_sms(mobile, otp)
        if data.get("return") == True:
            return jsonify({"success": True, "message": "OTP sent"})
        else:
            del otp_store[mobile]
            return jsonify({"success": False, "message": "SMS failed"}), 500
    except Exception as e:
        del otp_store[mobile]
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    mobile = request.json.get("mobile")
    otp    = request.json.get("otp")
    record = otp_store.get(mobile)

    if not record:
        return jsonify({"success": False, "message": "No OTP found"}), 400
    if record["expiresAt"] < time.time():
        del otp_store[mobile]
        return jsonify({"success": False, "message": "OTP expired"}), 400

    record["attempts"] += 1
    if record["attempts"] > 5:
        del otp_store[mobile]
        return jsonify({"success": False, "message": "Too many attempts"}), 429
    if record["otp"] != str(otp):
        return jsonify({"success": False, "message": "Wrong OTP"}), 400

    del otp_store[mobile]
    is_admin = (mobile == ADMIN_MOBILE)

    # ── Save / update user in DB ──
    users_col.update_one(
        {"mobile": mobile},
        {"$set": {
            "mobile":    mobile,
            "role":      "admin" if is_admin else "customer",
            "lastLogin": time.time()
        }},
        upsert=True
    )

    return jsonify({
        "success": True,
        "message": "Login successful",
        "user": {
            "mobile":  mobile,
            "role":    "admin" if is_admin else "customer",
            "isAdmin": is_admin
        }
    })

@app.route("/api/admin-login", methods=["POST"])
def admin_login():
    mobile   = request.json.get("mobile")
    password = request.json.get("password")

    if mobile != ADMIN_MOBILE:
        return jsonify({"success": False, "message": "Invalid admin mobile"}), 401
    if password != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Wrong password"}), 401

    users_col.update_one(
        {"mobile": mobile},
        {"$set": {"mobile": mobile, "role": "admin", "lastLogin": time.time()}},
        upsert=True
    )

    return jsonify({
        "success": True,
        "role": "admin",
        "user": {"mobile": mobile, "role": "admin", "isAdmin": True}
    })

# ──────────────────────────────────────────────────────────────
# CLOUDINARY — UPLOAD IMAGE
# ──────────────────────────────────────────────────────────────
@app.route("/api/upload-image", methods=["POST"])
def upload_image():
    """
    Accepts a base64 data-URL (from the frontend FileReader) and
    uploads it to Cloudinary.  Returns the secure URL.
    """
    data_url = request.json.get("dataUrl")
    folder   = request.json.get("folder", "sahu_vastra_bhandar/products")

    if not data_url:
        return jsonify({"success": False, "message": "No image data"}), 400

    try:
        result = cloudinary.uploader.upload(data_url, folder=folder)
        return jsonify({
            "success": True,
            "url":     result["secure_url"],
            "publicId": result["public_id"]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/upload-video", methods=["POST"])
def upload_video():
    """Upload a video file (base64 data-URL) to Cloudinary."""
    data_url = request.json.get("dataUrl")
    folder   = request.json.get("folder", "sahu_vastra_bhandar/videos")

    if not data_url:
        return jsonify({"success": False, "message": "No video data"}), 400

    try:
        result = cloudinary.uploader.upload(
            data_url,
            resource_type="video",
            folder=folder
        )
        return jsonify({
            "success":  True,
            "url":      result["secure_url"],
            "publicId": result["public_id"]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ──────────────────────────────────────────────────────────────
# PRODUCTS
# ──────────────────────────────────────────────────────────────
@app.route("/api/products", methods=["GET"])
def get_products():
    """Return all products (newest first)."""
    docs = list(products_col.find().sort("ts", -1))
    return jsonify({"success": True, "products": [serialize(d) for d in docs]})

@app.route("/api/products", methods=["POST"])
def add_product():
    """
    Add a new product.
    Frontend sends product data; photos/video are already uploaded
    to Cloudinary and come in as URL strings.
    """
    body = request.json
    if not body.get("name") or not body.get("orig"):
        return jsonify({"success": False, "message": "Name and price required"}), 400

    doc = {
        "name":      body["name"],
        "desc":      body.get("desc", ""),
        "orig":      float(body["orig"]),
        "sale":      float(body["sale"]) if body.get("sale") else None,
        "cat":       body.get("cat", ""),
        "color":     body.get("color", "").lower().strip(),
        "badge":     body.get("badge", ""),
        "available": body.get("available", True),
        "rating":    float(body.get("rating", 0)),
        "reviews":   int(body.get("reviews", 0)),
        # photos = list of { url, publicId }
        "photos":    body.get("photos", []),
        # video  = { url, publicId, name, size } or None
        "video":     body.get("video", None),
        "ts":        int(time.time() * 1000)
    }

    result = products_col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return jsonify({"success": True, "product": doc}), 201

@app.route("/api/products/<product_id>", methods=["PUT"])
def update_product(product_id):
    body = request.json
    try:
        oid = ObjectId(product_id)
    except Exception:
        return jsonify({"success": False, "message": "Invalid ID"}), 400

    update = {
        "name":      body["name"],
        "desc":      body.get("desc", ""),
        "orig":      float(body["orig"]),
        "sale":      float(body["sale"]) if body.get("sale") else None,
        "cat":       body.get("cat", ""),
        "color":     body.get("color", "").lower().strip(),
        "badge":     body.get("badge", ""),
        "available": body.get("available", True),
        "rating":    float(body.get("rating", 0)),
        "reviews":   int(body.get("reviews", 0)),
        "photos":    body.get("photos", []),
        "video":     body.get("video", None),
    }

    products_col.update_one({"_id": oid}, {"$set": update})
    updated = products_col.find_one({"_id": oid})
    return jsonify({"success": True, "product": serialize(updated)})

@app.route("/api/products/<product_id>", methods=["DELETE"])
def delete_product(product_id):
    try:
        oid = ObjectId(product_id)
    except Exception:
        return jsonify({"success": False, "message": "Invalid ID"}), 400

    products_col.delete_one({"_id": oid})
    return jsonify({"success": True, "message": "Deleted"})

# ──────────────────────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────────────────────
@app.route("/api/orders", methods=["POST"])
def place_order():
    """Called from frontend when payment completes."""
    body = request.json
    if not body.get("mobile") or not body.get("items"):
        return jsonify({"success": False, "message": "mobile and items required"}), 400

    order_id = "SVB" + str(int(time.time() * 1000))[-8:]

    doc = {
        "orderId":    order_id,
        "mobile":     body["mobile"],
        "items":      body["items"],       # [{id, name, price, photo_url}]
        "total":      float(body.get("total", 0)),
        "payMethod":  body.get("payMethod", ""),
        "status":     "placed",
        "createdAt":  int(time.time() * 1000)
    }

    orders_col.insert_one(doc)
    doc["_id"] = str(doc["_id"])
    return jsonify({"success": True, "orderId": order_id, "order": doc}), 201

@app.route("/api/orders", methods=["GET"])
def get_orders():
    """Admin: get all orders, newest first."""
    mobile = request.args.get("mobile")   # optional filter by customer
    query  = {"mobile": mobile} if mobile else {}
    docs   = list(orders_col.find(query).sort("createdAt", -1))
    return jsonify({"success": True, "orders": [serialize(d) for d in docs]})

@app.route("/api/orders/<order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    """Admin: update order status (placed → confirmed → shipped → delivered)."""
    status = request.json.get("status")
    orders_col.update_one({"orderId": order_id}, {"$set": {"status": status}})
    return jsonify({"success": True})

# ──────────────────────────────────────────────────────────────
# CUSTOMERS
# ──────────────────────────────────────────────────────────────
@app.route("/api/customers", methods=["GET"])
def get_customers():
    """Admin: return all customers with their order count and total spent."""
    customers = list(users_col.find({"role": "customer"}).sort("lastLogin", -1))
    # Annotate with order stats
    result = []
    for c in customers:
        mobile = c["mobile"]
        order_list   = list(orders_col.find({"mobile": mobile}))
        total_spent  = sum(o.get("total", 0) for o in order_list)
        c["orderCount"]  = len(order_list)
        c["totalSpent"]  = total_spent
        c["lastLogin"]   = c.get("lastLogin", 0)
        result.append(serialize(c))
    return jsonify({"success": True, "customers": result})

# ──────────────────────────────────────────────────────────────
# HEALTH
# ──────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    try:
        client.server_info()
        return jsonify({"status": "ok", "db": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "db": str(e)}), 500

if __name__ == "__main__":
    print("✅ Sahu Vastra Bhandar — Flask + MongoDB + Cloudinary")
    print(f"   Running at http://localhost:{PORT}")
    app.run(port=PORT, debug=True)

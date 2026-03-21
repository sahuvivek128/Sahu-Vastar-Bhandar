
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import random
import time

app = Flask(__name__, static_folder=".")
CORS(app)

FAST2SMS_API_KEY = "PASTE_YOUR_FAST2SMS_API_KEY"
ADMIN_MOBILE = "8948815093"
ADMIN_PASSWORD = "admin@svb123"

PORT = 3000
otp_store = {}

def generate_otp():
    return str(random.randint(100000,999999))

def clean_expired():
    now = time.time()
    for m in list(otp_store.keys()):
        if otp_store[m]["expiresAt"] < now:
            del otp_store[m]

def send_sms(mobile, otp):
    message = f"Your OTP for Sahu Vastra Bhandar is {otp}. Valid for 5 minutes."
    payload = {
        "route":"q",
        "message":message,
        "language":"english",
        "flash":0,
        "numbers":mobile
    }
    headers = {
        "authorization":FAST2SMS_API_KEY,
        "Content-Type":"application/json"
    }
    r = requests.post("https://www.fast2sms.com/dev/bulkV2", json=payload, headers=headers)
    return r.json()

@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    clean_expired()
    mobile = request.json.get("mobile")
    if not mobile:
        return jsonify({"success":False,"message":"Mobile required"}),400

    otp = generate_otp()
    otp_store[mobile] = {"otp":otp,"expiresAt":time.time()+300,"attempts":0}

    try:
        data = send_sms(mobile, otp)
        if data.get("return")==True:
            return jsonify({"success":True,"message":"OTP sent"})
        else:
            del otp_store[mobile]
            return jsonify({"success":False,"message":"SMS failed"}),500
    except Exception as e:
        del otp_store[mobile]
        return jsonify({"success":False,"message":str(e)}),500

@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    mobile = request.json.get("mobile")
    otp = request.json.get("otp")

    record = otp_store.get(mobile)
    if not record:
        return jsonify({"success":False,"message":"No OTP found"}),400

    if record["expiresAt"] < time.time():
        del otp_store[mobile]
        return jsonify({"success":False,"message":"OTP expired"}),400

    record["attempts"] += 1
    if record["attempts"] > 5:
        del otp_store[mobile]
        return jsonify({"success":False,"message":"Too many attempts"}),429

    if record["otp"] != str(otp):
        return jsonify({"success":False,"message":"Wrong OTP"}),400

    del otp_store[mobile]
    is_admin = mobile == ADMIN_MOBILE

    return jsonify({
        "success":True,
        "user":{
            "mobile":mobile,
            "role":"admin" if is_admin else "customer",
            "isAdmin":is_admin
        }
    })

@app.route("/api/admin-login", methods=["POST"])
def admin_login():
    mobile = request.json.get("mobile")
    password = request.json.get("password")

    if mobile != ADMIN_MOBILE:
        return jsonify({"success":False,"message":"Invalid admin mobile"}),401

    if password != ADMIN_PASSWORD:
        return jsonify({"success":False,"message":"Wrong password"}),401

    return jsonify({"success":True,"role":"admin"})

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    print("Server running at http://localhost:3000")
    app.run(port=PORT, debug=True)

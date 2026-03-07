# Sahu Vastra Bhandar — Setup Guide
## Real OTP Login via Fast2SMS

---

## Files in this folder
| File | Purpose |
|------|---------|
| `index.html` | Your full website (open in browser) |
| `server.js` | Backend server that sends real OTPs |
| `package.json` | Node.js dependencies |

---

## Step-by-Step Setup

### 1. Install Node.js
Download and install from: https://nodejs.org (choose LTS version)

### 2. Get Fast2SMS API Key (Free)
1. Go to https://www.fast2sms.com
2. Click **Sign Up** → register with your mobile number
3. After login, go to **Dev API** section
4. Copy your **API Key** (looks like: abcXYZ1234567890...)
5. New accounts get free credits to test

### 3. Configure Your API Key
Open `server.js` in Notepad or any text editor.
Find this line:
```
const FAST2SMS_API_KEY = 'YOUR_FAST2SMS_API_KEY';
```
Replace `YOUR_FAST2SMS_API_KEY` with your actual key. Example:
```
const FAST2SMS_API_KEY = 'abcXYZ1234567890yourActualKey';
```

### 4. Set Admin Mobile Number
In `server.js`, find:
```
const ADMIN_MOBILE = '9999999999';
```
Change `9999999999` to YOUR mobile number (the shopkeeper's number).
This number will get Admin access to upload/manage sarees.

### 5. Install & Run the Server
Open **Command Prompt** (Windows) or **Terminal** (Mac) in this folder:
```
npm install
node server.js
```
You should see:
```
╔══════════════════════════════════════════════╗
║   Sahu Vastra Bhandar — Server Started 🪡    ║
║   Running at: http://localhost:3000           ║
╚══════════════════════════════════════════════╝
```

### 6. Open the Website
Open `index.html` in your browser, OR go to:
```
http://localhost:3000
```

---

## How Login Works
1. Customer enters their **10-digit mobile number**
2. They click **Send OTP**
3. Fast2SMS sends a **real 6-digit SMS** to their phone
4. Customer enters the OTP → they're logged in
5. OTP expires in **5 minutes**
6. Wrong OTP is allowed max **5 attempts**

## Admin Login
- Enter the mobile number you set as `ADMIN_MOBILE` in server.js
- Receive the OTP on that phone
- Login → you'll see the Admin panel to upload sarees

---

## Keeping Server Running (24/7)
For permanent hosting, install PM2:
```
npm install -g pm2
pm2 start server.js --name "svb-server"
pm2 save
pm2 startup
```

---

## Fast2SMS Pricing (approx)
- ₹0.18 - ₹0.25 per OTP SMS
- 100 free SMS on signup
- Recharge at fast2sms.com → Wallet

---

## Troubleshooting
| Problem | Fix |
|---------|-----|
| "Cannot connect to server" | Make sure `node server.js` is running |
| OTP not received | Check Fast2SMS wallet balance & API key |
| "Invalid mobile number" | Enter a valid Indian number starting with 6-9 |
| Port 3000 in use | Change `const PORT = 3000` in server.js to 3001 |

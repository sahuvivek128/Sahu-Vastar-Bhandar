/**
 * Sahu Vastra Bhandar — OTP Backend Server
 * Uses Fast2SMS Quick SMS route (works immediately, no DLT needed)
 */

const express = require('express');
const cors    = require('cors');
const https   = require('https');
const app     = express();

// ─── PASTE YOUR FAST2SMS API KEY HERE ───────────────────────
const FAST2SMS_API_KEY = 'DWSF6crmIfy0oGvJub7xDQv2FZqeJYBhrEWVBbt0Ltrviwi6WHK4tmNKen7C';
// ────────────────────────────────────────────────────────────

// ─── YOUR SHOPKEEPER MOBILE (gets Admin access) ─────────────
const ADMIN_MOBILE = '8948815093';
// ────────────────────────────────────────────────────────────

const PORT = 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

const otpStore = {};

function generateOTP() {
  return String(Math.floor(100000 + Math.random() * 900000));
}

function cleanExpired() {
  const now = Date.now();
  for (const mob in otpStore) {
    if (otpStore[mob].expiresAt < now) delete otpStore[mob];
  }
}

// ── Send OTP via Fast2SMS Quick SMS route ──
function sendSMS(mobile, otp) {
  return new Promise((resolve, reject) => {

    const message = `Your OTP for Sahu Vastra Bhandar is ${otp}. Valid for 5 minutes. Do not share.`;

    const postData = JSON.stringify({
      route: 'q',
      message: message,
      language: 'english',
      flash: 0,
      numbers: mobile
    });

    const options = {
      hostname: 'www.fast2sms.com',
      path: '/dev/bulkV2',
      method: 'POST',
      headers: {
        'authorization': FAST2SMS_API_KEY,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
        'cache-control': 'no-cache'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error('Bad response: ' + data)); }
      });
    });

    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

// ── POST /api/send-otp ──
app.post('/api/send-otp', async (req, res) => {
  cleanExpired();
  const { mobile } = req.body;

  if (!mobile || !/^[6-9]\d{9}$/.test(mobile)) {
    return res.status(400).json({ success: false, message: 'Invalid mobile number. Enter a valid 10-digit Indian number.' });
  }

  const otp = generateOTP();
  otpStore[mobile] = { otp, expiresAt: Date.now() + 5 * 60 * 1000, attempts: 0 };
  console.log(`\n📤 Sending OTP [${otp}] to ${mobile}...`);

  try {
    const data = await sendSMS(mobile, otp);
    console.log('Fast2SMS response:', JSON.stringify(data));

    if (data.return === true) {
      console.log(`✅ OTP sent successfully to ${mobile}`);
      return res.json({ success: true, message: `OTP sent to +91 ${mobile}` });
    } else {
      delete otpStore[mobile];
      const msg = data.message
        ? (Array.isArray(data.message) ? data.message.join(' ') : String(data.message))
        : 'Failed to send OTP.';
      console.error('❌ Fast2SMS said:', msg);
      return res.status(500).json({ success: false, message: 'SMS Error: ' + msg });
    }
  } catch (err) {
    console.error('❌ Error:', err.message);
    delete otpStore[mobile];
    return res.status(500).json({ success: false, message: 'Network error: ' + err.message });
  }
});

// ── POST /api/verify-otp ──
app.post('/api/verify-otp', (req, res) => {
  const { mobile, otp } = req.body;
  if (!mobile || !otp) return res.status(400).json({ success: false, message: 'Mobile and OTP are required.' });

  const record = otpStore[mobile];
  if (!record) return res.status(400).json({ success: false, message: 'No OTP found. Please request a new OTP.' });
  if (record.expiresAt < Date.now()) {
    delete otpStore[mobile];
    return res.status(400).json({ success: false, message: 'OTP expired. Please request a new one.' });
  }
  record.attempts += 1;
  if (record.attempts > 5) {
    delete otpStore[mobile];
    return res.status(429).json({ success: false, message: 'Too many wrong attempts. Request a new OTP.' });
  }
  if (record.otp !== String(otp)) {
    const left = 5 - record.attempts;
    return res.status(400).json({ success: false, message: `Wrong OTP. ${left} attempt${left !== 1 ? 's' : ''} remaining.` });
  }

  delete otpStore[mobile];
  const isAdmin = mobile === ADMIN_MOBILE;
  console.log(`✅ Login verified: ${mobile} (${isAdmin ? 'ADMIN' : 'Customer'})`);
  return res.json({
    success: true,
    message: 'Login successful!',
    user: { mobile, isAdmin, role: isAdmin ? 'admin' : 'customer' }
  });
});

app.get('/api/health', (req, res) => res.json({ status: 'ok' }));

app.listen(PORT, () => {
  console.log('\n╔══════════════════════════════════════════════╗');
  console.log('║   Sahu Vastra Bhandar — Server Started 🪡    ║');
  console.log(`║   Open: http://localhost:${PORT}                ║`);
  console.log('╚══════════════════════════════════════════════╝\n');
  if (FAST2SMS_API_KEY === 'YOUR_FAST2SMS_API_KEY') {
    console.log('⚠️  Add your Fast2SMS API key in server.js!\n');
  } else {
    console.log(`✅ API key set. Admin: ${ADMIN_MOBILE}`);
    console.log(`✅ Using Quick SMS route\n`);
  }
});

// ══════════════════════════════════════════════════
//  POST /api/admin-login  (mobile + password)
// ══════════════════════════════════════════════════
// Set your admin password below
const ADMIN_PASSWORD = 'admin@svb123';   // ← CHANGE THIS to a strong password

app.post('/api/admin-login', (req, res) => {
  const { mobile, password } = req.body;

  if (!mobile || !password) {
    return res.status(400).json({ success: false, message: 'Mobile and password are required.' });
  }

  if (mobile !== ADMIN_MOBILE) {
    return res.status(401).json({ success: false, message: 'Invalid admin mobile number.' });
  }

  if (password !== ADMIN_PASSWORD) {
    return res.status(401).json({ success: false, message: 'Wrong password. Please try again.' });
  }

  console.log(`✅ Admin login: ${mobile}`);
  return res.json({
    success: true,
    message: 'Admin login successful!',
    user: { mobile, isAdmin: true, role: 'admin' }
  });
});

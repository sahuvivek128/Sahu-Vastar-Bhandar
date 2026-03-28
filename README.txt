============================================================
  Sahu Vastra Bhandar — Full Stack Setup Guide
============================================================

STACK
-----
  Frontend  : index.html  (vanilla JS, no framework)
  Backend   : app.py      (Flask, Python)
  Database  : MongoDB Atlas (cloud, free tier)
  Images    : Cloudinary  (free tier, 25 GB storage)
  SMS OTP   : Fast2SMS


STEP 1 — Install dependencies
------------------------------
  pip install -r requirements.txt


STEP 2 — MongoDB Atlas
-----------------------
  1. Go to https://mongodb.com/atlas → Sign up free
  2. Create a cluster → Click "Connect"
  3. Choose "Connect your application" → copy the URI
     e.g.  mongodb+srv://user:pass@cluster0.xxxx.mongodb.net/
  4. Paste it in app.py:
       MONGO_URI = "mongodb+srv://..."


STEP 3 — Cloudinary
---------------------
  1. Go to https://cloudinary.com → Sign up free
  2. Dashboard shows: Cloud Name, API Key, API Secret
  3. Paste in app.py:
       CLOUDINARY_CLOUD  = "your_cloud_name"
       CLOUDINARY_KEY    = "your_api_key"
       CLOUDINARY_SECRET = "your_api_secret"


STEP 4 — Fast2SMS (already configured)
----------------------------------------
  The FAST2SMS_API_KEY in app.py is already set.
  Change it if you want to use your own account.


STEP 5 — Run the server
------------------------
  python app.py

  Server runs at: http://localhost:5000
  Open index.html in your browser (or visit http://localhost:5000)


FEATURES
---------
  ✅ OTP login via SMS (customers)
  ✅ Admin login with ID + password
  ✅ Add / Edit / Delete sarees (admin)
  ✅ Photo upload → stored on Cloudinary, URL saved to MongoDB
  ✅ Video upload → stored on Cloudinary
  ✅ Orders saved to MongoDB on every payment
  ✅ Admin panel: Sarees tab, Orders tab, Customers tab
  ✅ Order status management (Placed / Confirmed / Shipped / Delivered)
  ✅ Customer list with order count and total spent


API ENDPOINTS
--------------
  GET    /api/products              — All products
  POST   /api/products              — Add product (admin)
  PUT    /api/products/<id>         — Edit product (admin)
  DELETE /api/products/<id>         — Delete product (admin)

  POST   /api/upload-image          — Upload photo to Cloudinary
  POST   /api/upload-video          — Upload video to Cloudinary

  POST   /api/orders                — Place order (on payment)
  GET    /api/orders                — All orders (admin)
  PUT    /api/orders/<id>/status    — Update order status (admin)

  GET    /api/customers             — All customers with stats (admin)

  POST   /api/send-otp              — Send OTP via SMS
  POST   /api/verify-otp            — Verify OTP
  POST   /api/admin-login           — Admin password login
  GET    /api/health                — DB connection check


ADMIN CREDENTIALS
------------------
  Mobile   : 8948815093
  Password : admin@svb123


IMPORTANT NOTES
----------------
  - Photos and videos are uploaded to Cloudinary BEFORE saving the product.
    You will see a progress bar while uploading.
  - Products and orders persist in MongoDB permanently.
  - Cart is still stored in localStorage (per browser, intentional).
  - Never commit app.py with real API keys to a public git repo.
    Use environment variables for production.

============================================================

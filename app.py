"""
JuiceFront - Fresh Juice Delivered
Airbnb-style marketplace for fresh juice in Nansana, Uganda.

Roles:
  - public:   browse vendors, place orders (no login)
  - vendor:   manage own profile, juices, and view own orders
  - operator: full admin access - all orders, statuses, revenue
"""
import os
import sqlite3
import time
import uuid
from datetime import datetime, date
from functools import wraps

from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# ---------- Config ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "juicefront.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "vendors")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB

SERVICE_FEE = int(os.getenv("SERVICE_FEE", "300"))  # UGX

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

# ---------- Database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        photo TEXT DEFAULT '',       -- filename in static/uploads/vendors/
        phone TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS juices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        price INTEGER NOT NULL,      -- UGX
        active INTEGER DEFAULT 1,
        FOREIGN KEY(vendor_id) REFERENCES vendors(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,          -- 'operator' | 'vendor'
        vendor_id INTEGER,
        FOREIGN KEY(vendor_id) REFERENCES vendors(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id INTEGER NOT NULL,
        vendor_name TEXT NOT NULL,
        juice_id INTEGER,
        juice_name TEXT NOT NULL,
        juice_price INTEGER NOT NULL,
        service_fee INTEGER NOT NULL,
        total INTEGER NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        customer_location TEXT NOT NULL,
        note TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Pending',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS login_attempts (
        ip TEXT PRIMARY KEY,
        fails INTEGER DEFAULT 0,
        locked_until INTEGER DEFAULT 0
    );
    """)
    conn.commit()

    # Seed vendors + juices only if empty
    if c.execute("SELECT COUNT(*) FROM vendors").fetchone()[0] == 0:
        seed = [
            ("Mama Sarah Juices", "Fresh tropical blends from Nansana market.", "0700000001",
             [("Mango Passion", 3000), ("Pineapple Ginger", 2500), ("Watermelon Mint", 2000)]),
            ("Green Leaf Naturals", "100% organic, no added sugar.", "0700000002",
             [("Avocado Smoothie", 4000), ("Beetroot Boost", 3500), ("Green Detox", 3500)]),
            ("Tropical Squeeze", "Cold-pressed daily.", "0700000003",
             [("Orange Fresh", 2500), ("Passion Fruit", 3000), ("Guava Delight", 2500)]),
            ("Nansana Fresh Co.", "Local fruits, local prices.", "0700000004",
             [("Sugarcane Juice", 1500), ("Tamarind Cooler", 2000), ("Jackfruit Blend", 3500)]),
            ("Kampala Juice Bar", "Premium blends, delivered cold.", "0700000005",
             [("Berry Mix", 4500), ("Tropical Sunrise", 4000), ("Mango Lassi", 3500)]),
            ("Fruit Basket Uganda", "Family-run since 2015.", "0700000006",
             [("Pineapple Passion", 3000), ("Watermelon Fresh", 2000), ("Mixed Fruit", 3500)]),
        ]
        for name, desc, phone, juices in seed:
            c.execute("INSERT INTO vendors (name, description, phone) VALUES (?,?,?)",
                      (name, desc, phone))
            vid = c.lastrowid
            for jn, jp in juices:
                c.execute("INSERT INTO juices (vendor_id, name, price) VALUES (?,?,?)",
                          (vid, jn, jp))

    # Seed users
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        op_pw = os.getenv("OPERATOR_PASSWORD", "operator123")
        v_pw = os.getenv("VENDOR_DEFAULT_PASSWORD", "vendor123")
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                  ("operator", generate_password_hash(op_pw), "operator"))
        for row in c.execute("SELECT id FROM vendors ORDER BY id").fetchall():
            c.execute("INSERT INTO users (username, password_hash, role, vendor_id) VALUES (?,?,?,?)",
                      (f"vendor{row['id']}", generate_password_hash(v_pw), "vendor", row["id"]))
    conn.commit()
    conn.close()

# ---------- Auth helpers ----------
LOCKOUT_SECONDS = 15 * 60
MAX_FAILS = 3

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("login", next=request.path))
            if role and u["role"] != role:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco

def check_lockout(ip):
    row = get_db().execute("SELECT * FROM login_attempts WHERE ip=?", (ip,)).fetchone()
    if row and row["locked_until"] > time.time():
        return int(row["locked_until"] - time.time())
    return 0

def register_fail(ip):
    db = get_db()
    row = db.execute("SELECT * FROM login_attempts WHERE ip=?", (ip,)).fetchone()
    fails = (row["fails"] if row else 0) + 1
    locked = int(time.time() + LOCKOUT_SECONDS) if fails >= MAX_FAILS else 0
    if row:
        db.execute("UPDATE login_attempts SET fails=?, locked_until=? WHERE ip=?",
                   (fails, locked, ip))
    else:
        db.execute("INSERT INTO login_attempts (ip, fails, locked_until) VALUES (?,?,?)",
                   (ip, fails, locked))
    db.commit()
    return fails

def clear_fails(ip):
    db = get_db()
    db.execute("DELETE FROM login_attempts WHERE ip=?", (ip,))
    db.commit()

# ---------- Template globals ----------
@app.context_processor
def inject_globals():
    return dict(user=current_user(), SERVICE_FEE=SERVICE_FEE, APP_NAME="JuiceFront")

# ---------- Public routes ----------
@app.route("/")
def index():
    db = get_db()
    vendors = db.execute("SELECT * FROM vendors ORDER BY id").fetchall()
    # Attach signature juice (cheapest active) for each vendor card
    cards = []
    for v in vendors:
        j = db.execute(
            "SELECT * FROM juices WHERE vendor_id=? AND active=1 ORDER BY price LIMIT 1",
            (v["id"],)).fetchone()
        cards.append({"v": v, "j": j})
    return render_template("index.html", cards=cards)

@app.route("/vendor/<int:vid>")
def vendor_detail(vid):
    db = get_db()
    v = db.execute("SELECT * FROM vendors WHERE id=?", (vid,)).fetchone()
    if not v:
        abort(404)
    juices = db.execute(
        "SELECT * FROM juices WHERE vendor_id=? AND active=1 ORDER BY name", (vid,)).fetchall()
    return render_template("vendor_detail.html", v=v, juices=juices)

@app.route("/order/<int:juice_id>", methods=["GET", "POST"])
def order_form(juice_id):
    db = get_db()
    j = db.execute("SELECT * FROM juices WHERE id=?", (juice_id,)).fetchone()
    if not j:
        abort(404)
    v = db.execute("SELECT * FROM vendors WHERE id=?", (j["vendor_id"],)).fetchone()
    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()[:100]
        phone = request.form.get("customer_phone", "").strip()[:30]
        loc = request.form.get("customer_location", "").strip()[:200]
        note = request.form.get("note", "").strip()[:500]
        if not (name and phone and loc):
            flash("Please fill in name, phone and location.", "error")
            return render_template("order_form.html", j=j, v=v)
        total = j["price"] + SERVICE_FEE
        cur = db.execute("""INSERT INTO orders
            (vendor_id, vendor_name, juice_id, juice_name, juice_price,
             service_fee, total, customer_name, customer_phone, customer_location,
             note, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (v["id"], v["name"], j["id"], j["name"], j["price"],
             SERVICE_FEE, total, name, phone, loc, note,
             "Pending", datetime.utcnow().isoformat(timespec="seconds")))
        db.commit()
        return redirect(url_for("success", order_id=cur.lastrowid))
    return render_template("order_form.html", j=j, v=v)

@app.route("/success/<int:order_id>")
def success(order_id):
    o = get_db().execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o:
        abort(404)
    return render_template("success.html", o=o)

# ---------- Auth routes ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr or "unknown"
    wait = check_lockout(ip)
    if request.method == "POST":
        if wait > 0:
            flash(f"Too many attempts. Try again in {wait//60}m {wait%60}s.", "error")
            return render_template("login.html", locked=wait)
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if row and check_password_hash(row["password_hash"], p):
            session["user_id"] = row["id"]
            clear_fails(ip)
            if row["role"] == "operator":
                return redirect(url_for("operator_dashboard"))
            return redirect(url_for("vendor_dashboard"))
        fails = register_fail(ip)
        remaining = MAX_FAILS - fails
        if remaining > 0:
            flash(f"Invalid credentials. {remaining} attempt(s) left.", "error")
        else:
            flash("Locked out for 15 minutes.", "error")
    return render_template("login.html", locked=wait)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------- Vendor dashboard ----------
def _allowed_file(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_EXT

@app.route("/vendor", methods=["GET", "POST"])
@login_required(role="vendor")
def vendor_dashboard():
    db = get_db()
    u = current_user()
    v = db.execute("SELECT * FROM vendors WHERE id=?", (u["vendor_id"],)).fetchone()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            name = request.form.get("name", "").strip()[:100] or v["name"]
            desc = request.form.get("description", "").strip()[:500]
            phone = request.form.get("phone", "").strip()[:30]
            photo_name = v["photo"] or ""
            file = request.files.get("photo")
            if file and file.filename:
                if not _allowed_file(file.filename):
                    flash("Only image files allowed (png/jpg/jpeg/webp/gif).", "error")
                    return redirect(url_for("vendor_dashboard"))
                ext = file.filename.rsplit(".", 1)[1].lower()
                photo_name = f"vendor_{v['id']}_{uuid.uuid4().hex[:8]}.{ext}"
                file.save(os.path.join(UPLOAD_DIR, secure_filename(photo_name)))
            db.execute("UPDATE vendors SET name=?, description=?, phone=?, photo=? WHERE id=?",
                       (name, desc, phone, photo_name, v["id"]))
            db.commit()
            flash("Profile updated.", "ok")
        elif action == "add_juice":
            n = request.form.get("juice_name", "").strip()[:100]
            try:
                p = int(request.form.get("juice_price", "0"))
            except ValueError:
                p = 0
            if n and p > 0:
                db.execute("INSERT INTO juices (vendor_id, name, price) VALUES (?,?,?)",
                           (v["id"], n, p))
                db.commit()
                flash("Juice added.", "ok")
            else:
                flash("Enter valid name and price.", "error")
        elif action == "edit_juice":
            jid = int(request.form.get("juice_id", "0"))
            n = request.form.get("juice_name", "").strip()[:100]
            try:
                p = int(request.form.get("juice_price", "0"))
            except ValueError:
                p = 0
            active = 1 if request.form.get("active") == "on" else 0
            db.execute("UPDATE juices SET name=?, price=?, active=? WHERE id=? AND vendor_id=?",
                       (n, p, active, jid, v["id"]))
            db.commit()
            flash("Juice updated.", "ok")
        elif action == "delete_juice":
            jid = int(request.form.get("juice_id", "0"))
            db.execute("DELETE FROM juices WHERE id=? AND vendor_id=?", (jid, v["id"]))
            db.commit()
            flash("Juice deleted.", "ok")
        return redirect(url_for("vendor_dashboard"))

    juices = db.execute("SELECT * FROM juices WHERE vendor_id=? ORDER BY name",
                        (v["id"],)).fetchall()
    orders = db.execute("SELECT * FROM orders WHERE vendor_id=? ORDER BY id DESC",
                        (v["id"],)).fetchall()
    return render_template("vendor_dashboard.html", v=v, juices=juices, orders=orders)

# ---------- Operator dashboard ----------
STATUSES = ["Pending", "Preparing", "On the Way", "Delivered", "Cancelled"]

@app.route("/operator", methods=["GET", "POST"])
@login_required(role="operator")
def operator_dashboard():
    db = get_db()
    if request.method == "POST":
        oid = int(request.form.get("order_id", "0"))
        new_status = request.form.get("status", "")
        if new_status in STATUSES:
            db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, oid))
            db.commit()
        return redirect(url_for("operator_dashboard"))

    orders = db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    today = date.today().isoformat()
    todays = [o for o in orders if o["created_at"].startswith(today) and o["status"] != "Cancelled"]
    revenue_gross = sum(o["total"] for o in todays)
    revenue_fees = sum(o["service_fee"] for o in todays)
    return render_template("operator_dashboard.html", orders=orders, statuses=STATUSES,
                           revenue_gross=revenue_gross, revenue_fees=revenue_fees,
                           todays_count=len(todays))

@app.route("/orders")
@login_required(role="operator")
def orders_all():
    orders = get_db().execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return render_template("orders.html", orders=orders)

# ---------- Errors ----------
@app.errorhandler(403)
def e403(e): return render_template("error.html", code=403, msg="Forbidden"), 403
@app.errorhandler(404)
def e404(e): return render_template("error.html", code=404, msg="Not found"), 404
@app.errorhandler(413)
def e413(e):
    flash("File too large. Max 2MB.", "error")
    return redirect(request.referrer or url_for("index"))

# ---------- Bootstrap ----------
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("DEBUG", "False").lower() == "true")

"""
JuiceFront — Fresh Juice Delivered (Nansana, Uganda)
A tiny Flask app: browse juice vendors, place an order, staff manage orders.
Educational and minimal — every important line is commented.
"""

import os
import sqlite3
import time
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, abort, flash
)

# ---------- Config ----------
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-change-me")
DB_PATH = os.path.join(os.path.dirname(__file__), "juice.db")
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD")  # required for /orders and /operator
SERVICE_FEE = 300  # UGX flat delivery/service fee

# ---------- Vendor catalog (hardcoded, easy to edit) ----------
VENDORS = [
    {
        "id": 1,
        "name": "Mama Nansana Juices",
        "juice": "Fresh Passion Fruit",
        "price": 3000,
        "description": "Hand-squeezed passion fruit juice, no sugar added. Sweet, tangy, and cold.",
        "photo": "https://images.unsplash.com/photo-1546173159-315724a31696?w=800",
    },
    {
        "id": 2,
        "name": "Kabuye Fresh",
        "juice": "Mango Madness",
        "price": 2500,
        "description": "Ripe local mangoes blended fresh every morning. Thick and creamy.",
        "photo": "https://images.unsplash.com/photo-1600271886742-f049cd451bba?w=800",
    },
    {
        "id": 3,
        "name": "Green Leaf Co.",
        "juice": "Watermelon Cooler",
        "price": 2000,
        "description": "Ice-cold watermelon juice with a hint of lime. Perfect for hot afternoons.",
        "photo": "https://images.unsplash.com/photo-1587691592099-24045742c181?w=800",
    },
    {
        "id": 4,
        "name": "Patricia's Blends",
        "juice": "Pineapple & Ginger",
        "price": 3500,
        "description": "Zesty pineapple with a spicy ginger kick. Locally sourced, freshly pressed.",
        "photo": "https://images.unsplash.com/photo-1622597467836-f3e6707e1191?w=800",
    },
    {
        "id": 5,
        "name": "Sunrise Juicery",
        "juice": "Orange Sunrise",
        "price": 2500,
        "description": "Sweet Ugandan oranges, cold pressed. Bright, fresh, and full of vitamin C.",
        "photo": "https://images.unsplash.com/photo-1613478223719-2ab802602423?w=800",
    },
    {
        "id": 6,
        "name": "Tropicana Nansana",
        "juice": "Avocado Smoothie",
        "price": 4000,
        "description": "Creamy avocado smoothie with milk and honey. Filling and delicious.",
        "photo": "https://images.unsplash.com/photo-1623065422902-30a2d299bbe4?w=800",
    },
]

def get_vendor(vid):
    for v in VENDORS:
        if v["id"] == vid:
            return v
    return None

# ---------- Database ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER NOT NULL,
            vendor_name TEXT NOT NULL,
            juice TEXT NOT NULL,
            price INTEGER NOT NULL,
            service_fee INTEGER NOT NULL,
            total INTEGER NOT NULL,
            phone TEXT NOT NULL,
            location TEXT NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'New',
            created_at INTEGER NOT NULL
        )
        """)

init_db()

# ---------- Rate-limited staff login ----------
# In-process store: {ip: {"count": n, "locked_until": ts}}
FAILED = {}
MAX_TRIES = 3
LOCKOUT_SECONDS = 15 * 60

def client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

def is_locked(ip):
    entry = FAILED.get(ip)
    if entry and entry.get("locked_until", 0) > time.time():
        return int(entry["locked_until"] - time.time())
    return 0

def record_failure(ip):
    entry = FAILED.setdefault(ip, {"count": 0, "locked_until": 0})
    entry["count"] += 1
    if entry["count"] >= MAX_TRIES:
        entry["locked_until"] = time.time() + LOCKOUT_SECONDS
    return entry

def clear_failures(ip):
    FAILED.pop(ip, None)

def require_staff(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("staff"):
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper

# ---------- Public routes ----------
@app.route("/")
def home():
    return render_template("index.html", vendors=VENDORS)

@app.route("/vendor/<int:vid>")
def vendor_detail(vid):
    v = get_vendor(vid)
    if not v:
        abort(404)
    return render_template("vendor.html", v=v, service_fee=SERVICE_FEE)

@app.route("/order/<int:vid>", methods=["GET", "POST"])
def order(vid):
    v = get_vendor(vid)
    if not v:
        abort(404)
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        note = request.form.get("note", "").strip()
        if not phone or not location:
            flash("Please add your phone and delivery location.")
            return render_template("order.html", v=v, service_fee=SERVICE_FEE)
        total = v["price"] + SERVICE_FEE
        with db() as conn:
            cur = conn.execute("""
              INSERT INTO orders
              (vendor_id, vendor_name, juice, price, service_fee, total, phone, location, note, status, created_at)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?)
            """, (v["id"], v["name"], v["juice"], v["price"], SERVICE_FEE, total,
                  phone, location, note, int(time.time())))
            order_id = cur.lastrowid
        return redirect(url_for("success", order_id=order_id))
    return render_template("order.html", v=v, service_fee=SERVICE_FEE)

@app.route("/success/<int:order_id>")
def success(order_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        abort(404)
    return render_template("success.html", o=row)

# ---------- Staff login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if not STAFF_PASSWORD:
        return "Staff access is not configured. Set STAFF_PASSWORD environment variable.", 503
    ip = client_ip()
    locked = is_locked(ip)
    if request.method == "POST":
        if locked:
            return render_template("login.html", locked=locked, remaining=0), 429
        password = request.form.get("password", "")
        if password == STAFF_PASSWORD:
            clear_failures(ip)
            session["staff"] = True
            return redirect(request.args.get("next") or url_for("orders"))
        entry = record_failure(ip)
        remaining = max(0, MAX_TRIES - entry["count"])
        return render_template("login.html", locked=is_locked(ip), remaining=remaining, error="Wrong password."), 401
    remaining = MAX_TRIES - FAILED.get(ip, {}).get("count", 0)
    return render_template("login.html", locked=locked, remaining=remaining)

@app.route("/logout")
def logout():
    session.pop("staff", None)
    return redirect(url_for("home"))

# ---------- Staff-only routes ----------
@app.route("/orders")
@require_staff
def orders():
    with db() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return render_template("orders.html", orders=rows)

@app.route("/operator")
@require_staff
def operator():
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE status != 'Delivered' ORDER BY created_at ASC"
        ).fetchall()
    return render_template("operator.html", orders=rows)

@app.route("/api/orders/<int:oid>/status", methods=["POST"])
@require_staff
def update_status(oid):
    new_status = request.form.get("status", "").strip()
    if new_status not in ("New", "Preparing", "Delivering", "Delivered"):
        return jsonify(ok=False, error="bad status"), 400
    with db() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, oid))
    return redirect(url_for("operator"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

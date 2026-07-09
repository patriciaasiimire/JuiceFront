"""
Ntuma - Simple neighbourhood shop delivery app.
One Flask file, one SQLite database. Easy to read, easy to change.
"""
from flask import Flask, render_template, request, jsonify, g
import sqlite3
import os
from datetime import datetime

# ---------- Setup ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "orders.db")

app = Flask(__name__)


# ---------- Database helpers ----------
def get_db():
    """Open a SQLite connection for the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the orders table on first run."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            text       TEXT    NOT NULL,
            phone      TEXT    NOT NULL,
            location   TEXT    NOT NULL,
            status     TEXT    NOT NULL DEFAULT 'New',
            created_at TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


# ---------- Page routes ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/orders.html")
def orders_page():
    return render_template("orders.html")


@app.route("/operator.html")
def operator_page():
    return render_template("operator.html")


# ---------- API routes ----------
@app.route("/api/orders", methods=["POST"])
def create_order():
    """Save a new customer order."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    phone = (data.get("phone") or "").strip()
    location = (data.get("location") or "").strip()

    if not text or not phone or not location:
        return jsonify({"error": "Please fill in what you want, phone and location."}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO orders (text, phone, location, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (text, phone, location, "New", datetime.utcnow().isoformat(timespec="seconds")),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "message": "Order received"}), 201


@app.route("/api/orders", methods=["GET"])
def list_orders():
    db = get_db()
    rows = db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return jsonify([dict(r) for r in rows])


VALID_STATUSES = ["New", "Buying", "Walking", "Delivered"]


@app.route("/api/orders/<int:order_id>/status", methods=["POST"])
def update_status(order_id):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in VALID_STATUSES:
        return jsonify({"error": f"Status must be one of {VALID_STATUSES}"}), 400

    db = get_db()
    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    db.commit()
    return jsonify({"ok": True})


# ---------- Entry point ----------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)

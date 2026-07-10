# JuiceFront — Fresh Juice Delivered

A tiny, beautiful Flask app for ordering fresh juice from local vendors in Nansana, Uganda.
We are the delivery service — vendors keep their prices, we add a small service fee.

## Run it

```bash
pip install -r requirements.txt
export STAFF_PASSWORD="pick-a-strong-password"
export SESSION_SECRET="any-long-random-string"
python app.py
```

Then open http://127.0.0.1:5000

## What's inside

- `app.py` — the whole Flask app (single file, commented)
- `templates/` — HTML pages
- `static/style.css` — colorful, mobile-first styles
- `juice.db` — SQLite database, auto-created on first run

## Pages

**Public**
- `/` — Homepage with juice vendor cards
- `/vendor/<id>` — Vendor detail + Order Now button
- `/order/<id>` — Order form (phone, location, note)
- `/success/<order_id>` — Order confirmation

**Staff only (password protected)**
- `/login` — Enter staff password (3 wrong tries = 15 min lockout per IP)
- `/orders` — All orders
- `/operator` — Active orders dashboard, update status
- `/logout`

## Configuration

- `STAFF_PASSWORD` — required for staff pages. Missing = staff pages disabled.
- `SESSION_SECRET` — set to a long random string in production.
- Service fee is `SERVICE_FEE = 300` UGX in `app.py` — edit to taste.
- Add/edit vendors in the `VENDORS` list in `app.py`.

## Three-click order flow

1. Click a juice card on the homepage
2. Click "Order Now"
3. Fill phone + location → click "Place Order"

Done.

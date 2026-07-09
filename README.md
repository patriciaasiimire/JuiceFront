# Ntuma — Neighbourhood Shop Delivery

A tiny, friendly delivery app for a small shop in Nansana, Uganda.
Customers just write what they want in one text box. That's it.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

## Pages

- `/` — the customer order page
- `/orders.html` — every order that has come in (for testing)
- `/operator.html` — the shop operator's dashboard (update order status)

## Files

```
ntuma-shop/
├── app.py             # Flask backend + SQLite (all in one file)
├── requirements.txt
├── orders.db          # auto-created on first run
├── templates/         # HTML pages
├── static/css/        # styles
├── static/js/         # small vanilla JS helpers
└── images/            # place a logo/photo here if you like
```

Everything is deliberately simple so Patricia (and any beginner) can read it end-to-end.

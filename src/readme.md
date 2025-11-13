# Boostly — Kudos & Credits (Flask)

A simple Flask application that enables students to recognize peers by sending credits, endorse recognitions, redeem received credits as vouchers, and view a leaderboard. Includes monthly reset with carry-forward up to 50 unused sending credits.

## Tech Stack
- Python 3.9+
- Flask + Flask-SQLAlchemy (SQLite)
- Minimal HTML + JavaScript UI for demo

## Setup
1. Create a virtual environment and install dependencies:
   - Windows (PowerShell):
     - `python -m venv .venv`
     - `.venv\\Scripts\\Activate.ps1`
     - `pip install -r src/requirements.txt`
   - macOS/Linux:
     - `python3 -m venv .venv`
     - `source .venv/bin/activate`
     - `pip install -r src/requirements.txt`

2. Run the app:
   - `python src/app.py`
   - App runs at `http://127.0.0.1:5000/`

3. Open the demo UI:
   - Visit `http://127.0.0.1:5000/`

Database is an `SQLite` file created at `src/app.db` on first run.

## Business Rules Implemented
- Recognition
  - Every student gets 100 credits each calendar month as sending credits.
  - Cannot send to self.
  - Cannot send more than available credits.
  - Monthly sending limit of 100 enforced (even with carry-forward).
- Endorsements
  - One endorsement per endorser per recognition; counts only.
- Redemption
  - Received credits can be redeemed at ₹5 per credit.
  - Redemption permanently deducts from the student's received balance.
- Monthly Reset + Carry-Forward
  - On month change, sending credits reset to 100 + carry-forward (max 50 unused from prior month).
  - Monthly sending quota resets to 100.

Note: The reset is performed lazily on access (on recognition or when fetching a student) and via `/admin/reset_month` for batch runs.

## API Reference
Base URL: `http://127.0.0.1:5000`

- `GET /health`
  - Returns `{ status: "ok" }`.

- `POST /students`
  - Body: `{ "name": "Alice" }`
  - Creates a new student; name must be unique.

- `GET /students/{id}`
  - Returns student details including remaining sending limit and received balance. Triggers monthly reset if needed.

- `POST /recognitions`
  - Body: `{ "sender_id": 1, "recipient_id": 2, "amount": 10, "message": "Great work!" }`
  - Creates a recognition if rules are satisfied; debits sender's available credits and increments recipient's received balance.

- `GET /recognitions?sender_id={id}&recipient_id={id}`
  - Optional filters; returns recent recognitions and endorsement counts.

- `GET /recognitions/{id}`
  - Returns details of a recognition including endorsements count.

- `POST /endorsements`
  - Body: `{ "recognition_id": 1, "endorser_id": 3 }`
  - Adds a single endorsement per endorser per recognition.

- `POST /redemptions`
  - Body: `{ "student_id": 2, "amount": 20 }`
  - Redeems received credits for a voucher at ₹5 per credit.

- `GET /leaderboard?limit=10`
  - Returns top recipients by total credits received (lifetime), tie-broken by ascending student ID. Includes recognition and endorsement counts.

- `POST /admin/reset_month`
  - Idempotent per calendar month. Forces monthly reset across all students. Primarily for ops/testing; resets also happen lazily.

## Sample Requests

- Create students
```bash
curl -X POST http://127.0.0.1:5000/students -H "Content-Type: application/json" -d '{"name":"Alice"}'
curl -X POST http://127.0.0.1:5000/students -H "Content-Type: application/json" -d '{"name":"Bob"}'
```

- Get student
```bash
curl http://127.0.0.1:5000/students/1
```

- Send recognition
```bash
curl -X POST http://127.0.0.1:5000/recognitions -H "Content-Type: application/json" \
  -d '{"sender_id":1,"recipient_id":2,"amount":15,"message":"Great teamwork!"}'
```

- Endorse a recognition
```bash
curl -X POST http://127.0.0.1:5000/endorsements -H "Content-Type: application/json" \
  -d '{"recognition_id":1,"endorser_id":2}'
```

- Redeem credits
```bash
curl -X POST http://127.0.0.1:5000/redemptions -H "Content-Type: application/json" \
  -d '{"student_id":2,"amount":10}'
```

- Leaderboard
```bash
curl http://127.0.0.1:5000/leaderboard?limit=5
```

## Notes on Design
- Persistence: SQLite + SQLAlchemy ORM. Simple schema with `Student`, `Recognition`, `Endorsement`, and `Redemption`.
- Monthly Reset: Lazy recalculation based on `last_reset_month`. Carry-forward capped to 50 and monthly sending limit enforced at 100.
- Leaderboard: Lifetime total credits from recognitions; not reduced by redemptions per problem statement.

## Running Tests Manually
Use the sample curl commands or the UI at `/`.

## Folder Structure
```
src/
  app.py               # Flask app + models + routes
  requirements.txt     # Python deps
  readme.md            # This file
  templates/
    index.html         # Minimal UI
  static/
    app.js             # Fetch API calls
    styles.css         # Basic styles
prompt/
  llm-chat-export.txt  # Paste your LLM transcript here
test-cases/
  test-cases.txt       # Manual test steps
```


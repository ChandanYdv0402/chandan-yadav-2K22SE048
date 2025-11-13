from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func
from flask_cors import CORS
import os


app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# SQLite DB in src directory
db_path = os.path.join(os.path.dirname(__file__), "app.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Constants
MONTHLY_BASE_CREDITS = 100
MONTHLY_SENDING_LIMIT = 100
CARRY_FORWARD_CAP = 50
REDEMPTION_RATE_INR = 5


def current_month_str():
    now = datetime.utcnow()
    return f"{now.year:04d}-{now.month:02d}"


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)

    # Sending side
    available_credits = db.Column(db.Integer, nullable=False, default=MONTHLY_BASE_CREDITS)
    monthly_sent = db.Column(db.Integer, nullable=False, default=0)
    last_reset_month = db.Column(db.String(7), nullable=False, default=current_month_str)

    # Receiving side (redeemable balance). Redemptions subtract from this.
    received_balance = db.Column(db.Integer, nullable=False, default=0)


class Recognition(db.Model):
    __tablename__ = "recognitions"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Endorsement(db.Model):
    __tablename__ = "endorsements"
    id = db.Column(db.Integer, primary_key=True)
    recognition_id = db.Column(db.Integer, db.ForeignKey("recognitions.id"), nullable=False)
    endorser_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("recognition_id", "endorser_id", name="uq_endorse_once"),
    )


class Redemption(db.Model):
    __tablename__ = "redemptions"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    voucher_value_in_inr = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def ensure_monthly_reset(student: Student):
    """
    Resets sending credits monthly with carry-forward up to CARRY_FORWARD_CAP.
    Also resets monthly_sent (sending limit tracker) to 0 each new month.
    """
    if not student:
        return
    now_month = current_month_str()
    if student.last_reset_month != now_month:
        carry = min(max(student.available_credits, 0), CARRY_FORWARD_CAP)
        student.available_credits = MONTHLY_BASE_CREDITS + carry
        student.monthly_sent = 0
        student.last_reset_month = now_month


"""Initialize DB (Flask 3 removed before_first_request)."""
with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return render_template("index.html")


# ----------------------------- Students -----------------------------
@app.route("/students", methods=["POST"])
def create_student():
    data = request.get_json(force=True)
    name = (data or {}).get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400
    if Student.query.filter_by(name=name).first():
        return jsonify({"error": "student with this name already exists"}), 409
    s = Student(
        name=name,
        available_credits=MONTHLY_BASE_CREDITS,
        monthly_sent=0,
        last_reset_month=current_month_str(),
        received_balance=0,
    )
    db.session.add(s)
    db.session.commit()
    return jsonify(student_to_dict(s)), 201


@app.route("/students/<int:student_id>", methods=["GET"])
def get_student(student_id):
    s = Student.query.get_or_404(student_id)
    ensure_monthly_reset(s)
    db.session.commit()
    return jsonify(student_to_dict(s))


def student_to_dict(s: Student):
    remaining_limit = max(MONTHLY_SENDING_LIMIT - s.monthly_sent, 0)
    return {
        "id": s.id,
        "name": s.name,
        "available_credits": s.available_credits,
        "monthly_sent": s.monthly_sent,
        "monthly_sending_limit": MONTHLY_SENDING_LIMIT,
        "remaining_monthly_limit": remaining_limit,
        "last_reset_month": s.last_reset_month,
        "received_balance": s.received_balance,
        "voucher_value_if_redeem_all_inr": s.received_balance * REDEMPTION_RATE_INR,
    }


# --------------------------- Recognitions ---------------------------
@app.route("/recognitions", methods=["POST"])
def create_recognition():
    data = request.get_json(force=True)
    try:
        sender_id = int(data.get("sender_id"))
        recipient_id = int(data.get("recipient_id"))
        amount = int(data.get("amount"))
    except Exception:
        return jsonify({"error": "sender_id, recipient_id, amount must be integers"}), 400

    if amount <= 0:
        return jsonify({"error": "amount must be > 0"}), 400
    if sender_id == recipient_id:
        return jsonify({"error": "self-recognition is not allowed"}), 400

    sender = Student.query.get(sender_id)
    recipient = Student.query.get(recipient_id)
    if not sender or not recipient:
        return jsonify({"error": "sender or recipient not found"}), 404

    # Monthly reset checks
    ensure_monthly_reset(sender)
    ensure_monthly_reset(recipient)

    # Rule: cannot exceed available balance
    if sender.available_credits < amount:
        return jsonify({"error": "insufficient available credits"}), 400

    # Rule: cannot exceed monthly sending limit
    remaining_limit = MONTHLY_SENDING_LIMIT - sender.monthly_sent
    if amount > remaining_limit:
        return jsonify({"error": "monthly sending limit exceeded"}), 400

    msg = data.get("message")
    rec = Recognition(
        sender_id=sender.id,
        recipient_id=recipient.id,
        amount=amount,
        message=msg,
    )

    # Apply effects
    sender.available_credits -= amount
    sender.monthly_sent += amount
    recipient.received_balance += amount

    db.session.add(rec)
    db.session.commit()

    return jsonify({
        "recognition_id": rec.id,
        "created_at": rec.created_at.isoformat() + "Z",
        "sender": student_to_brief(sender),
        "recipient": student_to_brief(recipient),
        "amount": amount,
        "message": msg,
    }), 201


def student_to_brief(s: Student):
    return {"id": s.id, "name": s.name}


@app.route("/recognitions", methods=["GET"])
def list_recognitions():
    sender_id = request.args.get("sender_id", type=int)
    recipient_id = request.args.get("recipient_id", type=int)
    q = Recognition.query
    if sender_id is not None:
        q = q.filter_by(sender_id=sender_id)
    if recipient_id is not None:
        q = q.filter_by(recipient_id=recipient_id)
    q = q.order_by(Recognition.created_at.desc())
    items = []
    for r in q.limit(200).all():
        items.append({
            "id": r.id,
            "sender_id": r.sender_id,
            "recipient_id": r.recipient_id,
            "amount": r.amount,
            "message": r.message,
            "created_at": r.created_at.isoformat() + "Z",
            "endorsements": Endorsement.query.filter_by(recognition_id=r.id).count(),
        })
    return jsonify(items)


@app.route("/recognitions/<int:recognition_id>", methods=["GET"])
def get_recognition(recognition_id):
    r = Recognition.query.get_or_404(recognition_id)
    endorses = Endorsement.query.filter_by(recognition_id=r.id).count()
    return jsonify({
        "id": r.id,
        "sender_id": r.sender_id,
        "recipient_id": r.recipient_id,
        "amount": r.amount,
        "message": r.message,
        "created_at": r.created_at.isoformat() + "Z",
        "endorsements": endorses,
    })


# --------------------------- Endorsements ---------------------------
@app.route("/endorsements", methods=["POST"])
def create_endorsement():
    data = request.get_json(force=True)
    try:
        recognition_id = int(data.get("recognition_id"))
        endorser_id = int(data.get("endorser_id"))
    except Exception:
        return jsonify({"error": "recognition_id and endorser_id must be integers"}), 400

    rec = Recognition.query.get(recognition_id)
    if not rec:
        return jsonify({"error": "recognition not found"}), 404
    if not Student.query.get(endorser_id):
        return jsonify({"error": "endorser not found"}), 404

    existing = Endorsement.query.filter_by(recognition_id=recognition_id, endorser_id=endorser_id).first()
    if existing:
        return jsonify({"error": "each endorser can endorse only once"}), 409

    e = Endorsement(recognition_id=recognition_id, endorser_id=endorser_id)
    db.session.add(e)
    db.session.commit()
    count = Endorsement.query.filter_by(recognition_id=recognition_id).count()
    return jsonify({"endorsement_id": e.id, "recognition_id": recognition_id, "total_endorsements": count}), 201


# ---------------------------- Redemptions ---------------------------
@app.route("/redemptions", methods=["POST"])
def redeem_credits():
    data = request.get_json(force=True)
    try:
        student_id = int(data.get("student_id"))
        amount = int(data.get("amount"))
    except Exception:
        return jsonify({"error": "student_id and amount must be integers"}), 400

    if amount <= 0:
        return jsonify({"error": "amount must be > 0"}), 400

    s = Student.query.get(student_id)
    if not s:
        return jsonify({"error": "student not found"}), 404

    # Can only redeem received credits
    if s.received_balance < amount:
        return jsonify({"error": "insufficient received credits to redeem"}), 400

    value_in_inr = amount * REDEMPTION_RATE_INR
    red = Redemption(student_id=s.id, amount=amount, voucher_value_in_inr=value_in_inr)

    s.received_balance -= amount
    db.session.add(red)
    db.session.commit()

    return jsonify({
        "redemption_id": red.id,
        "student_id": s.id,
        "amount": amount,
        "voucher_value_in_inr": value_in_inr,
        "created_at": red.created_at.isoformat() + "Z",
    }), 201


# ---------------------------- Leaderboard ---------------------------
@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    limit = request.args.get("limit", default=10, type=int)
    limit = max(1, min(limit, 100))

    # total credits received per student
    totals_subq = (
        db.session.query(
            Recognition.recipient_id.label("student_id"),
            func.coalesce(func.sum(Recognition.amount), 0).label("total_received"),
            func.count(Recognition.id).label("recognitions_count"),
        )
        .group_by(Recognition.recipient_id)
        .subquery()
    )

    # endorsements per recipient across all their recognitions
    endorses_subq = (
        db.session.query(
            Recognition.recipient_id.label("student_id"),
            func.coalesce(func.count(Endorsement.id), 0).label("endorsements_count"),
        )
        .join(Endorsement, Endorsement.recognition_id == Recognition.id, isouter=True)
        .group_by(Recognition.recipient_id)
        .subquery()
    )

    q = (
        db.session.query(
            Student.id,
            Student.name,
            func.coalesce(totals_subq.c.total_received, 0).label("total_received"),
            func.coalesce(totals_subq.c.recognitions_count, 0).label("recognitions_count"),
            func.coalesce(endorses_subq.c.endorsements_count, 0).label("endorsements_count"),
        )
        .outerjoin(totals_subq, totals_subq.c.student_id == Student.id)
        .outerjoin(endorses_subq, endorses_subq.c.student_id == Student.id)
    )

    q = q.order_by(
        func.coalesce(totals_subq.c.total_received, 0).desc(),
        Student.id.asc(),
    ).limit(limit)

    rows = q.all()
    result = [
        {
            "student_id": row.id,
            "name": row.name,
            "total_credits_received": int(row.total_received or 0),
            "recognitions_count": int(row.recognitions_count or 0),
            "endorsements_count": int(row.endorsements_count or 0),
        }
        for row in rows
    ]
    return jsonify(result)


# -------------------------- Admin utilities -------------------------
@app.route("/admin/reset_month", methods=["POST", "GET"])
def admin_reset_month():
    # Reset all students for new month (idempotent for current month)
    now_month = current_month_str()
    students = Student.query.all()
    updated_ids = []
    for s in students:
        if s.last_reset_month != now_month:
            ensure_monthly_reset(s)
            updated_ids.append(s.id)
    db.session.commit()
    return jsonify({
        "status": "ok",
        "reset_month": now_month,
        "processed": len(students),
        "updated": len(updated_ids),
        "updated_ids": updated_ids,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # For local development
    app.run(host="127.0.0.1", port=5000, debug=True)

from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

# ---------------- APP CONFIG ----------------
app = Flask(__name__)

app.config["SECRET_KEY"] = "secret123"

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------- DATABASE MODELS ----------------

class Complaint(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))
    issue = db.Column(db.Text)

    location = db.Column(db.String(200))
    landmark = db.Column(db.String(200))

    category = db.Column(db.String(50))
    priority = db.Column(db.String(10))

    score = db.Column(db.Integer)
    count = db.Column(db.Integer, default=1)

    photo = db.Column(db.String(300))

    status = db.Column(db.String(20), default="Pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), unique=True)

    points = db.Column(db.Integer, default=0)

    level = db.Column(db.String(20), default="Bronze")


class Challenge(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200))

    description = db.Column(db.Text)

    points_reward = db.Column(db.Integer)

    completed_by = db.Column(db.Text, default="")


with app.app_context():
    db.create_all()

# ---------------- HELPER FUNCTIONS ----------------

def allowed_file(filename):

    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- AI ISSUE CLASSIFICATION ----------------

def detect_priority(text):

    text = text.lower()

    high_keywords = ["fire", "gas leak", "electric shock", "live wire", "accident"]

    medium_keywords = ["leak", "pothole", "garbage", "traffic"]

    if any(word in text for word in high_keywords):
        return "High"

    if any(word in text for word in medium_keywords):
        return "Medium"

    return "Low"


def classify_issue(text):

    text = text.lower()

    mapping = {
        "Waste Management": ["garbage", "trash", "waste"],
        "Road Damage": ["pothole", "road"],
        "Water Issue": ["leak", "water", "drain"],
        "Electricity Issue": ["power", "light", "wire"],
        "Traffic Issue": ["traffic", "jam"],
        "Noise Pollution": ["noise"],
        "Air Pollution": ["smoke"],
        "Flooding": ["flood"],
        "Open Manhole": ["manhole"]
    }

    category = "General"

    for cat, words in mapping.items():

        if any(word in text for word in words):
            category = cat
            break

    priority = detect_priority(text)

    return category, priority


# ---------------- PRIORITY ENGINE ----------------

def get_priority_score(priority):

    scores = {"High": 10, "Medium": 6, "Low": 3}

    return scores.get(priority, 5)


def update_dynamic_priority(c):

    # Crowd escalation
    if c.count >= 5:
        c.priority = "High"

    elif c.count >= 3:
        c.priority = "Medium"

    # Time escalation
    hours = (datetime.utcnow() - c.created_at).total_seconds() / 3600

    if hours > 48:
        c.priority = "High"

    elif hours > 24 and c.priority == "Low":
        c.priority = "Medium"


# ---------------- LEVEL SYSTEM ----------------

def get_level(points):

    if points >= 200:
        return "Eco Hero"

    if points >= 100:
        return "Gold"

    if points >= 50:
        return "Silver"

    return "Bronze"


# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- SUBMIT COMPLAINT ----------------

@app.route("/submit", methods=["POST"])
def submit():

    name = request.form["name"]

    issue = request.form["issue"]

    location = request.form["location"]

    landmark = request.form["landmark"]

    file = request.files.get("photo")

    filepath = ""

    if file and allowed_file(file.filename):

        filename = secure_filename(file.filename)

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        file.save(filepath)

    category, priority = classify_issue(issue)

    score = get_priority_score(priority)

    existing = Complaint.query.filter_by(location=location).first()

    user = User.query.filter_by(name=name).first()

    if not user:
        user = User(name=name)
        db.session.add(user)

    if existing:

        existing.count += 1

        update_dynamic_priority(existing)

        existing.score = get_priority_score(existing.priority)

        user.points += 2

    else:

        complaint = Complaint(

            name=name,
            issue=issue,
            location=location,
            landmark=landmark,
            category=category,
            priority=priority,
            score=score,
            photo=filepath
        )

        db.session.add(complaint)

        user.points += score * 2

    user.level = get_level(user.points)

    db.session.commit()

    return redirect(url_for("show_challenges", user=name))


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
def admin():

    complaints = Complaint.query.all()

    for c in complaints:

        update_dynamic_priority(c)

        c.score = get_priority_score(c.priority)

    db.session.commit()

    complaints = Complaint.query.order_by(
        Complaint.score.desc(),
        Complaint.count.desc()
    ).all()

    return render_template("admin.html", complaints=complaints)


# ---------------- STATS PAGE ----------------

@app.route("/stats")
def stats():

    complaints = Complaint.query.all()

    data = {

        "high": sum(1 for c in complaints if c.priority == "High"),
        "medium": sum(1 for c in complaints if c.priority == "Medium"),
        "low": sum(1 for c in complaints if c.priority == "Low"),
        "total": len(complaints)
    }

    leaderboard = User.query.order_by(User.points.desc()).all()

    return render_template("stats.html", data=data, leaderboard=leaderboard)


# ---------------- CHALLENGES ----------------

@app.route("/challenges")
def show_challenges():

    user_name = request.args.get("user", "Guest")

    user = User.query.filter_by(name=user_name).first()

    if not user:

        user = User(name=user_name)

        db.session.add(user)

        db.session.commit()

    challenges = Challenge.query.all()

    for c in challenges:

        c.completed_list = c.completed_by.split(",") if c.completed_by else []

    return render_template("challenges.html", challenges=challenges, user=user)


# ---------------- COMPLETE CHALLENGE ----------------

@app.route("/complete_challenge", methods=["POST"])
def complete_challenge():

    cid = int(request.form["challenge_id"])

    user_name = request.form["user_name"]

    challenge = Challenge.query.get(cid)

    user = User.query.filter_by(name=user_name).first()

    completed = challenge.completed_by.split(",") if challenge.completed_by else []

    if user_name not in completed:

        completed.append(user_name)

        challenge.completed_by = ",".join(completed)

        user.points += challenge.points_reward

        user.level = get_level(user.points)

    db.session.commit()

    return redirect(url_for("show_challenges", user=user_name))


# ---------------- SEED CHALLENGES ----------------

with app.app_context():

    if Challenge.query.count() == 0:

        db.session.add_all([

            Challenge(
                title="Plant a Tree",
                description="Plant one tree in your neighborhood",
                points_reward=10
            ),

            Challenge(
                title="Recycle Waste",
                description="Separate recyclable waste",
                points_reward=15
            ),

            Challenge(
                title="Report Water Leaks",
                description="Help detect water leaks",
                points_reward=20
            )

        ])

        db.session.commit()


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=True)

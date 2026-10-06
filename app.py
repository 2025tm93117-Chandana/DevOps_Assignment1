import os
import random
import sqlite3
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


PROGRAMS = {
    "Fat Loss (FL) – 3 day": {"factor": 22, "description": "3-day full-body fat loss"},
    "Fat Loss (FL) – 5 day": {"factor": 24, "description": "5-day split, higher-volume fat loss"},
    "Muscle Gain (MG) – PPL": {"factor": 35, "description": "Push/Pull/Legs hypertrophy"},
    "Beginner (BG)": {"factor": 26, "description": "3-day beginner full-body"},
}
PROGRAM_TEMPLATES = {
    "Fat Loss": ["Full Body HIIT", "Circuit Training", "Cardio + Weights"],
    "Muscle Gain": ["Push/Pull/Legs", "Upper/Lower Split", "Full Body Strength"],
    "Beginner": ["Full Body 3x/week", "Light Strength + Mobility"],
}
WORKOUT_TYPES = ["Strength", "Hypertrophy", "Conditioning", "Mixed", "Mobility", "Cardio"]
PROGRAM_OPTIONS = list(dict.fromkeys(
    [*PROGRAMS, *(program for options in PROGRAM_TEMPLATES.values() for program in options)]
))
EXERCISES_BY_FOCUS = {
    "Strength": ["Squat", "Deadlift", "Bench Press", "Overhead Press", "Pull-Up", "Barbell Row"],
    "Hypertrophy": ["Leg Press", "Incline Dumbbell Press", "Lat Pulldown", "Lateral Raise", "Bicep Curl", "Tricep Extension"],
    "Conditioning": ["Running", "Cycling", "Rowing", "Burpees", "Jump Rope", "Kettlebell Swings"],
    "Full Body": ["Push-Up", "Pull-Up", "Lunge", "Plank", "Dumbbell Row", "Dumbbell Press"],
}
EXPERIENCE_SETTINGS = {
    "beginner": ((2, 3), (8, 12), 3),
    "intermediate": ((3, 4), (8, 15), 4),
    "advanced": ((4, 5), (6, 15), 5),
}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def generate_weekly_plan(program_name, experience):
    sets_range, reps_range, days = EXPERIENCE_SETTINGS[experience]
    focus = "Full Body"
    if "Fat Loss" in (program_name or ""):
        focus = "Conditioning"
    elif "Muscle Gain" in (program_name or ""):
        focus = "Hypertrophy"
    exercises_per_day = 3 if days < 4 else 4
    plan = []
    for day in WEEKDAYS[:days]:
        for exercise in random.sample(EXERCISES_BY_FOCUS[focus], k=exercises_per_day):
            plan.append({
                "day": day,
                "exercise": exercise,
                "sets": random.randint(*sets_range),
                "reps": random.randint(*reps_range),
            })
    return plan


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-development-key"),
        DATABASE=os.environ.get("DATABASE", str(Path(app.instance_path) / "aceest_fitness.db")),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Coach'
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                age INTEGER,
                height REAL,
                weight REAL,
                program TEXT,
                calories INTEGER,
                target_weight REAL,
                target_adherence INTEGER,
                membership_status TEXT NOT NULL DEFAULT 'Active',
                membership_end TEXT
            );
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                week TEXT NOT NULL,
                adherence INTEGER NOT NULL CHECK(adherence BETWEEN 0 AND 100)
            );
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                workout_type TEXT NOT NULL,
                duration_min INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                sets INTEGER NOT NULL,
                reps INTEGER NOT NULL,
                weight REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                weight REAL,
                waist REAL,
                bodyfat REAL
            );
            """
        )
        db.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin"), "Admin"),
        )
        db.commit()

    with app.app_context():
        init_db()

    def login_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped_view(**kwargs):
            if "username" not in session:
                return redirect(url_for("login"))
            return view(**kwargs)

        return wrapped_view

    def get_client(client_id):
        client = get_db().execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if client is None:
            abort(404)
        return client

    def number(field, label, *, integer=False, minimum=0, optional=True):
        raw = request.form.get(field, "").strip()
        if not raw:
            if optional:
                return None
            raise ValueError(f"{label} is required.")
        try:
            value = int(raw) if integer else float(raw)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc
        if value < minimum:
            raise ValueError(f"{label} must be at least {minimum}.")
        return value

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT username, password_hash, role FROM users WHERE username = ?", (username,)
            ).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["username"] = user["username"]
                session["role"] = user["role"]
                return redirect(url_for("dashboard"))
            flash("The username or password was not recognized.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        db = get_db()
        clients = db.execute("SELECT * FROM clients ORDER BY name").fetchall()
        summary = db.execute(
            "SELECT COUNT(*) AS total, SUM(membership_status = 'Active') AS active FROM clients"
        ).fetchone()
        recent_workouts = db.execute(
            """SELECT w.*, c.name AS client_name FROM workouts w
               JOIN clients c ON c.id = w.client_id ORDER BY w.date DESC, w.id DESC LIMIT 8"""
        ).fetchall()
        return render_template(
            "dashboard.html", clients=clients, summary=summary,
            recent_workouts=recent_workouts, programs=PROGRAMS,
            today=date.today().isoformat(),
        )

    @app.post("/clients")
    @login_required
    def create_client():
        name = request.form.get("name", "").strip()
        if not name:
            flash("Client name is required.", "error")
            return redirect(url_for("dashboard"))
        try:
            age = number("age", "Age", integer=True, minimum=1)
            height = number("height", "Height")
            weight = number("weight", "Weight")
            target_weight = number("target_weight", "Target weight")
            target_adherence = number("target_adherence", "Target adherence", integer=True, minimum=0)
            if target_adherence is not None and target_adherence > 100:
                raise ValueError("Target adherence must be between 0 and 100.")
            program = request.form.get("program", "").strip()
            if program and program not in PROGRAM_OPTIONS:
                raise ValueError("Choose a listed training program.")
            membership_end = request.form.get("membership_end", "").strip() or None
            if membership_end:
                datetime.strptime(membership_end, "%Y-%m-%d")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))

        calories = int(weight * PROGRAMS.get(program, {}).get("factor", 25)) if weight and program else None
        db = get_db()
        try:
            cursor = db.execute(
                """INSERT INTO clients
                   (name, age, height, weight, program, calories, target_weight,
                    target_adherence, membership_status, membership_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?)""",
                (name, age, height, weight, program or None, calories, target_weight,
                 target_adherence, membership_end),
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("A client with that name already exists.", "error")
            return redirect(url_for("dashboard"))
        flash(f"Client {name} added.", "success")
        return redirect(url_for("client_detail", client_id=cursor.lastrowid))

    @app.route("/clients/<int:client_id>")
    @login_required
    def client_detail(client_id):
        db = get_db()
        client = get_client(client_id)
        today = date.today().isoformat()
        if client["membership_end"] and client["membership_end"] < today and client["membership_status"] == "Active":
            db.execute("UPDATE clients SET membership_status = 'Expired' WHERE id = ?", (client_id,))
            db.commit()
            client = get_client(client_id)
        progress = db.execute(
            "SELECT * FROM progress WHERE client_id = ? ORDER BY id DESC", (client_id,)
        ).fetchall()
        metrics = db.execute(
            "SELECT * FROM metrics WHERE client_id = ? ORDER BY date DESC, id DESC", (client_id,)
        ).fetchall()
        workouts = db.execute(
            "SELECT * FROM workouts WHERE client_id = ? ORDER BY date DESC, id DESC", (client_id,)
        ).fetchall()
        workout_exercises = {
            workout["id"]: db.execute(
                "SELECT * FROM exercises WHERE workout_id = ? ORDER BY id", (workout["id"],)
            ).fetchall()
            for workout in workouts
        }
        adherence = round(sum(row["adherence"] for row in progress) / len(progress), 1) if progress else None
        bmi = None
        bmi_category = None
        if client["height"] and client["weight"]:
            bmi = round(client["weight"] / ((client["height"] / 100) ** 2), 1)
            bmi_category = "Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"
        return render_template(
            "client_detail.html", client=client, progress=progress, metrics=metrics,
            workouts=workouts, workout_exercises=workout_exercises, adherence=adherence,
            bmi=bmi, bmi_category=bmi_category, programs=PROGRAM_OPTIONS,
            workout_types=WORKOUT_TYPES, today=today,
            generated_program=(session.get("generated_program")
                               if session.get("generated_program", {}).get("client_id") == client_id
                               else None),
        )

    @app.post("/clients/<int:client_id>/update")
    @login_required
    def update_client(client_id):
        get_client(client_id)
        name = request.form.get("name", "").strip()
        program = request.form.get("program", "").strip()
        if not name or (program and program not in PROGRAM_OPTIONS):
            flash("Enter a name and choose a valid program.", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        try:
            age = number("age", "Age", integer=True, minimum=1)
            height = number("height", "Height")
            weight = number("weight", "Weight")
            target_weight = number("target_weight", "Target weight")
            target_adherence = number("target_adherence", "Target adherence", integer=True, minimum=0)
            if target_adherence is not None and target_adherence > 100:
                raise ValueError("Target adherence must be between 0 and 100.")
            membership_end = request.form.get("membership_end", "").strip() or None
            if membership_end:
                datetime.strptime(membership_end, "%Y-%m-%d")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("client_detail", client_id=client_id))
        calories = int(weight * PROGRAMS.get(program, {}).get("factor", 25)) if weight and program else None
        try:
            get_db().execute(
                """UPDATE clients SET name=?, age=?, height=?, weight=?, program=?, calories=?,
                   target_weight=?, target_adherence=?, membership_status=?, membership_end=? WHERE id=?""",
                (name, age, height, weight, program or None, calories, target_weight,
                 target_adherence, request.form.get("membership_status", "Active"), membership_end, client_id),
            )
            get_db().commit()
        except sqlite3.IntegrityError:
            flash("A client with that name already exists.", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        flash("Client details updated.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/program")
    @login_required
    def generate_program(client_id):
        client = get_client(client_id)
        program_type = random.choice(list(PROGRAM_TEMPLATES))
        program = random.choice(PROGRAM_TEMPLATES[program_type])
        db = get_db()
        db.execute("UPDATE clients SET program = ? WHERE id = ?", (program, client_id))
        db.commit()
        flash(f"Generated {program_type}: {program} for {client['name']}.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/ai-program")
    @login_required
    def generate_ai_program(client_id):
        client = get_client(client_id)
        experience = request.form.get("experience", "").strip().lower()
        if experience not in EXPERIENCE_SETTINGS:
            flash("Choose beginner, intermediate, or advanced experience.", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        session["generated_program"] = {
            "client_id": client_id,
            "experience": experience,
            "workouts": generate_weekly_plan(client["program"], experience),
        }
        flash(f"Weekly workout plan generated for {client['name']}.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/progress")
    @login_required
    def add_progress(client_id):
        get_client(client_id)
        try:
            adherence = number("adherence", "Adherence", integer=True, minimum=0, optional=False)
            if adherence > 100:
                raise ValueError("Adherence must be between 0 and 100.")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("client_detail", client_id=client_id))
        week = request.form.get("week", "").strip() or date.today().strftime("Week %U - %Y")
        db = get_db()
        db.execute("INSERT INTO progress (client_id, week, adherence) VALUES (?, ?, ?)", (client_id, week, adherence))
        db.commit()
        flash("Weekly adherence saved.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/workouts")
    @login_required
    def add_workout(client_id):
        get_client(client_id)
        workout_date = request.form.get("date", "").strip()
        workout_type = request.form.get("workout_type", "").strip()
        try:
            datetime.strptime(workout_date, "%Y-%m-%d")
            duration = number("duration_min", "Duration", integer=True, minimum=1, optional=False)
            if workout_type not in WORKOUT_TYPES:
                raise ValueError("Choose a valid workout type.")
            exercise_name = request.form.get("exercise_name", "").strip()
            exercise_sets = number("sets", "Sets", integer=True, minimum=1) if exercise_name else None
            exercise_reps = number("reps", "Reps", integer=True, minimum=1) if exercise_name else None
            exercise_weight = number("exercise_weight", "Exercise weight") if exercise_name else None
        except ValueError as exc:
            flash(f"Invalid workout: {exc}", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        db = get_db()
        cursor = db.execute(
            "INSERT INTO workouts (client_id, date, workout_type, duration_min, notes) VALUES (?, ?, ?, ?, ?)",
            (client_id, workout_date, workout_type, duration, request.form.get("notes", "").strip()),
        )
        if exercise_name:
            db.execute(
                "INSERT INTO exercises (workout_id, name, sets, reps, weight) VALUES (?, ?, ?, ?, ?)",
                (cursor.lastrowid, exercise_name, exercise_sets, exercise_reps, exercise_weight or 0),
            )
        db.commit()
        flash("Workout logged.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/metrics")
    @login_required
    def add_metrics(client_id):
        get_client(client_id)
        metric_date = request.form.get("date", "").strip()
        try:
            datetime.strptime(metric_date, "%Y-%m-%d")
            weight = number("weight", "Weight")
            waist = number("waist", "Waist")
            bodyfat = number("bodyfat", "Body fat")
            if bodyfat is not None and bodyfat > 100:
                raise ValueError("Body fat must be at most 100%.")
        except ValueError as exc:
            flash(f"Invalid metrics: {exc}", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        db = get_db()
        db.execute(
            "INSERT INTO metrics (client_id, date, weight, waist, bodyfat) VALUES (?, ?, ?, ?, ?)",
            (client_id, metric_date, weight, waist, bodyfat),
        )
        if weight is not None:
            db.execute("UPDATE clients SET weight = ? WHERE id = ?", (weight, client_id))
        db.commit()
        flash("Body metrics saved.", "success")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.get("/clients/<int:client_id>/report")
    @login_required
    def client_report(client_id):
        client = get_client(client_id)
        pdf = _build_pdf(client)
        safe_name = "".join(character for character in client["name"] if character.isalnum() or character in "-_ ").strip().replace(" ", "_")
        return send_file(BytesIO(pdf), as_attachment=True, download_name=f"{safe_name}_report.pdf", mimetype="application/pdf")

    return app


def _build_pdf(client):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 12, f"ACEest Client Report - {client['name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Arial", size=11)
    fields = [
        ("ID", client["id"]),
        ("Age", client["age"]), ("Height (cm)", client["height"]),
        ("Weight (kg)", client["weight"]), ("Program", client["program"]),
        ("Calories/day", client["calories"]), ("Target weight (kg)", client["target_weight"]),
        ("Target adherence (%)", client["target_adherence"]),
        ("Membership", client["membership_status"]), ("Membership end", client["membership_end"]),
    ]
    for label, value in fields:
        pdf.cell(0, 9, f"{label}: {value if value is not None else 'N/A'}", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
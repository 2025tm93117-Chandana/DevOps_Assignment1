import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE": str(tmp_path / "test.db"),
    })


@pytest.fixture
def client(app):
    return app.test_client()


def sign_in(client):
    return client.post("/login", data={"username": "admin", "password": "admin"})


def add_client(client, name="Taylor Reed"):
    return client.post("/clients", data={
        "name": name,
        "age": "29",
        "height": "172",
        "weight": "70",
        "target_weight": "67",
        "target_adherence": "85",
        "program": "Fat Loss (FL) – 3 day",
    }, follow_redirects=True)


def test_dashboard_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.location


def test_login_and_client_creation_calculates_calories(client):
    sign_in(client)
    response = add_client(client)
    assert response.status_code == 200
    assert b"Taylor Reed" in response.data
    assert b"1540 kcal" in response.data


def test_duplicate_client_name_is_rejected(client):
    sign_in(client)
    add_client(client)
    response = add_client(client)
    assert b"already exists" in response.data


def test_progress_workout_and_metrics_are_recorded(client, app):
    sign_in(client)
    add_client(client)
    with app.app_context():
        from flask import current_app
        import sqlite3

        db = sqlite3.connect(current_app.config["DATABASE"])
        client_id = db.execute("SELECT id FROM clients WHERE name = ?", ("Taylor Reed",)).fetchone()[0]
        db.close()

    response = client.post(f"/clients/{client_id}/progress", data={
        "week": "Week 40 - 2026", "adherence": "91",
    })
    assert response.status_code == 302
    response = client.post(f"/clients/{client_id}/workouts", data={
        "date": "2026-10-06", "workout_type": "Strength", "duration_min": "55",
        "notes": "Lower body", "exercise_name": "Squat", "sets": "4", "reps": "8",
        "exercise_weight": "60",
    })
    assert response.status_code == 302
    response = client.post(f"/clients/{client_id}/metrics", data={
        "date": "2026-10-06", "weight": "69.5", "waist": "78", "bodyfat": "22.4",
    })
    assert response.status_code == 302
    page = client.get(f"/clients/{client_id}")
    assert b"91%" in page.data
    assert b"Squat" in page.data
    assert b"69.5 kg" in page.data


def test_adherence_outside_range_is_rejected(client, app):
    sign_in(client)
    add_client(client)
    with app.app_context():
        from flask import current_app
        import sqlite3

        db = sqlite3.connect(current_app.config["DATABASE"])
        client_id = db.execute("SELECT id FROM clients WHERE name = ?", ("Taylor Reed",)).fetchone()[0]
        db.close()
    response = client.post(f"/clients/{client_id}/progress", data={"adherence": "101"}, follow_redirects=True)
    assert b"between 0 and 100" in response.data


def test_report_download_is_pdf(client):
    sign_in(client)
    add_client(client)
    with client.application.app_context():
        from flask import current_app
        import sqlite3

        db = sqlite3.connect(current_app.config["DATABASE"])
        client_id = db.execute("SELECT id FROM clients WHERE name = ?", ("Taylor Reed",)).fetchone()[0]
        db.close()
    response = client.get(f"/clients/{client_id}/report")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_ai_program_uses_experience_and_client_program_focus(client, app):
    sign_in(client)
    add_client(client)
    with app.app_context():
        from flask import current_app
        import sqlite3

        db = sqlite3.connect(current_app.config["DATABASE"])
        client_id = db.execute("SELECT id FROM clients WHERE name = ?", ("Taylor Reed",)).fetchone()[0]
        db.close()
    response = client.post(
        f"/clients/{client_id}/ai-program", data={"experience": "beginner"}
    )
    assert response.status_code == 302
    page = client.get(f"/clients/{client_id}")
    assert b"BEGINNER PLAN" in page.data
    generated_plan = page.data.split(b'<div class="generated-plan">', 1)[1].split(b"</section>", 1)[0]
    assert b"Conditioning" not in generated_plan
    assert page.data.count(b"Monday") == 3
    assert b"Running" in page.data or b"Cycling" in page.data or b"Rowing" in page.data
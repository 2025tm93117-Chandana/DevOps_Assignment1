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

# ---- Additional coverage ----

def get_client_id(app, name="Taylor Reed"):
    import sqlite3

    db = sqlite3.connect(app.config["DATABASE"])
    try:
        return db.execute("SELECT id FROM clients WHERE name = ?", (name,)).fetchone()[0]
    finally:
        db.close()


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_login_with_wrong_password_is_rejected(client):
    response = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 200
    assert b"not recognized" in response.data
    assert client.get("/").status_code == 302


def test_login_with_unknown_user_is_rejected(client):
    response = client.post("/login", data={"username": "ghost", "password": "admin"})
    assert b"not recognized" in response.data


def test_successful_login_redirects_to_dashboard(client):
    response = sign_in(client)
    assert response.status_code == 302
    assert client.get("/").status_code == 200


def test_logout_clears_session(client):
    sign_in(client)
    response = client.post("/logout")
    assert response.status_code == 302
    assert "/login" in response.location
    assert client.get("/").status_code == 302


@pytest.mark.parametrize("path", ["/clients/1", "/clients/1/report"])
def test_protected_routes_require_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert "/login" in response.location


def test_create_client_requires_name(client):
    sign_in(client)
    response = client.post("/clients", data={"name": "  "}, follow_redirects=True)
    assert b"Client name is required" in response.data


@pytest.mark.parametrize("field,value,message", [
    ("age", "abc", b"Age must be a number"),
    ("age", "0", b"Age must be at least 1"),
    ("target_adherence", "150", b"between 0 and 100"),
    ("program", "Not A Program", b"Choose a listed training program"),
    ("membership_end", "31-12-2026", b"does not match"),
])
def test_create_client_validation_errors(client, field, value, message):
    sign_in(client)
    response = client.post("/clients", data={"name": "Casey", field: value}, follow_redirects=True)
    assert message in response.data
    assert b"Client Casey added" not in response.data


def test_dashboard_lists_created_clients(client):
    sign_in(client)
    add_client(client, "Alex Doe")
    add_client(client, "Sam Roe")
    page = client.get("/")
    assert b"Alex Doe" in page.data
    assert b"Sam Roe" in page.data


def test_unknown_client_returns_404(client):
    sign_in(client)
    assert client.get("/clients/9999").status_code == 404


def test_client_detail_shows_bmi(client, app):
    sign_in(client)
    add_client(client)
    page = client.get(f"/clients/{get_client_id(app)}")
    assert b"23.7" in page.data
    assert b"Normal" in page.data


def test_update_client_changes_profile_and_calories(client, app):
    sign_in(client)
    add_client(client)
    client_id = get_client_id(app)
    response = client.post(f"/clients/{client_id}/update", data={
        "name": "Taylor Reed", "age": "30", "height": "172", "weight": "80",
        "program": "Muscle Gain (MG) – PPL", "membership_status": "Paused",
    }, follow_redirects=True)
    assert b"Client details updated" in response.data
    assert b"2800 kcal" in response.data
    assert b"Paused" in response.data


def test_update_client_rejects_invalid_program(client, app):
    sign_in(client)
    add_client(client)
    response = client.post(f"/clients/{get_client_id(app)}/update", data={
        "name": "Taylor Reed", "program": "Bogus",
    }, follow_redirects=True)
    assert b"valid program" in response.data


def test_update_client_rejects_duplicate_name(client, app):
    sign_in(client)
    add_client(client, "Taylor Reed")
    add_client(client, "Jordan Lee")
    response = client.post(f"/clients/{get_client_id(app, 'Jordan Lee')}/update", data={
        "name": "Taylor Reed",
    }, follow_redirects=True)
    assert b"already exists" in response.data


def test_expired_membership_is_flagged_on_view(client, app):
    sign_in(client)
    client.post("/clients", data={"name": "Old Member", "membership_end": "2020-01-01"})
    page = client.get(f"/clients/{get_client_id(app, 'Old Member')}")
    assert b"status-expired" in page.data


def test_generate_program_assigns_a_template_program(client, app):
    from app import PROGRAM_TEMPLATES

    sign_in(client)
    add_client(client)
    client_id = get_client_id(app)
    response = client.post(f"/clients/{client_id}/program", follow_redirects=True)
    assert b"Generated" in response.data
    all_templates = [name for options in PROGRAM_TEMPLATES.values() for name in options]
    assert any(name.encode() in response.data for name in all_templates)


def test_ai_program_rejects_invalid_experience(client, app):
    sign_in(client)
    add_client(client)
    response = client.post(
        f"/clients/{get_client_id(app)}/ai-program", data={"experience": "godlike"},
        follow_redirects=True,
    )
    assert b"Choose beginner, intermediate, or advanced" in response.data


def test_progress_requires_adherence(client, app):
    sign_in(client)
    add_client(client)
    response = client.post(f"/clients/{get_client_id(app)}/progress", data={}, follow_redirects=True)
    assert b"Adherence is required" in response.data


def test_workout_rejects_invalid_type_and_date(client, app):
    sign_in(client)
    add_client(client)
    client_id = get_client_id(app)
    bad_type = client.post(f"/clients/{client_id}/workouts", data={
        "date": "2026-10-06", "workout_type": "Dancing", "duration_min": "30",
    }, follow_redirects=True)
    assert b"Choose a valid workout type" in bad_type.data
    bad_date = client.post(f"/clients/{client_id}/workouts", data={
        "date": "tomorrow", "workout_type": "Cardio", "duration_min": "30",
    }, follow_redirects=True)
    assert b"Invalid workout" in bad_date.data


def test_workout_without_exercise_is_logged(client, app):
    sign_in(client)
    add_client(client)
    client_id = get_client_id(app)
    response = client.post(f"/clients/{client_id}/workouts", data={
        "date": "2026-10-06", "workout_type": "Cardio", "duration_min": "30",
    }, follow_redirects=True)
    assert b"Workout logged" in response.data


def test_metrics_reject_bodyfat_over_100(client, app):
    sign_in(client)
    add_client(client)
    response = client.post(f"/clients/{get_client_id(app)}/metrics", data={
        "date": "2026-10-06", "bodyfat": "120",
    }, follow_redirects=True)
    assert b"Invalid metrics" in response.data


@pytest.mark.parametrize("experience,days", [("beginner", 2), ("intermediate", 3), ("advanced", 4)])
def test_generate_weekly_plan_shape(experience, days):
    from app import EXPERIENCE_SETTINGS, generate_weekly_plan

    plan = generate_weekly_plan("Muscle Gain (MG) – PPL", experience)
    sets_range, reps_range, plan_days = EXPERIENCE_SETTINGS[experience]
    assert len({item["day"] for item in plan}) == plan_days
    assert all(sets_range[0] <= item["sets"] <= sets_range[1] for item in plan)
    assert all(reps_range[0] <= item["reps"] <= reps_range[1] for item in plan)


def test_generate_weekly_plan_focus_follows_program():
    from app import EXERCISES_BY_FOCUS, generate_weekly_plan

    fat_loss = generate_weekly_plan("Fat Loss (FL) – 3 day", "beginner")
    assert {item["exercise"] for item in fat_loss} <= set(EXERCISES_BY_FOCUS["Conditioning"])
    muscle = generate_weekly_plan("Muscle Gain (MG) – PPL", "beginner")
    assert {item["exercise"] for item in muscle} <= set(EXERCISES_BY_FOCUS["Hypertrophy"])
    default = generate_weekly_plan(None, "beginner")
    assert {item["exercise"] for item in default} <= set(EXERCISES_BY_FOCUS["Full Body"])


def test_delete_client_removes_client_and_related_records(client, app):
    import sqlite3

    sign_in(client)
    add_client(client)
    client_id = get_client_id(app)
    client.post(f"/clients/{client_id}/progress", data={"adherence": "80"})
    client.post(f"/clients/{client_id}/workouts", data={
        "date": "2026-10-06", "workout_type": "Strength", "duration_min": "45",
        "exercise_name": "Squat", "sets": "3", "reps": "5",
    })
    client.post(f"/clients/{client_id}/metrics", data={"date": "2026-10-06", "weight": "70"})

    response = client.post(f"/clients/{client_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Client Taylor Reed deleted" in response.data
    assert client.get(f"/clients/{client_id}").status_code == 404

    db = sqlite3.connect(app.config["DATABASE"])
    try:
        for table in ("progress", "workouts", "metrics"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM exercises").fetchone()[0] == 0
    finally:
        db.close()


def test_delete_client_keeps_other_clients(client, app):
    sign_in(client)
    add_client(client, "Taylor Reed")
    add_client(client, "Jordan Lee")
    client.post(f"/clients/{get_client_id(app, 'Taylor Reed')}/delete")
    page = client.get("/")
    assert b'aria-label="View Taylor Reed"' not in page.data
    assert b'aria-label="View Jordan Lee"' in page.data


def test_delete_unknown_client_returns_404(client):
    sign_in(client)
    assert client.post("/clients/9999/delete").status_code == 404


def test_delete_client_requires_login(client):
    response = client.post("/clients/1/delete")
    assert response.status_code == 302
    assert "/login" in response.location


def test_delete_client_rejects_get(client):
    sign_in(client)
    assert client.get("/clients/1/delete").status_code == 405


def test_client_detail_shows_delete_button(client, app):
    sign_in(client)
    add_client(client)
    page = client.get(f"/clients/{get_client_id(app)}")
    assert b"Delete client" in page.data

def roster_names(response):
    import re

    return re.findall(rb'aria-label="View ([^"]+)"', response.data)


def test_dashboard_search_filters_by_name_case_insensitively(client):
    sign_in(client)
    add_client(client, "Taylor Reed")
    add_client(client, "Jordan Lee")
    response = client.get("/?q=taylor")
    assert roster_names(response) == [b"Taylor Reed"]


def test_dashboard_search_matches_partial_names(client):
    sign_in(client)
    add_client(client, "Taylor Reed")
    add_client(client, "Tara Stone")
    add_client(client, "Jordan Lee")
    response = client.get("/?q=ta")
    assert roster_names(response) == [b"Tara Stone", b"Taylor Reed"]


def test_dashboard_search_without_match_shows_empty_message(client):
    sign_in(client)
    add_client(client)
    response = client.get("/?q=nobody")
    assert roster_names(response) == []
    assert b"No matching clients" in response.data


def test_dashboard_search_treats_wildcards_literally(client):
    sign_in(client)
    add_client(client, "Taylor Reed")
    assert roster_names(client.get("/?q=%25")) == []
    assert roster_names(client.get("/?q=_")) == []


def test_dashboard_status_filter(client, app):
    sign_in(client)
    add_client(client, "Taylor Reed")
    add_client(client, "Jordan Lee")
    client.post(f"/clients/{get_client_id(app, 'Jordan Lee')}/update", data={
        "name": "Jordan Lee", "membership_status": "Paused",
    })
    assert roster_names(client.get("/?status=Paused")) == [b"Jordan Lee"]
    assert roster_names(client.get("/?status=Active")) == [b"Taylor Reed"]
    assert roster_names(client.get("/?status=Expired")) == []


def test_dashboard_search_and_status_combine(client, app):
    sign_in(client)
    add_client(client, "Taylor Reed")
    add_client(client, "Tara Stone")
    client.post(f"/clients/{get_client_id(app, 'Tara Stone')}/update", data={
        "name": "Tara Stone", "membership_status": "Paused",
    })
    assert roster_names(client.get("/?q=ta&status=Paused")) == [b"Tara Stone"]


def test_dashboard_invalid_status_is_ignored(client):
    sign_in(client)
    add_client(client)
    response = client.get("/?status=Bogus")
    assert roster_names(response) == [b"Taylor Reed"]


def test_dashboard_search_injection_attempt_is_harmless(client):
    sign_in(client)
    add_client(client)
    response = client.get("/?q=' OR 1=1 --")
    assert response.status_code == 200
    assert roster_names(response) == []


def test_dashboard_summary_ignores_filters(client):
    sign_in(client)
    add_client(client, "Taylor Reed")
    add_client(client, "Jordan Lee")
    response = client.get("/?q=taylor")
    assert b"<strong>2</strong>" in response.data


def test_dashboard_keeps_search_term_in_form(client):
    sign_in(client)
    response = client.get("/?q=taylor&status=Paused")
    assert b'value="taylor"' in response.data
    assert b"Clear" in response.data
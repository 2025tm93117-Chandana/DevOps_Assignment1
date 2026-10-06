# ACEest Fitness & Performance

A Flask and SQLite web app for gym coaches to manage client profiles, training programs, membership, weekly adherence, workouts, exercises, and body metrics. It also calculates calorie targets and BMI, summarizes client progress, and generates downloadable PDF reports.

## Local setup

Requirements: Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The demo login is `admin` / `admin`. Set `SECRET_KEY` to a random value before exposing the app outside a local development environment. Set `DATABASE` to change the SQLite database location.

## Tests

Run the pytest suite locally:

```powershell
python -m pytest -q
```

Run the suite in the production image:

```powershell
docker build -t aceest-fitness .
docker run --rm --entrypoint python aceest-fitness -m pytest -q
```

Run the web app in Docker and persist its database:

```powershell
docker run --rm -p 5000:5000 -v aceest-data:/app/instance `
  -e SECRET_KEY="replace-with-a-long-random-value" aceest-fitness
```

## Features

- Coach sign-in with hashed password storage and session-based access control.
- Client profiles, goals, membership status/expiry, and program-based daily calorie estimates.
- Randomized training-program suggestions, weekly adherence check-ins, workout and exercise logs.
- Body metric history, BMI category, average adherence, and client PDF report downloads.
- SQLite persistence with parameterized statements and relational foreign-key constraints.

## Code version port

The scripts in `Code_Versions` are the application behavior reference; Tkinter windows and widgets are replaced with Flask routes and HTML forms. The client goals, calorie factors, adherence, progress analytics, body metrics, workout history, and BMI logic follow the `3.0.1` increment. The experience-level weekly exercise generator follows `3.1.2`, including its exercise pools, focus selection, day counts, and sets/reps ranges. The login, randomized training-template generator, membership status, workout entry, and PDF report flow follow `3.2.4`. Program names and calorie factors match the reference data.

## CI/CD overview

GitHub Actions runs on every push and pull request. It checks Python syntax, runs the pytest suite, builds a Docker image, and runs pytest again inside that image. The workflow is in `.github/workflows/main.yml`.

The `Jenkinsfile` checks out the configured repository, builds an isolated Docker image, and runs the same tests in that image. Create a Jenkins Pipeline job pointed at this repository and enable a GitHub webhook or a multibranch scan to trigger builds. The Jenkins agent needs Docker installed and permission to access the Docker daemon.

## Demo credentials and production note

The assignment demo bootstraps `admin` / `admin` on a fresh database. Replace this bootstrap account and configure a strong `SECRET_KEY` for any non-demo deployment. This app is intended as a development/assignment deliverable and should be placed behind a production WSGI server and HTTPS before public use.
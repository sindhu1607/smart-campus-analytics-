# Smart Campus Analytics

Django web application for explainable student-success analytics, role-based dashboards, CSV/Excel data import, risk monitoring, and intervention tracking. The current analytics engine is **rule-based and explainable**; it is not a trained machine-learning model and should be treated as decision support, not as an automated decision-maker.

## Features

- Role-aware accounts: administrator, faculty, placement officer, and student.
- Student academic, attendance, LMS, placement, skills, engagement, and intervention records.
- Student success score with sub-score breakdown, data coverage, missing-domain flags, weighted contributions, risk flags, segments, and recommended interventions.
- Independent academic and placement risk classification; feedback satisfaction contributes to the 15% skills/engagement/feedback domain.
- Dashboard pages, student directory/detail pages, risk monitoring, interventions, and CSV reports.
- Authenticated REST endpoints with role/department checks and request throttling.
- CSV/Excel import with upload size and extension checks.
- SQLite for local development; PostgreSQL recommended for production.

## Requirements

- Python 3.12 (recommended; matches CI and Docker).
- pip and a virtual environment.
- PostgreSQL for production deployments. Local development defaults to SQLite.

## Local setup (Windows PowerShell)

```powershell
cd smart-campus-analytics-main
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `.env` and set a unique `SECRET_KEY` for your local environment. Do not commit `.env`.

Linux/macOS activation:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env
```

Apply migrations and run the app:

```bash
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

### Optional demonstration data

Only run this command in a disposable development database; it creates synthetic users and records:

```bash
python manage.py generate_sample_data --count 40
python manage.py run_analytics_engine
```

The development data generator creates demo credentials. Change or delete those accounts before using any shared environment. Never run the sample-data generator as part of a production startup.

## Environment variables

| Variable | Purpose | Local default / production guidance |
|---|---|---|
| `SECRET_KEY` | Django signing key | Required when `DEBUG=False`; use a long random secret |
| `DEBUG` | Debug mode | `True` locally; `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hostnames | Set your actual deployment hostname(s) |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated scheme-qualified origins | Set your HTTPS site origin(s) if needed |
| `DATABASE_URL` | Database connection | SQLite locally; PostgreSQL URL in production |
| `DB_CONN_MAX_AGE` | Persistent DB connection lifetime in seconds | `60`; tune for hosting limits |
| `DB_SSL_REQUIRE` | Require SSL for database connection | Enable when required by your database provider |
| `TIME_ZONE` | Django time zone | `Asia/Kolkata` |
| `ALLOW_PUBLIC_STUDENT_REGISTRATION` | Enable public student self-registration | Enabled by default in local debug; disable in production unless intended |
| `SECURE_SSL_REDIRECT` | Redirect HTTP to HTTPS | Enable in production behind HTTPS |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | Secure cookies | Enable in production |
| `SECURE_HSTS_SECONDS` | HSTS duration | Enable only after HTTPS is verified |
| `USE_X_FORWARDED_HOST` | Trust reverse-proxy host/protocol headers | Enable only behind a trusted hosting proxy |
| `FILE_UPLOAD_MAX_MEMORY_SIZE`, `DATA_UPLOAD_MAX_MEMORY_SIZE` | Django upload/request memory limits | Defaults to 5 MiB |
| `API_ANON_RATE`, `API_USER_RATE` | DRF request throttling rates | Defaults `60/hour`, `600/hour` |
| `LOG_LEVEL` | Application log level | `INFO` by default |

`.env.example` lists all supported configuration variables. Never place real credentials in source code, CI files, screenshots, or commits.

## Data import

Use **Students → Import** after signing in as an administrator. The importer currently expects a combined student dataset with column names such as `student_id`, `name`, `email`, `department`, `semester`, `cgpa`, `backlog_count`, `attendance_percentage`, `lms_login_frequency`, `assignment_completion_percentage`, `aptitude_score`, `coding_score`, `mock_interview_score`, `resume_readiness_score`, `communication_score`, `engagement_score`, `technical_skill_score`, `soft_skill_score`, and `feedback_score` when available. The sample template is `sample_student_import_template.csv`. Upload limit is 5 MiB. Validate imported data before using it for institutional decisions.

Command-line import:

```bash
python manage.py import_student_data sample_student_import_template.csv
```

## Testing and quality checks

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tests apps.analytics
ruff check .
python -m compileall -q apps config tests
python manage.py collectstatic --noinput
```

Use `ruff format .` to apply the configured formatter. GitHub Actions runs the lint, tests, compile, static-collection, and production-settings checks on pushes and pull requests. A successful test run does not replace manual verification of every role, import format, database backup, and deployment environment.

## Production deployment (Render)

A starter blueprint is included in `render.yaml`. Review the plan/costs before applying it; it provisions a web service and PostgreSQL database.

1. Push the project to a GitHub repository.
2. In Render, create a new **Blueprint** from that repository and review `render.yaml` before applying it.
3. Confirm the generated `SECRET_KEY`, PostgreSQL `DATABASE_URL`, `DEBUG=False`, and secure-cookie settings are present. Render's `RENDER_EXTERNAL_HOSTNAME` is appended to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` automatically.
4. In Render Shell, run `python manage.py createsuperuser` to create the first administrator. Do not use the sample-data generator in production.
5. In Render Shell, run `python manage.py run_analytics_engine` once after deployment to recompute snapshots with the current scoring method. This can create proposed intervention records for students whose measured indicators cross the configured thresholds; review those records before acting.
6. Sign in and verify dashboard static CSS/JS, login/logout, role and department boundaries, CSV import/export, analytics recalculation, database persistence, and logs.
7. Use only synthetic data for the demo unless the institution has approved real student data handling. Configure database backups before relying on the deployment.

Production startup uses Gunicorn, runs database migrations, and serves collected static assets through WhiteNoise. For high-availability or multi-instance deployments, run migrations as a release step rather than independently from every web worker, configure managed backups, and use a dedicated log/monitoring service.

## Docker

Build and run locally after creating `.env`:

```bash
docker compose up --build
```

The container runs as a non-root user and starts with migrations plus Gunicorn. `docker-compose.yml` is for local development; use a managed production database and secret store for deployment.

## Important security and product limitations

- The score engine is deterministic/rule-based; no model training or calibrated probability prediction is implemented.
- Synthetic records and demo credentials are for local demonstration only.
- Student data is sensitive. Use least-privilege accounts, HTTPS, secure secrets, database backups, and institutional approval before importing real student records.
- Faculty accounts without an assigned department are denied access to student records. Administrator accounts should be provisioned deliberately.
- No production deployment can be considered verified until its actual environment, database, hostname, and role-based workflows have been tested.

## Project layout

- `config/` — Django settings, root URLs, WSGI/ASGI.
- `apps/accounts/` — authentication, user roles, permissions.
- `apps/students/` — student profiles and import services.
- `apps/academics/`, `apps/attendance/`, `apps/lms/`, `apps/engagement/`, `apps/placements/`, `apps/skills/`, `apps/feedback/` — campus data domains.
- `apps/analytics/` — scoring, snapshots, dashboards, and APIs.
- `apps/interventions/` — intervention tracking.
- `tests/` — Django integration and analytics tests.


## CSV import integrity

The combined CSV/Excel import accepts optional domains but will not invent missing scores. Academic results require both `cgpa` and `backlog_count`; LMS summaries require `lms_login_frequency`, `assignment_completion_percentage`, `assignment_timeliness_percentage`, and `quiz_participation_percentage`; placement assessments require `aptitude_score`, `coding_score`, `mock_interview_score`, `resume_readiness_score`, and `communication_score`. Partial domain columns generate a coverage warning and are not used to create that domain's record. Use `sample_student_import_template.csv` as the full-column example.

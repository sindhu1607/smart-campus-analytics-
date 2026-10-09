# Deployment Handoff Checklist

## Before pushing

- [ ] Keep `.env`, `db.sqlite3`, uploaded real data, and credentials out of Git.
- [ ] Use Python 3.12, create/activate `.venv`, and install `requirements-dev.txt`.
- [ ] Run `python manage.py check`.
- [ ] Run `python manage.py makemigrations --check --dry-run`.
- [ ] Run `python manage.py test tests apps.analytics`.
- [ ] Run `ruff check .` and `python manage.py collectstatic --noinput`.
- [ ] Test login/logout, admin, faculty department isolation, placement officer, and student self-only access.
- [ ] Test import validation and the student detail page for both complete and missing data.

## Render deployment

The included `render.yaml` provisions the Django web service and PostgreSQL database. Review the plan and cost before applying the Blueprint.

1. Push this project to the GitHub repository connected to Render.
2. In Render, create a new Blueprint from the repository and review the resources before confirming.
3. Confirm `SECRET_KEY` is generated, `DEBUG=False`, PostgreSQL `DATABASE_URL` is attached, public registration is disabled, and secure cookies/HTTPS are enabled.
4. After the first successful deploy, open the Render Shell and run `python manage.py createsuperuser`.
5. In Render Shell, run `python manage.py run_analytics_engine` once to recompute snapshots using the current score methodology. Review proposed intervention records before acting.
6. Verify the site URL, login/logout, static assets, dashboard filters, score explanations, placement-risk chart, import/export, and role/department access boundaries.
7. Configure database backups and use only synthetic demo data unless institutional approval exists for real student records.

## Local Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Edit .env and set a unique local SECRET_KEY.
python manage.py migrate
python manage.py check
python manage.py test tests apps.analytics
python manage.py run_analytics_engine
python manage.py runserver
```

If a `.venv` already exists, activate it instead of recreating it. Back up your local database before applying migrations.

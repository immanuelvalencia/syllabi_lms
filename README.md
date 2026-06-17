# Syllabi LMS

A Django smart learning management system with role-based dashboards for students, instructors, and academic admins.

## Local setup

```powershell
conda activate syllabi_lms
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Background AI tasks

AI tools are queued through Celery so web requests stay responsive while multiple students and teachers use the app.

Run Redis locally, then start a worker in a second terminal:

```powershell
celery -A config worker --loglevel=info
```

The current task implementation returns structured placeholder output. Replace `build_ai_response` in `academics/tasks.py` with your real AI provider call.

## Local Docker

Start Django, PostgreSQL, Redis, and Celery together:

```powershell
docker compose up --build
```

Then open `http://localhost:8000/`.

Create a superuser inside the running web container:

```powershell
docker compose exec web python manage.py createsuperuser
```

Useful Docker commands:

```powershell
docker compose ps
docker compose logs -f web
docker compose logs -f worker
docker compose down
```

### Rebuild Docker after code changes

For normal code, template, CSS, Python dependency, or Dockerfile changes, rebuild the local images and start the services again:

```powershell
docker compose down
docker compose up --build
```

If Docker seems to reuse an old layer, force a clean rebuild:

```powershell
docker compose build --no-cache
docker compose up
```

For database model changes, create and commit migrations before rebuilding:

```powershell
conda activate syllabi_lms
python manage.py makemigrations
docker compose up --build
```

The `web` service runs migrations automatically on startup. The `worker` service must also be rebuilt when shared code changes because it uses the same Django image.

To delete the local Docker database and start fresh:

```powershell
docker compose down -v
```

## Roles

User roles live in `academics.Profile`:

- Student
- Instructor
- Academic Admin
- Platform Admin

Create users in Django admin, then assign their profile role under `Profiles`.

## Render deployment

This repo includes:

- `Dockerfile` for the Django app image
- `render.yaml` for a web service, Celery worker, PostgreSQL database, and Redis instance

After creating the Render blueprint, set:

- `ALLOWED_HOSTS` to your Render host, for example `syllabi-lms-web.onrender.com`
- `CSRF_TRUSTED_ORIGINS` to your full Render origin, for example `https://syllabi-lms-web.onrender.com`

To deploy changes to Render:

```powershell
git add .
git commit -m "Describe your change"
git push
```

Render rebuilds the Docker image from the pushed commit and redeploys the web and worker services. If auto-deploy is disabled, open the service in Render and choose **Manual Deploy**.

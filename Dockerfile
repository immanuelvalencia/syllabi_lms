FROM node:22-slim AS assets

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY assets ./assets
COPY templates ./templates
COPY academics ./academics
RUN npm run build:css

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=assets /app/static/css/tailwind.css /app/static/css/tailwind.css

RUN python manage.py collectstatic --noinput

CMD python manage.py migrate && python manage.py initadmin && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --threads 2

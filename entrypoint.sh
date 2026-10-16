#!/bin/sh
# entrypoint.sh

export PYTHONPATH="${PYTHONPATH}:/app"

echo "Waiting for PostgreSQL to start..."
while ! nc -z $POSTGRES_HOST 5432; do
  sleep 0.5
done
echo "PostgreSQL started!"

# Запускаем Worker.
python -m celery -A app.tasks.celery_app worker --loglevel=info --pool=solo &

# Запускаем Beat
python -m celery -A app.tasks.celery_app beat --loglevel=info &

# Запускftv веб-сервер FastAPI
uvicorn app.main:app --host 0.0.0.0 --port 8000

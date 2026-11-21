FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m app && mkdir -p /data && chown -R app /app /data
USER app
ENV DB_PATH=/data/db.sqlite3
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_sources && python manage.py collectstatic --noinput && exec gunicorn config.wsgi:application -b 0.0.0.0:8000 --workers 2 --threads 2 --worker-class gthread --timeout 60"]

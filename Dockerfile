FROM node:22-alpine AS assets
WORKDIR /build
COPY package*.json ./
RUN npm ci
COPY tailwind.config.js ./
COPY templates ./templates
COPY static ./static
RUN npm run build

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home scoresheet
COPY app.py wsgi.py ./
COPY migrations ./migrations
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts
COPY --from=assets /build/static/app.css ./static/app.css
RUN mkdir -p /data/uploads /backups && chown -R scoresheet:scoresheet /data /backups
USER scoresheet
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]

FROM runtime AS test
USER root
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
COPY pytest.ini ./
USER scoresheet
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

FROM runtime AS production

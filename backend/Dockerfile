FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv
RUN useradd --create-home --uid 10001 app && mkdir -p /data/objects && chown app /data/objects

ARG INSTALL_DEV=false
# Lock files pin every package (including transitive ones) to an exact version and hash, so a
# tampered or substituted package fails the install. Regenerate with pip-compile (docs/security.md).
COPY requirements*.txt requirements*.lock ./
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install --require-hashes -r requirements-dev.lock; \
    else pip install --require-hashes -r requirements.lock; fi

COPY . .
USER app
EXPOSE 8000
# FORWARDED_ALLOW_IPS must list only the reverse proxy that overwrites X-Forwarded-For.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]

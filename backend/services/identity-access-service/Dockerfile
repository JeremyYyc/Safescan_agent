FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY services/identity-access-service/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY packages/safescan-common /opt/safescan-common
RUN pip install --no-cache-dir --no-deps /opt/safescan-common

ENV PYTHONPATH=/app
COPY services/identity-access-service/app ./app

EXPOSE 8001

FROM base AS test
COPY services/identity-access-service/requirements-dev.txt ./
COPY services/identity-access-service/tests ./tests
COPY alembic/versions/20260908_0003_identity_tenancy_and_staff_permissions.py /identity_p0_migration.py
COPY packages/safescan-common/tests /common-tests
RUN pip install --no-cache-dir -r requirements-dev.txt
CMD ["pytest", "-q", "/common-tests", "/app/tests"]

FROM base AS runtime
CMD ["sh", "-c", "python -m app.seed_staff && uvicorn app.main:app --host 0.0.0.0 --port 8001"]

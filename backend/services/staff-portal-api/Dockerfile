FROM python:3.11-slim AS base

WORKDIR /app
COPY services/staff-portal-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY packages/safescan-common /opt/safescan-common
RUN pip install --no-cache-dir --no-deps /opt/safescan-common
COPY services/staff-portal-api/app ./app

FROM base AS test
COPY services/staff-portal-api/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY services/staff-portal-api/pytest.ini .
COPY services/staff-portal-api/tests ./tests
CMD ["sh", "-c", "pytest -q -p no:cacheprovider && ruff check app tests && ruff format --check app tests"]

FROM base AS runtime
ENV SERVICE_PORT=8006
EXPOSE 8006
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]

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

EXPOSE 8000

FROM base AS test
COPY services/identity-access-service/requirements-dev.txt ./
COPY services/identity-access-service/tests ./tests
COPY packages/safescan-common/tests /common-tests
RUN pip install --no-cache-dir -r requirements-dev.txt
CMD ["pytest", "-q", "/common-tests", "/app/tests"]

FROM base AS runtime
CMD ["sh", "-c", "python -m app.bootstrap_admin && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

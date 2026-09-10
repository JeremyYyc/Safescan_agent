FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY services/property-leasing-service/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY packages/safescan-common /opt/safescan-common
RUN pip install --no-cache-dir --no-deps /opt/safescan-common
COPY services/property-leasing-service/app ./app
EXPOSE 8002

FROM base AS test
COPY services/property-leasing-service/requirements-dev.txt ./
COPY services/property-leasing-service/tests ./tests
COPY alembic/versions/20260909_0003_property_leasing_p0.py /migrations/20260909_0003_property_leasing_p0.py
RUN pip install --no-cache-dir -r requirements-dev.txt
CMD ["pytest", "-q", "/app/tests"]

FROM base AS runtime
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]

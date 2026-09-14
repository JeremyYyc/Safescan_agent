FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/runtime:/runtime/packages/safescan-common/src

WORKDIR /runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/backend-requirements.txt
COPY services/inspection-report-service/requirements.txt /tmp/service-requirements.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.10.0 torchvision==0.25.0 \
    && pip install --no-cache-dir -r /tmp/backend-requirements.txt -r /tmp/service-requirements.txt

COPY packages ./packages
RUN pip install --no-cache-dir -e ./packages/safescan-common

# The protected report pipeline remains the single implementation. The service
# imports it through a narrow persistence/storage adapter.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY services/inspection-report-service/inspection_report_service ./inspection_report_service

RUN useradd --create-home --uid 10001 safescan \
    && chown -R safescan:safescan /runtime
USER safescan

EXPOSE 8004
CMD ["uvicorn", "inspection_report_service.main:app", "--host", "0.0.0.0", "--port", "8004"]

FROM runtime AS test
USER root
COPY services/inspection-report-service/requirements.txt /tmp/requirements.txt
COPY services/inspection-report-service/requirements-dev.txt /tmp/service-dev-requirements.txt
RUN pip install --no-cache-dir -r /tmp/service-dev-requirements.txt
COPY services/inspection-report-service/tests ./tests
USER safescan
CMD ["pytest", "-q", "tests"]

FROM python:3.11-alpine

WORKDIR /app
COPY app.py ./app.py

ENV SERVICE_NAME=skeleton-api
ENV SERVICE_PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "python app.py --host 0.0.0.0 --port ${SERVICE_PORT}"]

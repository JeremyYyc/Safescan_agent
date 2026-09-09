FROM python:3.11-alpine

WORKDIR /app
RUN pip install --no-cache-dir alembic==1.18.4 SQLAlchemy==2.0.48 psycopg[binary]==3.3.4 \
    python-dotenv==1.0.0 pydantic==2.13.5

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app/__init__.py ./app/__init__.py
COPY backend/app/settings.py ./app/settings.py
COPY backend/app/persistence ./app/persistence

CMD ["alembic", "upgrade", "head"]

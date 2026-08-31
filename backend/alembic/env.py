from alembic import context
from app.persistence.database import get_engine
from app.persistence.schema import metadata

with get_engine().connect() as connection:
    context.configure(connection=connection,target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()

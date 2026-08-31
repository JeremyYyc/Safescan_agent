"""Replace file locations; requires an empty Demo files table, never deletes data."""
from alembic import op
import sqlalchemy as sa
revision='20260831_0002'
down_revision='20260831_0001'
branch_labels=None
depends_on=None

def upgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM files')).scalar():
        raise RuntimeError('MinIO refactor requires a fresh Demo database; old files are not migrated or deleted')
    op.drop_constraint('uq_files_storage_path_hash','files',type_='unique')
    for name in ('storage_path','storage_path_hash','file_ext'): op.drop_column('files',name)
    op.add_column('files',sa.Column('bucket',sa.Text(),nullable=False))
    op.add_column('files',sa.Column('object_key',sa.Text(),nullable=False))
    op.add_column('files',sa.Column('original_name',sa.Text(),nullable=False,server_default=''))
    op.create_unique_constraint('uq_files_bucket','files',['bucket','object_key'])

def downgrade():
    raise RuntimeError('No lossy object-to-filesystem downgrade; restore prior Git branch with its separate Demo database')

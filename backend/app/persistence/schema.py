"""Ten domain tables; only Alembic executes DDL, never request handlers."""
from sqlalchemy import (MetaData, Table, Column as C, BigInteger, Integer, Text,
    Boolean, DateTime, Identity, ForeignKey, UniqueConstraint, CheckConstraint, Index, text)
from sqlalchemy.dialects.postgresql import UUID, JSONB

metadata = MetaData(naming_convention={'ix':'ix_%(table_name)s_%(column_0_name)s',
    'fk':'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'uq':'uq_%(table_name)s_%(column_0_name)s', 'pk':'pk_%(table_name)s'})

def pk(name='id'):
    return C(name, BigInteger, Identity(), primary_key=True)

def stamp(name='created_at'):
    return C(name, DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP'))

def fk(name, target, delete='CASCADE', nullable=False):
    return C(name, BigInteger, ForeignKey(target, ondelete=delete), nullable=nullable, index=True)

users = Table('users', metadata, pk('user_id'), C('username', Text, nullable=False),
    C('email', Text, nullable=False, unique=True), C('avatar', Text, nullable=False, server_default=''),
    C('password', Text, nullable=False), C('storage_uuid', UUID, nullable=False, unique=True),
    stamp('create_time'), stamp('update_time'),
    CheckConstraint('email = lower(trim(email))', name='email_normalized'))
chats = Table('chats', metadata, pk(), C('chat_uuid', UUID, nullable=False, unique=True),
    fk('user_id','users.user_id'), C('title',Text,nullable=False),
    C('chat_type',Text,nullable=False,server_default='report'),
    C('status',Text,nullable=False,server_default='active'),
    C('pinned',Boolean,nullable=False,server_default=text('false')),
    C('last_message_at',DateTime(timezone=True)),stamp(),stamp('updated_at'),
    CheckConstraint("chat_type IN ('report','bot')",name='chat_type_valid'),
    CheckConstraint("status IN ('active','archived','deleted')",name='chat_status_valid'))
messages = Table('messages', metadata, pk(),C('role',Text,nullable=False),C('content',Text,nullable=False),
    C('meta',JSONB),stamp(),CheckConstraint("role IN ('user','assistant')",name='message_role_valid'))
reports = Table('reports',metadata,pk(),C('report_uuid',UUID,nullable=False,unique=True),
    fk('user_id','users.user_id'),C('report_kind',Text,nullable=False),
    fk('origin_chat_id','chats.id','SET NULL',True),C('title',Text,nullable=False),
    C('status',Text,nullable=False,server_default='active'),stamp(),
    CheckConstraint("report_kind IN ('analysis','pdf')",name='report_kind_valid'),
    CheckConstraint("status IN ('active','deleted')",name='report_status_valid'))
files = Table('files',metadata,pk(),C('file_uuid',UUID,nullable=False,unique=True),
    fk('user_id','users.user_id'),C('storage_path',Text,nullable=False),
    C('storage_path_hash',Text,nullable=False,unique=True),C('mime_type',Text),C('file_ext',Text),
    C('file_size',BigInteger),C('sha256',Text),stamp(),
    CheckConstraint('file_size IS NULL OR file_size >= 0',name='file_size_nonnegative'))
report_analysis = Table('report_analysis',metadata,
    C('report_id',BigInteger,ForeignKey('reports.id',ondelete='CASCADE'),primary_key=True),
    fk('video_file_id','files.id','RESTRICT',True),C('region_info_json',JSONB),C('report_json',JSONB))
report_pdf = Table('report_pdf',metadata,
    C('report_id',BigInteger,ForeignKey('reports.id',ondelete='CASCADE'),primary_key=True),
    fk('file_id','files.id','RESTRICT'),C('pdf_kind',Text,nullable=False),
    fk('derived_from_report_id','reports.id','SET NULL',True),C('content_preview',Text),
    CheckConstraint("pdf_kind IN ('uploaded','exported')",name='pdf_kind_valid'))
report_assets = Table('report_assets',metadata,pk(),fk('report_id','reports.id'),
    fk('file_id','files.id','RESTRICT'),C('asset_kind',Text,nullable=False),
    C('sort_order',Integer,nullable=False,server_default='0'),
    UniqueConstraint('report_id','file_id','asset_kind'))
chat_details = Table('chat_details',metadata,pk(),fk('chat_id','chats.id'),C('role',Text,nullable=False),
    fk('message_id','messages.id','CASCADE',True),fk('report_id','reports.id','CASCADE',True),stamp(),
    UniqueConstraint('message_id'),UniqueConstraint('chat_id','report_id'),
    CheckConstraint("(role IN ('user','assistant') AND message_id IS NOT NULL AND report_id IS NULL) OR (role='report' AND report_id IS NOT NULL AND message_id IS NULL)",name='detail_exactly_one_source'))
chat_report_refs = Table('chat_report_refs',metadata,pk(),fk('chat_id','chats.id'),
    fk('report_id','reports.id','SET NULL',True),fk('source_chat_id','chats.id','SET NULL',True),
    C('status',Text,nullable=False,server_default='active'),stamp(),stamp('updated_at'),
    UniqueConstraint('chat_id','report_id'),
    CheckConstraint("status IN ('active','removed','deleted')",name='reference_status_valid'))
Index('ix_chats_user_recent',chats.c.user_id,chats.c.updated_at)
Index('ix_reports_user_created',reports.c.user_id,reports.c.created_at)
Index('ix_details_chat_created',chat_details.c.chat_id,chat_details.c.created_at)

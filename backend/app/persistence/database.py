"""SQLAlchemy pool and a scoped unit of work for synchronous repositories.

Nested repository calls join the same transaction. Only its outer owner commits.
All SQL is PostgreSQL, with bound parameters; no dialect translation at runtime.
"""
from contextvars import ContextVar
from functools import lru_cache
from uuid import UUID
from sqlalchemy import create_engine
from app.settings import get_settings

_active = ContextVar('database_unit_of_work',default=None)

@lru_cache(maxsize=1)
def get_engine():
    s = get_settings()
    url = s.require_secret('DATABASE_URL')
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://','postgresql+psycopg://',1)
    if not url.startswith('postgresql+psycopg://'):
        raise RuntimeError('DATABASE_URL must use postgresql+psycopg')
    return create_engine(url,pool_size=s.POSTGRES_POOL_SIZE,max_overflow=s.POSTGRES_MAX_OVERFLOW,
                         pool_timeout=s.POSTGRES_POOL_TIMEOUT,pool_pre_ping=True,hide_parameters=True)

class Cursor:
    def __init__(self, conn, dictionaries=False):
        self.conn,self.dictionaries = conn,dictionaries
        self.result=None
        self.lastrowid=None
        self.rowcount=0
    def __enter__(self): return self
    def __exit__(self,*args):
        if self.result is not None: self.result.close()
    def execute(self,sql,params=()):
        self.result=self.conn.exec_driver_sql(sql,tuple(params))
        self.rowcount=self.result.rowcount
        if sql.lstrip().upper().startswith('INSERT') and self.result.returns_rows:
            row=self.result.fetchone()
            self.lastrowid=row[0] if row else None
        return self
    def _normalize(self,row):
        if row is None: return None
        values=[v.hex if isinstance(v,UUID) else v for v in row]
        return dict(zip(self.result.keys(),values)) if self.dictionaries else tuple(values)
    def fetchone(self): return self._normalize(self.result.fetchone())
    def fetchall(self): return [self._normalize(r) for r in self.result.fetchall()]

class UnitOfWork:
    def __init__(self):
        self.depth=0
        self.failed=False
    def __enter__(self):
        if not self.depth:
            self.conn=get_engine().connect()
            self.tx=self.conn.begin()
            self.token=_active.set(self)
        self.depth+=1
        return self
    def __exit__(self,typ,value,tb):
        self.failed |= typ is not None
        self.depth-=1
        if not self.depth:
            try:
                if self.failed: self.tx.rollback()
                else: self.tx.commit()
            finally:
                self.conn.close()
                _active.reset(self.token)
    def cursor(self,dictionaries=False): return Cursor(self.conn,dictionaries)

def get_connection():
    return _active.get() or UnitOfWork()

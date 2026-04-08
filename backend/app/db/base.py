from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# SQLAlchemy 2.x dropped the legacy "postgres://" dialect alias; Supabase
# (and many other hosted Postgres services) still emit that scheme, so
# normalise it to "postgresql://" before passing it to create_engine.
_db_url = settings.database_url
if _db_url.startswith("postgres://"):
    _db_url = "postgresql://" + _db_url[len("postgres://"):]

# Use NullPool when connecting via pgbouncer (transaction mode) to avoid
# "prepared statement already exists" and pool exhaustion issues on serverless.
_is_pgbouncer = "pgbouncer=true" in _db_url.lower()

engine = create_engine(
    _db_url,
    pool_pre_ping=not _is_pgbouncer,
    poolclass=NullPool if _is_pgbouncer else None,
    **({} if _is_pgbouncer else {"pool_size": 10, "max_overflow": 20}),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

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

# Detect pgbouncer mode BEFORE stripping the param from the URL.
# psycopg2 rejects "pgbouncer" as an unknown DSN option, so we must
# remove it from the URL while still using NullPool for the connection.
_is_pgbouncer = "pgbouncer=true" in _db_url.lower()

if _is_pgbouncer:
    _parsed = urlparse(_db_url)
    _qs = {k: v for k, v in parse_qs(_parsed.query).items() if k.lower() != "pgbouncer"}
    _db_url = urlunparse(_parsed._replace(query=urlencode({k: v[0] for k, v in _qs.items()})))

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

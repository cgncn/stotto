from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Use NullPool when connecting via pgbouncer (transaction mode) to avoid
# "prepared statement already exists" and pool exhaustion issues on serverless.
_is_pgbouncer = "pgbouncer=true" in settings.database_url.lower()

engine = create_engine(
    settings.database_url,
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

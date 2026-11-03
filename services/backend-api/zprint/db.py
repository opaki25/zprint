from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def normalize_database_url(url):
    """Cloud providers supply postgres:// URLs; this project installs psycopg v3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def connect(url):
    url = normalize_database_url(url)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine, sessionmaker(engine, expire_on_commit=False)

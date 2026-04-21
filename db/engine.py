import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base

FRESH_DIR = ".fresh"
DB_FILE = os.path.join(FRESH_DIR, "fresh.db")


def get_engine():
    """Returns the SQLite engine."""
    # Ensure it connects to the local .fresh/ db
    sqlite_url = f"sqlite:///{DB_FILE}"
    engine = create_engine(sqlite_url, echo=False)
    return engine


def init_db():
    """Creates the `.fresh` directory and initializes the database tables."""
    if not os.path.exists(FRESH_DIR):
        os.makedirs(FRESH_DIR)

    engine = get_engine()
    Base.metadata.create_all(engine)


def get_session():
    """Returns a new SQLAlchemy session."""
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

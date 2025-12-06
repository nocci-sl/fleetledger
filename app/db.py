from sqlmodel import SQLModel, create_engine, Session
import os

# SQLite database path, mapped to a Docker volume for persistence
DB_PATH = os.getenv("DATABASE_PATH", "/data/fleetledger.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create all tables if they do not exist yet."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency that yields a SQLModel session."""
    with Session(engine) as session:
        yield session

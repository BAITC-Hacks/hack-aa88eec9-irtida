from pathlib import Path

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = 'employees'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    profile: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class Catalog(Base):
    __tablename__ = 'catalog'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Activity(Base):
    __tablename__ = 'activity_history'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'), index=True)
    event_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[str] = mapped_column(String)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Recommendation(Base):
    __tablename__ = 'recommendations'
    key: Mapped[str] = mapped_column(String, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)


class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    role: Mapped[str] = mapped_column(String)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.id'), nullable=True)
    expires_at: Mapped[float] = mapped_column(Float)


class AIRequest(Base):
    __tablename__ = 'ai_requests'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    provider: Mapped[str] = mapped_column(String)


class ImportRecord(Base):
    """Original kit records retained locally for conflict detection and replay."""

    __tablename__ = 'import_records'
    source: Mapped[str] = mapped_column(String, primary_key=True)
    record_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


def connect(url: str):
    filename = url.removeprefix('sqlite:///')
    if filename != ':memory:':
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 5})

    @event.listens_for(engine, 'connect')
    def pragmas(connection, _):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.close()

    @event.listens_for(engine, 'checkout')
    def reset_busy_timeout(connection, _record, _proxy):
        # Recommendation writes use a shorter local wait; do not leak it to
        # completion/import transactions via pooled SQLite connections.
        connection.execute('PRAGMA busy_timeout=5000')

    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)

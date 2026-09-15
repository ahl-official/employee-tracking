from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

import config


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    department: Mapped[str] = mapped_column(String(80), default="Engineering")
    on_break: Mapped[bool] = mapped_column(Boolean, default=False)

    heartbeats: Mapped[list["Heartbeat"]] = relationship(back_populates="user")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="user")
    sessions: Mapped[list["WorkSession"]] = relationship(back_populates="user")


class Heartbeat(Base):
    __tablename__ = "heartbeats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    present: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idle: Mapped[bool] = mapped_column(Boolean, default=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0)
    app: Mapped[str] = mapped_column(String(80), default="unknown")
    window_title: Mapped[str] = mapped_column(String(180), default="")
    device: Mapped[str] = mapped_column(String(20), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="heartbeats")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seen: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="alerts")


class WorkSession(Base):
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    clock_in: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

"""Data model: Topics group entries; entries carry an optional embedding
(packed float32 BLOB) for semantic search; reminders attach to a date."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now()


class Topic(Base):
    """A section/category for entries: Work, a specific project, Personal…"""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    color: Mapped[str] = mapped_column(String(7), default="#7c6cf0")  # hex accent
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    entries: Mapped[list["Entry"]] = relationship(back_populates="topic")


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")        # the brain dump
    polished_text: Mapped[str] = mapped_column(Text, default="")   # AI-cleaned version
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(80), default="")
    mood: Mapped[int | None] = mapped_column(nullable=True)  # 1 (rough) … 5 (great), AI-scored
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    topic: Mapped[Topic | None] = relationship(back_populates="entries")

    @property
    def display_text(self) -> str:
        return self.polished_text or self.raw_text


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Setting(Base):
    """Key-value app settings, e.g. ai_provider = "local" | "anthropic"."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), default="")


class Brief(Base):
    """Cached morning briefs, one per day."""

    __tablename__ = "briefs"

    brief_date: Mapped[date] = mapped_column(Date, primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

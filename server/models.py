"""SQLAlchemy models for the pension-planner backend.

Plain relational schema, queryable with ordinary SQL. Profile documents are
stored as JSON text in a column (the client owns their shape and it changes
often); everything used for lookups - users, names, shares, versions - is a
proper column with an index or constraint.
"""
import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow)

    profiles: Mapped[list["Profile"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")
    tokens: Mapped[list["AuthToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class AuthToken(Base):
    """Bearer tokens; only the SHA-256 of the token is stored."""
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="tokens")


class Profile(Base):
    """One saved planner profile: the full client input document as JSON."""
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_profile_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    data: Mapped[str] = mapped_column(Text)  # JSON document
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="profiles")
    shares: Mapped[list["ProfileShare"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan")


class ProfileShare(Base):
    """Adviser/client sharing: a profile made visible to another account."""
    __tablename__ = "profile_shares"
    __table_args__ = (UniqueConstraint("profile_id", "shared_with_id",
                                       name="uq_share_profile_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    shared_with_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    permission: Mapped[str] = mapped_column(String(10), default="read")  # read | write
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow)

    profile: Mapped[Profile] = relationship(back_populates="shares")
    shared_with: Mapped[User] = relationship()


class ReferenceDoc(Base):
    """Versioned reference data (tax tables + return history), one row per key."""
    __tablename__ = "reference_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(40))
    data: Mapped[str] = mapped_column(Text)  # JSON document
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

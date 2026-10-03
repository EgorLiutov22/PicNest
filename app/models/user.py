from __future__ import annotations
from datetime import datetime
from typing import List, Optional


from sqlalchemy import (
    String, Enum as SQLEnum
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.userrole import UserRole
from app.models.userstatus import UserStatus

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), nullable=False)
    status: Mapped[UserStatus] = mapped_column(SQLEnum(UserStatus), default=UserStatus.active, nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    timezone: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="CURRENT_TIMESTAMP")


    photographer_profile: Mapped[Optional["PhotographerProfile"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    studio_profile: Mapped[Optional["StudioProfile"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    reviews: Mapped[List["Review"]] = relationship(back_populates="author", cascade="all, delete-orphan")
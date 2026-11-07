from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=15)
    # role ограничен списком: произвольная строка позволяла присвоить себе
    # role="admin" при регистрации и через PATCH /users/me.
    role: Literal["client", "photographer", "studio"] = Field(
        ..., description="Роль пользователя"
    )
    city: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field("Europe/Moscow", max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=15)
    role: Optional[Literal["client", "photographer", "studio"]] = None
    city: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    role: str
    status: str
    city: Optional[str]
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
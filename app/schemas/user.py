from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RoleUpdate(BaseModel):
    role: Literal["student", "counselor", "admin"]


class UserProfile(BaseModel):
    google_sub: str
    email: str
    name: str
    role: Literal["student", "counselor", "admin"]


class StaffUser(BaseModel):
    id: str
    name: str
    email: str
    role: Literal["student", "counselor", "admin"]
    created_at: datetime | None = None


class StaffUserPage(BaseModel):
    items: list[StaffUser]
    total: int = Field(ge=0)
    limit: int
    skip: int

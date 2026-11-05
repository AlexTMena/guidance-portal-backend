from typing import Literal

from pydantic import BaseModel


class RoleUpdate(BaseModel):
    role: Literal["student", "counselor", "admin"]


class UserProfile(BaseModel):
    google_sub: str
    email: str
    name: str
    role: Literal["student", "counselor", "admin"]

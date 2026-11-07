from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudentBookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(min_length=1, max_length=64)
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Date and time must include a timezone")
        return value


class CounselingEvent(BaseModel):
    id: str
    starts_at: datetime
    ends_at: datetime
    status: str
    title: str
    attempt_id: str | None = None
    test_name: str | None = None
    student_name: str | None = None
    student_email: str | None = None
    counselor_name: str | None = None

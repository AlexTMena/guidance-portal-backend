from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StudentBookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str | None = Field(default=None, min_length=1, max_length=64)
    note: str | None = Field(default=None, min_length=1, max_length=3000)
    starts_at: datetime
    ends_at: datetime

    @field_validator("note")
    @classmethod
    def require_non_whitespace_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("A counseling note is required")
        return value

    @model_validator(mode="after")
    def require_exactly_one_booking_type(self):
        if bool(self.attempt_id) == bool(self.note):
            raise ValueError("Provide either an assessment attempt or a counseling note")
        return self

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
    booking_type: str = "request"
    attempt_id: str | None = None
    test_id: str | None = None
    test_name: str | None = None
    student_note: str | None = None
    student_name: str | None = None
    student_email: str | None = None
    counselor_name: str | None = None
    accepted_by_name: str | None = None
    accepted_by_role: str | None = None
    accepted_at: datetime | None = None

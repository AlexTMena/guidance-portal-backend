from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StudentSurveySummary(BaseModel):
    form_key: str
    title: str
    form_number: str
    access_mode: Literal["always", "request"] = "always"
    requested_at: datetime | None = None
    submitted_at: datetime | None = None
    response_id: str | None = None


class StudentTestAttemptSummary(BaseModel):
    attempt_id: str
    submitted_at: datetime


class StudentTestSummary(BaseModel):
    test_id: str
    name: str
    submissions: list[StudentTestAttemptSummary]


class StaffStudentSummary(BaseModel):
    id: str
    name: str
    email: str
    role: Literal["student", "counselor", "admin"]
    registered_at: datetime | None = None
    surveys: list[StudentSurveySummary]
    tests: list[StudentTestSummary]

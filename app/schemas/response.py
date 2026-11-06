from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TestAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: UUID
    answers: dict[str, str] = Field(max_length=21)


class StartedAttempt(BaseModel):
    attempt_id: UUID


class TestResult(BaseModel):
    score: int = Field(ge=0, le=63)
    max_score: int = 63
    category: str
    interpretation: str
    submitted_at: datetime


class StaffTestResponse(TestResult):
    attempt_id: UUID
    respondent_id: str
    respondent_name: str
    respondent_email: str
    answers: dict[str, str]
    self_harm_follow_up_flag: bool

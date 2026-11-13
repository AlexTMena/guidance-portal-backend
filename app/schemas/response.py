from datetime import datetime
from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TestAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: UUID
    answers: dict[str, str] = Field(max_length=21)


class StartedAttempt(BaseModel):
    attempt_id: UUID


class TestScaleResult(BaseModel):
    scale: Literal["Depression", "Anxiety", "Stress"]
    score: int = Field(ge=0, le=42)
    max_score: int = 42
    severity: Literal["Normal", "Mild", "Moderate", "Severe", "Extremely Severe"]
    interpretation: str


class TestResult(BaseModel):
    attempt_id: UUID
    score: int | float | None = Field(default=None, ge=0, le=80)
    max_score: int | None = Field(default=None, ge=0, le=80)
    category: str | None = None
    interpretation: str
    submitted_at: datetime
    scale_results: list[TestScaleResult] = Field(default_factory=list)


class StaffTestResponse(TestResult):
    attempt_id: UUID
    respondent_id: str
    respondent_name: str
    respondent_email: str
    answers: dict[str, str]
    self_harm_follow_up_flag: bool


class StaffTestResponseItem(BaseModel):
    attempt_id: UUID
    respondent_id: str
    student_id: str
    respondent_name: str
    respondent_email: str
    submitted_at: datetime


class StaffTestResponsePage(BaseModel):
    items: list[StaffTestResponseItem]
    total: int
    limit: int
    skip: int

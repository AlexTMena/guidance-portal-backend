from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class FormOption(BaseModel):
    value: str
    label: str


class FormCondition(BaseModel):
    question: str
    equals: str | None = None
    in_: list[str] | None = Field(default=None, alias="in")
    contains: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class FormQuestion(BaseModel):
    key: str
    label: str
    type: Literal["short_text", "long_text", "email", "tel", "date", "number", "select", "yes_no", "single_choice", "multi_select", "checkbox"]
    required: bool = False
    options: list[FormOption] = Field(default_factory=list)
    placeholder: str | None = None
    read_only: bool = False
    condition: FormCondition | None = None


class FormSection(BaseModel):
    key: str
    title: str
    description: str | None = None
    condition: FormCondition | None = None
    layout: Literal["rating_matrix"] | None = None
    questions: list[FormQuestion]


class SurveyForm(BaseModel):
    form_key: str
    form_number: str
    title: str
    version: int
    access_mode: Literal["always", "request"] = "always"
    sections: list[FormSection]


SurveyAnswer = StrictStr | StrictBool | list[StrictStr]


class SurveySubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, SurveyAnswer] = Field(max_length=100)


class SurveySubmission(BaseModel):
    form_key: str
    form_number: str
    form_version: int
    answers: dict[str, SurveyAnswer]
    submitted_at: datetime


class StaffSurveySubmission(SurveySubmission):
    student_id: str
    student_name: str
    student_email: str


class StaffSurveyCatalogItem(BaseModel):
    form_key: str
    form_number: str
    title: str


class StaffSurveyResponseItem(BaseModel):
    student_id: str
    student_name: str
    student_email: str
    submitted_at: datetime


class StaffSurveyResponsePage(BaseModel):
    items: list[StaffSurveyResponseItem]
    total: int
    limit: int
    skip: int


class AvailableSurvey(BaseModel):
    form_key: str
    form_number: str
    title: str
    requested_at: datetime | None = None
    submitted_at: datetime | None = None


class SurveyAccessRequest(BaseModel):
    form_key: str
    form_number: str
    title: str
    requested_at: datetime | None = None
    submitted_at: datetime | None = None

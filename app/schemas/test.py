from typing import Literal

from pydantic import BaseModel, Field


class TestCatalogItem(BaseModel):
    id: str
    name: str


class TestQuestionOption(BaseModel):
    value: str
    label: str
    score: int | None = None


class TestQuestion(BaseModel):
    id: str
    key: str
    order: int
    type: Literal["single_choice", "multi_choice", "scale", "text"]
    prompt: str
    required: bool = True
    options: list[TestQuestionOption] = Field(default_factory=list)
    min_value: int | None = None
    max_value: int | None = None
    min_label: str | None = None
    max_label: str | None = None
    is_demo: bool = False

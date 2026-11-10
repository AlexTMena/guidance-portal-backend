from datetime import datetime, timezone
from email.utils import parseaddr

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.security import CurrentUser
from app.data.student_cumulative_form import FORM_KEY
from app.db.mongo import require_database
from app.schemas.survey import (
    StaffSurveySubmission,
    SurveyForm,
    SurveySubmission,
    SurveySubmissionCreate,
)

router = APIRouter(prefix="/surveys", tags=["surveys"])


async def _get_form(database) -> dict:
    document = await database.forms.find_one({"form_key": FORM_KEY}, {"_id": 0})
    if document is None:
        raise HTTPException(status_code=503, detail="Student Cumulative Form is not seeded")
    return document


def _condition_matches(condition: dict | None, answers: dict) -> bool:
    if not condition:
        return True
    actual = answers.get(condition["question"])
    if "equals" in condition:
        return actual == condition["equals"]
    if "in" in condition:
        return actual in condition["in"]
    if "contains" in condition:
        return isinstance(actual, list) and condition["contains"] in actual
    return False


def _question_is_visible(question: dict, section: dict, answers: dict) -> bool:
    return _condition_matches(section.get("condition"), answers) and _condition_matches(
        question.get("condition"), answers
    )


def _validate_answers(form: dict, submitted: dict, user: dict) -> dict:
    questions: list[tuple[dict, dict]] = [
        (section, question)
        for section in form["sections"]
        for question in section["questions"]
    ]
    known_keys = {question["key"] for _, question in questions}
    unknown_keys = submitted.keys() - known_keys
    if unknown_keys:
        raise HTTPException(status_code=422, detail="Answers include unknown form fields")

    hidden_keys = {
        question["key"]
        for section, question in questions
        if not _question_is_visible(question, section, submitted)
    }
    if submitted.keys() & hidden_keys:
        raise HTTPException(status_code=422, detail="Answers include fields that are not currently displayed")

    normalized = dict(submitted)
    for section, question in questions:
        key = question["key"]
        if not _question_is_visible(question, section, submitted):
            continue
        value = submitted.get(key)
        required = question.get("required", False)
        kind = question["type"]

        if kind == "checkbox":
            if not isinstance(value, bool) or (required and value is not True):
                raise HTTPException(status_code=422, detail=f"Please confirm: {question['label']}")
            continue

        if value is None or value == "":
            if required:
                raise HTTPException(status_code=422, detail=f"This field is required: {question['label']}")
            normalized.pop(key, None)
            continue

        if kind == "multi_select":
            allowed = {option["value"] for option in question.get("options", [])}
            if (
                not isinstance(value, list)
                or len(value) != len(set(value))
                or not set(value) <= allowed
                or (required and not value)
            ):
                raise HTTPException(status_code=422, detail=f"Choose valid options for: {question['label']}")
            continue

        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"Enter a valid answer for: {question['label']}")
        value = value.strip()
        if required and not value:
            raise HTTPException(status_code=422, detail=f"This field is required: {question['label']}")
        if len(value) > 5000:
            raise HTTPException(status_code=422, detail=f"This answer is too long: {question['label']}")
        if kind in {"select", "single_choice", "yes_no"}:
            allowed = {option["value"] for option in question.get("options", [])}
            if value not in allowed:
                raise HTTPException(status_code=422, detail=f"Choose a valid option for: {question['label']}")
        elif kind == "number" and value:
            maximum = 150 if key == "age" else datetime.now(timezone.utc).year + 1
            minimum = 0 if key == "age" else 1900
            if not value.isdigit() or int(value) < minimum or int(value) > maximum:
                raise HTTPException(status_code=422, detail=f"Enter a valid number for: {question['label']}")
        elif kind == "date" and value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"Enter a valid date for: {question['label']}") from exc
        elif kind == "email" and value:
            if parseaddr(value)[1] != value or value.casefold() != str(user.get("email", "")).casefold():
                raise HTTPException(status_code=422, detail="Email Address must match the authenticated account")
        normalized[key] = value

    return normalized


@router.get("/student-cumulative-form", response_model=SurveyForm)
async def get_student_cumulative_form(
    _user: CurrentUser,
    database=Depends(require_database),
) -> SurveyForm:
    return SurveyForm(**(await _get_form(database)))


@router.get("/student-cumulative-form/submissions/me", response_model=SurveySubmission)
async def get_my_cumulative_form_submission(
    user: CurrentUser,
    database=Depends(require_database),
) -> SurveySubmission:
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student role required")
    document = await database.form_submissions.find_one(
        {"form_key": FORM_KEY, "student_user_id": user["auth_user_id"]},
        {"_id": 0, "student_user_id": 0},
    )
    if document is None:
        raise HTTPException(status_code=404, detail="No submitted form was found")
    return SurveySubmission(**document)


@router.post(
    "/student-cumulative-form/submissions",
    response_model=SurveySubmission,
    status_code=status.HTTP_201_CREATED,
)
async def submit_student_cumulative_form(
    body: SurveySubmissionCreate,
    user: CurrentUser,
    database=Depends(require_database),
) -> SurveySubmission:
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student role required")

    form = await _get_form(database)
    answers = _validate_answers(form, body.answers, user)
    document = {
        "form_key": form["form_key"],
        "form_number": form["form_number"],
        "form_version": form["version"],
        "student_user_id": user["auth_user_id"],
        "answers": answers,
        "submitted_at": datetime.now(timezone.utc),
    }
    try:
        await database.form_submissions.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="This form has already been submitted") from exc
    document.pop("student_user_id")
    return SurveySubmission(**document)


@router.get(
    "/student-cumulative-form/submissions/students/{student_id}",
    response_model=StaffSurveySubmission,
)
async def get_student_cumulative_form_submission(
    student_id: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> StaffSurveySubmission:
    if user.get("role") not in {"counselor", "admin"}:
        raise HTTPException(status_code=403, detail="Counselor or admin role required")
    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=404, detail="Student not found")

    student = await database.app_users.find_one(
        {"_id": ObjectId(student_id), "role": "student"},
        {"auth_user_id": 1, "name": 1, "email": 1},
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    submission = await database.form_submissions.find_one(
        {"form_key": FORM_KEY, "student_user_id": student["auth_user_id"]},
        {"_id": 0, "student_user_id": 0},
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="No submitted form was found for this student")
    return StaffSurveySubmission(
        **submission,
        student_id=str(student["_id"]),
        student_name=student.get("name") or "Unknown student",
        student_email=student.get("email") or "",
    )

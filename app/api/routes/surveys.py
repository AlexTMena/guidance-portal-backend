from datetime import datetime, timezone
from email.utils import parseaddr
import re

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.security import CurrentUser
from app.data.exit_survey_forms import REQUESTABLE_FORM_KEYS
from app.data.student_cumulative_form import FORM_KEY
from app.db.mongo import require_database
from app.schemas.survey import (
    StaffSurveySubmission,
    StaffSurveyCatalogItem,
    StaffSurveyResponseItem,
    StaffSurveyResponsePage,
    AvailableSurvey,
    SurveyForm,
    SurveyAccessRequest,
    SurveySubmission,
    SurveySubmissionCreate,
)

router = APIRouter(prefix="/surveys", tags=["surveys"])


async def _get_form(database) -> dict:
    document = await database.forms.find_one({"form_key": FORM_KEY}, {"_id": 0})
    if document is None:
        raise HTTPException(status_code=503, detail="Student Cumulative Form is not seeded")
    return document


async def _get_form_by_key(database, form_key: str, user: dict) -> dict:
    document = await database.forms.find_one({"form_key": form_key}, {"_id": 0})
    if document is None:
        raise HTTPException(status_code=404, detail="Survey form not found")
    if document.get("access_mode") == "request" and user.get("role") == "student":
        request = await database.form_access_requests.find_one(
            {"form_key": form_key, "student_user_id": user["auth_user_id"]},
            {"_id": 1},
        )
        if request is None:
            raise HTTPException(status_code=403, detail="Request access to this form first")
    return document


def _require_student(user: dict) -> None:
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student role required")


def _require_staff(user: dict) -> None:
    if user.get("role") not in {"counselor", "admin"}:
        raise HTTPException(status_code=403, detail="Counselor or admin role required")


def _condition_matches(condition: dict | None, answers: dict) -> bool:
    if not condition:
        return True
    actual = answers.get(condition["question"])
    normalized_actual = _normalize_condition_value(actual)
    if "equals" in condition:
        return normalized_actual == _normalize_condition_value(condition["equals"])
    if "in" in condition:
        return normalized_actual in [_normalize_condition_value(value) for value in condition["in"]]
    if "contains" in condition:
        return isinstance(normalized_actual, list) and _normalize_condition_value(condition["contains"]) in normalized_actual
    return False


def _normalize_condition_value(value):
    if isinstance(value, str):
        return re.sub(r"[\s/-]+", "_", value.strip().casefold()).strip("_")
    if isinstance(value, list):
        return [_normalize_condition_value(item) for item in value]
    return value


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
@router.get("/available", response_model=list[AvailableSurvey])
async def list_available_surveys(
    user: CurrentUser,
    database=Depends(require_database),
) -> list[AvailableSurvey]:
    _require_student(user)
    forms = await database.forms.find({}, {"_id": 0}).sort("title", 1).to_list(length=1000)
    requests = await database.form_access_requests.find(
        {"student_user_id": user["auth_user_id"]},
        {"_id": 0, "form_key": 1, "requested_at": 1},
    ).to_list(length=1000)
    request_by_key = {request["form_key"]: request for request in requests}
    submissions = await database.form_submissions.find(
        {"student_user_id": user["auth_user_id"]},
        {"_id": 0, "form_key": 1, "submitted_at": 1},
    ).to_list(length=1000)
    submission_by_key = {submission["form_key"]: submission for submission in submissions}

    available = []
    for form in forms:
        request = request_by_key.get(form["form_key"])
        if form.get("access_mode") == "request" and request is None:
            continue
        submission = submission_by_key.get(form["form_key"])
        available.append(
            AvailableSurvey(
                form_key=form["form_key"],
                form_number=form["form_number"],
                title=form["title"],
                requested_at=request.get("requested_at") if request else None,
                submitted_at=submission.get("submitted_at") if submission else None,
            )
        )
    return available


@router.get("/staff/catalog", response_model=list[StaffSurveyCatalogItem])
async def list_staff_survey_catalog(
    user: CurrentUser,
    database=Depends(require_database),
) -> list[StaffSurveyCatalogItem]:
    _require_staff(user)
    forms = await database.forms.find(
        {}, {"_id": 0, "form_key": 1, "form_number": 1, "title": 1}
    ).sort("title", 1).to_list(length=1000)
    return [StaffSurveyCatalogItem(**form) for form in forms]


@router.get("/requests/me", response_model=list[SurveyAccessRequest])
async def list_my_survey_requests(
    user: CurrentUser,
    database=Depends(require_database),
) -> list[SurveyAccessRequest]:
    _require_student(user)
    forms = await database.forms.find(
        {"form_key": {"$in": list(REQUESTABLE_FORM_KEYS)}},
        {"_id": 0, "form_key": 1, "form_number": 1, "title": 1},
    ).to_list(length=len(REQUESTABLE_FORM_KEYS))
    requests = await database.form_access_requests.find(
        {
            "student_user_id": user["auth_user_id"],
            "form_key": {"$in": list(REQUESTABLE_FORM_KEYS)},
        },
        {"_id": 0, "form_key": 1, "requested_at": 1},
    ).to_list(length=len(REQUESTABLE_FORM_KEYS))
    submissions = await database.form_submissions.find(
        {
            "student_user_id": user["auth_user_id"],
            "form_key": {"$in": list(REQUESTABLE_FORM_KEYS)},
        },
        {"_id": 0, "form_key": 1, "submitted_at": 1},
    ).to_list(length=len(REQUESTABLE_FORM_KEYS))
    request_by_key = {request["form_key"]: request for request in requests}
    submission_by_key = {submission["form_key"]: submission for submission in submissions}
    return [
        SurveyAccessRequest(
            form_key=form["form_key"],
            form_number=form["form_number"],
            title=form["title"],
            requested_at=(request_by_key.get(form["form_key"]) or {}).get("requested_at"),
            submitted_at=(submission_by_key.get(form["form_key"]) or {}).get("submitted_at"),
        )
        for form in forms
    ]


@router.post("/requests/{form_key}", response_model=SurveyAccessRequest)
async def request_survey_access(
    form_key: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> SurveyAccessRequest:
    _require_student(user)
    if form_key not in REQUESTABLE_FORM_KEYS:
        raise HTTPException(status_code=404, detail="Survey form is not requestable")
    form = await database.forms.find_one(
        {"form_key": form_key, "access_mode": "request"},
        {"_id": 0, "form_key": 1, "form_number": 1, "title": 1},
    )
    if form is None:
        raise HTTPException(status_code=503, detail="The requested form is not seeded")

    now = datetime.now(timezone.utc)
    await database.form_access_requests.update_one(
        {"form_key": form_key, "student_user_id": user["auth_user_id"]},
        {
            "$setOnInsert": {
                "form_key": form_key,
                "student_user_id": user["auth_user_id"],
                "requested_at": now,
            }
        },
        upsert=True,
    )
    request = await database.form_access_requests.find_one(
        {"form_key": form_key, "student_user_id": user["auth_user_id"]},
        {"_id": 0, "requested_at": 1},
    )
    submission = await database.form_submissions.find_one(
        {"form_key": form_key, "student_user_id": user["auth_user_id"]},
        {"_id": 0, "submitted_at": 1},
    )
    return SurveyAccessRequest(
        **form,
        requested_at=request["requested_at"],
        submitted_at=submission.get("submitted_at") if submission else None,
    )


@router.get("/{form_key}", response_model=SurveyForm)
async def get_survey_form(
    form_key: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> SurveyForm:
    if user.get("role") not in {"student", "counselor", "admin"}:
        raise HTTPException(status_code=403, detail="Not authorized to view survey forms")
    return SurveyForm(**(await _get_form_by_key(database, form_key, user)))


@router.get("/{form_key}/submissions", response_model=StaffSurveyResponsePage)
async def list_staff_survey_responses(
    form_key: str,
    user: CurrentUser,
    database=Depends(require_database),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0, le=1_000_000),
) -> StaffSurveyResponsePage:
    _require_staff(user)
    form = await database.forms.find_one({"form_key": form_key}, {"_id": 0, "form_key": 1})
    if form is None:
        raise HTTPException(status_code=404, detail="Survey form not found")

    pipeline: list[dict] = [
        {"$match": {"form_key": form_key}},
        {
            "$lookup": {
                "from": "app_users",
                "localField": "student_user_id",
                "foreignField": "auth_user_id",
                "as": "student",
            }
        },
        {"$unwind": "$student"},
        {"$match": {"student.role": "student"}},
    ]
    search = q.strip()
    if search:
        escaped = re.escape(search)
        pipeline.append(
            {
                "$match": {
                    "$or": [
                        {"student.name": {"$regex": escaped, "$options": "i"}},
                        {"student.email": {"$regex": escaped, "$options": "i"}},
                    ]
                }
            }
        )
    pipeline.extend(
        [
            {"$sort": {"submitted_at": -1, "_id": -1}},
            {
                "$facet": {
                    "items": [
                        {"$skip": skip},
                        {"$limit": limit},
                        {
                            "$project": {
                                "_id": 0,
                                "student_id": {"$toString": "$student._id"},
                                "student_name": {
                                    "$ifNull": ["$student.name", "Unknown student"]
                                },
                                "student_email": {"$ifNull": ["$student.email", ""]},
                                "submitted_at": 1,
                            }
                        },
                    ],
                    "total": [{"$count": "value"}],
                }
            },
        ]
    )
    cursor = await database.form_submissions.aggregate(pipeline)
    results = await cursor.to_list(length=1)
    result = results[0] if results else {"items": [], "total": []}
    total = result["total"][0]["value"] if result["total"] else 0
    return StaffSurveyResponsePage(
        items=[StaffSurveyResponseItem(**item) for item in result["items"]],
        total=total,
        limit=limit,
        skip=skip,
    )


@router.get("/{form_key}/submissions/me", response_model=SurveySubmission)
async def get_my_survey_submission(
    form_key: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> SurveySubmission:
    _require_student(user)
    await _get_form_by_key(database, form_key, user)
    document = await database.form_submissions.find_one(
        {"form_key": form_key, "student_user_id": user["auth_user_id"]},
        {"_id": 0, "student_user_id": 0},
    )
    if document is None:
        raise HTTPException(status_code=404, detail="No submitted response was found")
    return SurveySubmission(**document)


@router.post(
    "/{form_key}/submissions",
    response_model=SurveySubmission,
    status_code=status.HTTP_201_CREATED,
)
async def submit_survey(
    form_key: str,
    body: SurveySubmissionCreate,
    user: CurrentUser,
    database=Depends(require_database),
) -> SurveySubmission:
    _require_student(user)
    form = await _get_form_by_key(database, form_key, user)
    answers = _validate_answers(form, body.answers, user)
    document = {
        "form_key": form_key,
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
    "/{form_key}/submissions/students/{student_id}",
    response_model=StaffSurveySubmission,
)
async def get_student_survey_submission(
    form_key: str,
    student_id: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> StaffSurveySubmission:
    _require_staff(user)
    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=404, detail="Student not found")
    form = await database.forms.find_one({"form_key": form_key}, {"_id": 0, "form_key": 1})
    if form is None:
        raise HTTPException(status_code=404, detail="Survey form not found")
    student = await database.app_users.find_one(
        {"_id": ObjectId(student_id), "role": "student"},
        {"auth_user_id": 1, "name": 1, "email": 1},
    )
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    submission = await database.form_submissions.find_one(
        {"form_key": form_key, "student_user_id": student["auth_user_id"]},
        {"_id": 0, "student_user_id": 0},
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="No submitted response was found")
    return StaffSurveySubmission(
        **submission,
        student_id=str(student["_id"]),
        student_name=student.get("name") or "Unknown student",
        student_email=student.get("email") or "",
    )

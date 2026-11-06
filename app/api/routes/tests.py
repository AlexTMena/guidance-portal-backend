from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import CurrentUser
from app.db.mongo import require_database
from app.schemas.response import StartedAttempt, StaffTestResponse, TestAnswers, TestResult
from app.schemas.test import TestCatalogItem, TestQuestion

router = APIRouter(prefix="/tests", tags=["tests"])

BDI_NAME = "Beck's Depression Inventory"
BDI_QUESTION_COUNT = 21


def _response_id(respondent_id: str, test_id: ObjectId, attempt_id: str) -> str:
    return sha256(f"{respondent_id}:{test_id}:{attempt_id}".encode()).hexdigest()


async def _bdi_context(test_id: str, database):
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=404, detail="Test not found")

    test_object_id = ObjectId(test_id)
    test = await database.tests.find_one({"_id": test_object_id}, {"name": 1})
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    if test.get("name") != BDI_NAME:
        raise HTTPException(status_code=409, detail="Submissions are not configured for this test")

    questions = await database.test_questions.find(
        {"test_id": test_object_id},
        {"_id": 0, "key": 1, "required": 1, "type": 1, "options": 1, "order": 1},
    ).sort("order", 1).to_list(length=BDI_QUESTION_COUNT + 1)
    if len(questions) != BDI_QUESTION_COUNT or any(
        question.get("type") != "single_choice" or not question.get("required", True)
        for question in questions
    ):
        raise HTTPException(status_code=503, detail="The Beck questionnaire is not configured correctly")
    expected_keys = {f"bdi-pdf-{number:02d}" for number in range(1, BDI_QUESTION_COUNT + 1)}
    if {question.get("key") for question in questions} != expected_keys:
        raise HTTPException(status_code=503, detail="The Beck question keys are not configured correctly")
    return test_object_id, questions


def _validated_answers(
    answers: dict[str, str], questions: list[dict], *, complete: bool
) -> tuple[dict[str, str], int | None]:
    question_by_key = {question["key"]: question for question in questions}
    unknown = answers.keys() - question_by_key.keys()
    if unknown:
        raise HTTPException(status_code=422, detail="Answers include unknown question keys")
    if complete and answers.keys() != question_by_key.keys():
        raise HTTPException(status_code=422, detail="Please answer all 21 questions before submitting")

    score = 0
    normalized: dict[str, str] = {}
    for key, value in answers.items():
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail="Each answer must be a selected option value")
        question = question_by_key[key]
        option = next(
            (option for option in question.get("options", []) if option.get("value") == value),
            None,
        )
        if (
            option is None
            or not isinstance(option.get("score"), int)
            or not 0 <= option["score"] <= 3
        ):
            raise HTTPException(status_code=422, detail="An answer contains an invalid option")
        normalized[key] = value
        score += option["score"]

    return normalized, score if complete else None


def _interpret_score(score: int) -> tuple[str, str]:
    if score <= 10:
        return (
            "Normal range (0–10)",
            "The uploaded questionnaire describes scores 1–10 as ups and downs considered normal. A score of 0 is the minimum possible and is grouped in this band.",
        )
    if score <= 16:
        return "Mild mood disturbance (11–16)", "The uploaded questionnaire places this score in the mild mood disturbance range."
    if score <= 20:
        return "Borderline clinical depression (17–20)", "The uploaded questionnaire places this score in the borderline range. This is a screening result, not a diagnosis."
    if score <= 30:
        return "Moderate depression (21–30)", "The uploaded questionnaire places this score in the moderate range. Please review it with your counselor."
    if score <= 40:
        return "Severe depression (31–40)", "The uploaded questionnaire places this score in the severe range. Please review it with your counselor."
    return "Extreme depression (41–63)", "The uploaded questionnaire places this score in the extreme range. Please contact your counselor to discuss support."


def _result(document: dict) -> TestResult:
    return TestResult(
        score=document["score"],
        max_score=63,
        category=document["category"],
        interpretation=document["interpretation"],
        submitted_at=document["submitted_at"],
    )


@router.get("", response_model=list[TestCatalogItem])
async def list_tests(
    _user: CurrentUser,
    database=Depends(require_database),
) -> list[TestCatalogItem]:
    documents = await database.tests.find({}, {"name": 1}).sort("name", 1).to_list()
    return [
        TestCatalogItem(id=str(document["_id"]), name=document["name"])
        for document in documents
    ]


@router.get("/{test_id}", response_model=TestCatalogItem)
async def get_test(
    test_id: str,
    _user: CurrentUser,
    database=Depends(require_database),
) -> TestCatalogItem:
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    document = await database.tests.find_one(
        {"_id": ObjectId(test_id)},
        {"name": 1},
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    return TestCatalogItem(id=str(document["_id"]), name=document["name"])


@router.get("/{test_id}/questions", response_model=list[TestQuestion])
async def list_test_questions(
    test_id: str,
    _user: CurrentUser,
    database=Depends(require_database),
) -> list[TestQuestion]:
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    test_object_id = ObjectId(test_id)
    if await database.tests.find_one({"_id": test_object_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    documents = await database.test_questions.find(
        {"test_id": test_object_id},
        {"test_id": 0},
    ).sort("order", 1).to_list()
    return [
        TestQuestion(id=str(document.pop("_id")), **document)
        for document in documents
    ]


@router.get("/{test_id}/responses/draft")
async def get_my_draft(
    test_id: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> dict:
    test_object_id, _ = await _bdi_context(test_id, database)
    document = await database.test_responses.find_one(
        {
            "respondent_id": user["auth_user_id"],
            "test_id": test_object_id,
            "status": "draft",
        },
        {"_id": 0, "answers": 1, "updated_at": 1, "attempt_id": 1},
        sort=[("updated_at", -1)],
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return document


@router.post("/{test_id}/responses/draft/start", response_model=StartedAttempt)
async def start_my_attempt(
    test_id: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> StartedAttempt:
    test_object_id, _ = await _bdi_context(test_id, database)
    respondent_id = user["auth_user_id"]
    existing_draft = await database.test_responses.find_one(
        {"respondent_id": respondent_id, "test_id": test_object_id, "status": "draft"},
        {"attempt_id": 1},
        sort=[("updated_at", -1)],
    )
    if existing_draft:
        return StartedAttempt(attempt_id=existing_draft["attempt_id"])

    now = datetime.now(timezone.utc)
    attempt_id = uuid4()
    document = {
        "_id": _response_id(respondent_id, test_object_id, str(attempt_id)),
        "attempt_id": str(attempt_id),
        "respondent_id": respondent_id,
        "test_id": test_object_id,
        "answers": {},
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    await database.test_responses.insert_one(document)
    return StartedAttempt(attempt_id=attempt_id)


@router.put("/{test_id}/responses/draft")
async def save_my_draft(
    test_id: str,
    body: TestAnswers,
    user: CurrentUser,
    database=Depends(require_database),
) -> dict[str, str]:
    test_object_id, questions = await _bdi_context(test_id, database)
    answers, _ = _validated_answers(body.answers, questions, complete=False)
    respondent_id = user["auth_user_id"]
    attempt_id = str(body.attempt_id)
    response_id = _response_id(respondent_id, test_object_id, attempt_id)
    now = datetime.now(timezone.utc)

    updated = await database.test_responses.update_one(
        {
            "_id": response_id,
            "respondent_id": respondent_id,
            "status": "draft",
        },
        {"$set": {"answers": answers, "updated_at": now}},
    )
    if not updated.matched_count:
        raise HTTPException(status_code=404, detail="Draft not found; start a new attempt")
    return {"status": "saved", "updated_at": now.isoformat()}


@router.post("/{test_id}/responses/submit", response_model=TestResult)
async def submit_my_answers(
    test_id: str,
    body: TestAnswers,
    user: CurrentUser,
    database=Depends(require_database),
) -> TestResult:
    test_object_id, questions = await _bdi_context(test_id, database)
    answers, score = _validated_answers(body.answers, questions, complete=True)
    assert score is not None
    category, interpretation = _interpret_score(score)
    respondent_id = user["auth_user_id"]
    attempt_id = str(body.attempt_id)
    response_id = _response_id(respondent_id, test_object_id, attempt_id)
    existing = await database.test_responses.find_one({"_id": response_id})
    if existing and existing.get("status") == "submitted":
        return _result(existing)

    now = datetime.now(timezone.utc)
    self_harm_question = next(
        question for question in questions if question["key"] == "bdi-pdf-09"
    )
    self_harm_score = next(
        option["score"]
        for option in self_harm_question["options"]
        if option["value"] == answers["bdi-pdf-09"]
    )
    document = {
        "respondent_id": respondent_id,
        "attempt_id": attempt_id,
        "test_id": test_object_id,
        "answers": answers,
        "status": "submitted",
        "score": score,
        "category": category,
        "interpretation": interpretation,
        "self_harm_follow_up_flag": self_harm_score > 0,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
        "submitted_at": now,
    }
    updated = await database.test_responses.update_one(
        {
            "_id": response_id,
            "respondent_id": respondent_id,
            "status": "draft",
        },
        {"$set": document},
    )
    if updated.matched_count:
        return _result({**document, "_id": response_id})

    existing = await database.test_responses.find_one({"_id": response_id})
    if existing and existing.get("status") == "submitted":
        return _result(existing)
    raise HTTPException(status_code=404, detail="Draft not found; start a new attempt")


@router.get("/{test_id}/responses/me", response_model=TestResult)
async def get_my_result(
    test_id: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> TestResult:
    test_object_id, _ = await _bdi_context(test_id, database)
    document = await database.test_responses.find_one(
        {
            "respondent_id": user["auth_user_id"],
            "test_id": test_object_id,
            "status": "submitted",
        },
        {"answers": 0, "respondent_id": 0},
        sort=[("submitted_at", -1)],
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Submitted result not found")
    return _result(document)


@router.get("/{test_id}/responses/staff", response_model=list[StaffTestResponse])
async def list_submitted_responses_for_staff(
    test_id: str,
    user: CurrentUser,
    database=Depends(require_database),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[StaffTestResponse]:
    if user.get("role") not in {"counselor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Counselor or admin role required",
        )
    test_object_id, _ = await _bdi_context(test_id, database)
    documents = await database.test_responses.find(
        {"test_id": test_object_id, "status": "submitted"},
        {"_id": 0},
    ).sort("submitted_at", -1).limit(limit).to_list(length=limit)
    respondent_ids = list({document["respondent_id"] for document in documents})
    users = await database.app_users.find(
        {"auth_user_id": {"$in": respondent_ids}},
        {"_id": 0, "auth_user_id": 1, "name": 1, "email": 1},
    ).to_list(length=limit)
    user_by_id = {user["auth_user_id"]: user for user in users}
    return [
        StaffTestResponse(
            attempt_id=document["attempt_id"],
            respondent_id=document["respondent_id"],
            respondent_name=user_by_id.get(document["respondent_id"], {}).get("name", "Unknown user"),
            respondent_email=user_by_id.get(document["respondent_id"], {}).get("email", ""),
            answers=document["answers"],
            score=document["score"],
            max_score=63,
            category=document["category"],
            interpretation=document["interpretation"],
            submitted_at=document["submitted_at"],
            self_harm_follow_up_flag=document.get("self_harm_follow_up_flag", False),
        )
        for document in documents
    ]

from datetime import datetime, timezone
from hashlib import sha256
import re
from uuid import UUID, uuid4

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core.security import CurrentUser
from app.db.mongo import require_database
from app.schemas.response import (
    StartedAttempt,
    StaffTestResponse,
    StaffTestResponseItem,
    StaffTestResponsePage,
    TestAnswers,
    TestResult,
    TestScaleResult,
)
from app.schemas.test import TestCatalogItem, TestQuestion

router = APIRouter(prefix="/tests", tags=["tests"])

BDI_NAME = "Beck's Depression Inventory"
DASS21_NAME = "Depression Anxiety Stress Scales - 21 (DASS21)"
BRS_NAME = "THE BRIEF RESILIENCE SCALE"
PCL5_NAME = "PTSD Checklist for DSM-5 (PCL-5)"
BDI_QUESTION_COUNT = 21
DASS21_QUESTION_COUNT = 21
BRS_QUESTION_COUNT = 6
PCL5_QUESTION_COUNT = 20
DASS21_SCALE_ITEMS = {
    "Depression": {3, 5, 10, 13, 16, 17, 21},
    "Anxiety": {2, 4, 7, 9, 15, 19, 20},
    "Stress": {1, 6, 8, 11, 12, 14, 18},
}
BRS_REVERSE_SCORED_ITEMS = {2, 4, 6}


def _response_id(respondent_id: str, test_id: ObjectId, attempt_id: str) -> str:
    return sha256(f"{respondent_id}:{test_id}:{attempt_id}".encode()).hexdigest()


def _require_student(user: dict) -> None:
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student role required to answer tests")


def _require_staff(user: dict) -> None:
    if user.get("role") not in {"counselor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Counselor or admin role required",
        )


async def _assessment_context(test_id: str, database):
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=404, detail="Test not found")

    test_object_id = ObjectId(test_id)
    test = await database.tests.find_one({"_id": test_object_id}, {"name": 1})
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    test_name = test.get("name")
    test_configs = {
        BDI_NAME: ("bdi-pdf", BDI_QUESTION_COUNT),
        DASS21_NAME: ("dass21-pdf", DASS21_QUESTION_COUNT),
        BRS_NAME: ("brs-pdf", BRS_QUESTION_COUNT),
        PCL5_NAME: ("pcl5-pdf", PCL5_QUESTION_COUNT),
    }
    config = test_configs.get(test_name)
    if config is None:
        raise HTTPException(status_code=409, detail="Submissions are not configured for this test")
    question_prefix, question_count = config

    questions = await database.test_questions.find(
        {"test_id": test_object_id},
        {"_id": 0, "key": 1, "required": 1, "type": 1, "options": 1, "order": 1, "scale": 1},
    ).sort("order", 1).to_list(length=question_count + 1)
    expected_values = (
        {"1", "2", "3", "4", "5"} if test_name == BRS_NAME
        else {"0", "1", "2", "3", "4"} if test_name == PCL5_NAME
        else {"0", "1", "2", "3"}
    )
    if len(questions) != question_count or any(
        question.get("type") != "single_choice"
        or not question.get("required", True)
        or len(question.get("options", [])) != len(expected_values)
        or {option.get("value") for option in question.get("options", [])} != expected_values
        or any(not isinstance(option.get("score"), int) for option in question.get("options", []))
        for question in questions
    ):
        raise HTTPException(status_code=503, detail="The assessment questions are not configured correctly")
    expected_keys = {f"{question_prefix}-{number:02d}" for number in range(1, question_count + 1)}
    if (
        {question.get("key") for question in questions} != expected_keys
        or {question.get("order") for question in questions} != set(range(1, question_count + 1))
        or any(question.get("key") != f"{question_prefix}-{question.get('order'):02d}" for question in questions)
    ):
        raise HTTPException(status_code=503, detail="The assessment question keys are not configured correctly")
    expected_scale_by_item = {
        number: scale
        for scale, numbers in DASS21_SCALE_ITEMS.items()
        for number in numbers
    }
    if test_name == DASS21_NAME and any(
        question.get("scale") != expected_scale_by_item[question["order"]]
        for question in questions
    ):
        raise HTTPException(status_code=503, detail="The DASS-21 scale assignments are not configured correctly")
    if test_name == BRS_NAME and any(
        option["score"] != (6 - int(option["value"]) if question["order"] in BRS_REVERSE_SCORED_ITEMS else int(option["value"]))
        for question in questions
        for option in question["options"]
    ):
        raise HTTPException(status_code=503, detail="The BRS reverse scoring is not configured correctly")
    if test_name == PCL5_NAME and any(
        option["score"] != int(option["value"])
        for question in questions
        for option in question["options"]
    ):
        raise HTTPException(status_code=503, detail="The PCL-5 scoring is not configured correctly")
    return test_object_id, test_name, questions


def _validated_answers(
    answers: dict[str, str], questions: list[dict], *, complete: bool
) -> dict[str, str]:
    question_by_key = {question["key"]: question for question in questions}
    unknown = answers.keys() - question_by_key.keys()
    if unknown:
        raise HTTPException(status_code=422, detail="Answers include unknown question keys")
    if complete and answers.keys() != question_by_key.keys():
        raise HTTPException(status_code=422, detail=f"Please answer all {len(question_by_key)} questions before submitting")

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
            or not 0 <= option["score"] <= 5
        ):
            raise HTTPException(status_code=422, detail="An answer contains an invalid option")
        normalized[key] = value
    return normalized


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
    score = document.get("score")
    return TestResult(
        attempt_id=document["attempt_id"],
        score=score,
        max_score=document.get("max_score", 63 if score is not None else None),
        category=document.get("category"),
        interpretation=document["interpretation"],
        submitted_at=document["submitted_at"],
        scale_results=[TestScaleResult(**item) for item in document.get("scale_results", [])],
    )


def _option_score(question: dict, answer: str) -> int:
    return next(option["score"] for option in question["options"] if option["value"] == answer)


def _dass_severity(scale: str, score: int) -> str:
    thresholds = {
        "Depression": ((9, "Normal"), (13, "Mild"), (20, "Moderate"), (27, "Severe")),
        "Anxiety": ((7, "Normal"), (9, "Mild"), (14, "Moderate"), (19, "Severe")),
        "Stress": ((14, "Normal"), (18, "Mild"), (25, "Moderate"), (33, "Severe")),
    }
    return next((label for upper_bound, label in thresholds[scale] if score <= upper_bound), "Extremely Severe")


def _assessment_result_fields(test_name: str, questions: list[dict], answers: dict[str, str]) -> dict:
    if test_name == BDI_NAME:
        score = sum(_option_score(question, answers[question["key"]]) for question in questions)
        category, interpretation = _interpret_score(score)
        self_harm_question = next(question for question in questions if question["key"] == "bdi-pdf-09")
        return {
            "score": score,
            "max_score": 63,
            "category": category,
            "interpretation": interpretation,
            "self_harm_follow_up_flag": _option_score(self_harm_question, answers[self_harm_question["key"]]) > 0,
            "scale_results": [],
        }

    if test_name == BRS_NAME:
        total = sum(_option_score(question, answers[question["key"]]) for question in questions)
        score = round(total / BRS_QUESTION_COUNT, 2)
        if score <= 2.99:
            category = "Low Resilience"
        elif score <= 4.30:
            category = "Normal Resilience"
        else:
            category = "High Resilience"
        return {
            "score": score,
            "max_score": 5,
            "category": category,
            "interpretation": (
                f"The BRS score indicates {category.lower()}. Higher scores indicate greater resilience. "
                "This self-report result is for discussion and is not a diagnosis."
            ),
            "self_harm_follow_up_flag": False,
            "scale_results": [],
        }

    if test_name == PCL5_NAME:
        score = sum(_option_score(question, answers[question["key"]]) for question in questions)
        if score < 31:
            category = "Below commonly used cutoff range"
        else:
            category = "At or above commonly used cutoff range"
        return {
            "score": score,
            "max_score": 80,
            "category": category,
            "interpretation": (
                f"The total symptom score is {score} out of 80. A cutoff in the 31–33 range is commonly used "
                "for screening, but the appropriate cutoff varies by population and purpose. This result is "
                "not a diagnosis; review it with a qualified counselor or health professional."
            ),
            "self_harm_follow_up_flag": False,
            "scale_results": [],
        }

    score_by_scale = {scale: 0 for scale in DASS21_SCALE_ITEMS}
    for question in questions:
        score_by_scale[question["scale"]] += _option_score(question, answers[question["key"]])
    scale_results = []
    for scale, raw_score in score_by_scale.items():
        score = raw_score * 2
        severity = _dass_severity(scale, score)
        scale_results.append({
            "scale": scale,
            "score": score,
            "max_score": 42,
            "severity": severity,
            "interpretation": f"The {scale.lower()} scale score is in the {severity.lower()} range.",
        })
    return {
        "score": None,
        "max_score": None,
        "category": None,
        "interpretation": (
            "DASS-21 results describe depression, anxiety, and stress symptoms. "
            "They are not a diagnosis and do not replace a face-to-face clinical interview. "
            "Discuss concerns with a qualified professional."
        ),
        "self_harm_follow_up_flag": False,
        "scale_results": scale_results,
    }


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
    _require_student(user)
    test_object_id, _, _ = await _assessment_context(test_id, database)
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
    _require_student(user)
    test_object_id, _, _ = await _assessment_context(test_id, database)
    respondent_id = user["auth_user_id"]
    if await database.test_responses.find_one(
        {"respondent_id": respondent_id, "test_id": test_object_id, "status": "submitted"},
        {"_id": 1},
    ):
        raise HTTPException(status_code=409, detail="You have already submitted this test")
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
    _require_student(user)
    test_object_id, _, questions = await _assessment_context(test_id, database)
    answers = _validated_answers(body.answers, questions, complete=False)
    respondent_id = user["auth_user_id"]
    if await database.test_responses.find_one(
        {"respondent_id": respondent_id, "test_id": test_object_id, "status": "submitted"},
        {"_id": 1},
    ):
        raise HTTPException(status_code=409, detail="You have already submitted this test")
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
    _require_student(user)
    test_object_id, test_name, questions = await _assessment_context(test_id, database)
    answers = _validated_answers(body.answers, questions, complete=True)
    result_fields = _assessment_result_fields(test_name, questions, answers)
    respondent_id = user["auth_user_id"]
    attempt_id = str(body.attempt_id)
    response_id = _response_id(respondent_id, test_object_id, attempt_id)
    existing = await database.test_responses.find_one({"_id": response_id})
    if existing and existing.get("status") == "submitted":
        return _result(existing)
    other_submission = await database.test_responses.find_one(
        {
            "respondent_id": respondent_id,
            "test_id": test_object_id,
            "status": "submitted",
            "attempt_id": {"$ne": attempt_id},
        },
        {"_id": 1},
    )
    if other_submission:
        raise HTTPException(status_code=409, detail="You have already submitted this test")

    now = datetime.now(timezone.utc)
    document = {
        "respondent_id": respondent_id,
        "attempt_id": attempt_id,
        "test_id": test_object_id,
        "answers": answers,
        "status": "submitted",
        **result_fields,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
        "submitted_at": now,
    }
    try:
        updated = await database.test_responses.update_one(
            {
                "_id": response_id,
                "respondent_id": respondent_id,
                "status": "draft",
            },
            {"$set": document},
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="You have already submitted this test") from exc
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
    _require_student(user)
    test_object_id, _, _ = await _assessment_context(test_id, database)
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


@router.get("/{test_id}/responses/staff", response_model=StaffTestResponsePage)
async def list_submitted_responses_for_staff(
    test_id: str,
    user: CurrentUser,
    database=Depends(require_database),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0, le=1_000_000),
) -> StaffTestResponsePage:
    _require_staff(user)
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=404, detail="Test not found")
    test_object_id = ObjectId(test_id)
    if await database.tests.find_one({"_id": test_object_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=404, detail="Test not found")

    pipeline: list[dict] = [
        {"$match": {"test_id": test_object_id, "status": "submitted"}},
        {
            "$lookup": {
                "from": "app_users",
                "localField": "respondent_id",
                "foreignField": "auth_user_id",
                "as": "respondent",
            }
        },
        {"$unwind": "$respondent"},
        {"$match": {"respondent.role": "student"}},
    ]
    search = q.strip()
    if search:
        escaped = re.escape(search)
        pipeline.append(
            {
                "$match": {
                    "$or": [
                        {"respondent.name": {"$regex": escaped, "$options": "i"}},
                        {"respondent.email": {"$regex": escaped, "$options": "i"}},
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
                                "attempt_id": 1,
                                "respondent_id": 1,
                                "student_id": {"$toString": "$respondent._id"},
                                "respondent_name": {
                                    "$ifNull": ["$respondent.name", "Unknown student"]
                                },
                                "respondent_email": {"$ifNull": ["$respondent.email", ""]},
                                "submitted_at": 1,
                            }
                        },
                    ],
                    "total": [{"$count": "value"}],
                }
            },
        ]
    )
    cursor = await database.test_responses.aggregate(pipeline)
    documents = await cursor.to_list(length=1)
    result = documents[0] if documents else {"items": [], "total": []}
    total = result["total"][0]["value"] if result["total"] else 0
    return StaffTestResponsePage(
        items=[StaffTestResponseItem(**item) for item in result["items"]],
        total=total,
        limit=limit,
        skip=skip,
    )


@router.get("/{test_id}/responses/{attempt_id}", response_model=StaffTestResponse)
async def get_submitted_response(
    test_id: str,
    attempt_id: UUID,
    user: CurrentUser,
    database=Depends(require_database),
) -> StaffTestResponse:
    role = user.get("role")
    if role not in {"student", "counselor", "admin"}:
        raise HTTPException(status_code=403, detail="Not authorized to view submitted responses")
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=404, detail="Submitted response not found")

    test_object_id = ObjectId(test_id)
    if await database.tests.find_one({"_id": test_object_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=404, detail="Submitted response not found")

    query = {
        "test_id": test_object_id,
        "attempt_id": str(attempt_id),
        "status": "submitted",
    }
    if role == "student":
        query["respondent_id"] = user["auth_user_id"]
    document = await database.test_responses.find_one(query, {"_id": 0})
    if document is None:
        raise HTTPException(status_code=404, detail="Submitted response not found")

    respondent = await database.app_users.find_one(
        {"auth_user_id": document["respondent_id"]},
        {"_id": 0, "name": 1, "email": 1, "role": 1},
    )
    if not respondent or respondent.get("role") != "student":
        raise HTTPException(status_code=404, detail="Submitted response not found")
    return StaffTestResponse(
        attempt_id=document["attempt_id"],
        respondent_id=document["respondent_id"],
        respondent_name=respondent.get("name", "Unknown student"),
        respondent_email=respondent.get("email", ""),
        answers=document["answers"],
        score=document.get("score"),
        max_score=document.get("max_score", 63 if document.get("score") is not None else None),
        category=document.get("category"),
        interpretation=document["interpretation"],
        submitted_at=document["submitted_at"],
        scale_results=[TestScaleResult(**item) for item in document.get("scale_results", [])],
        self_harm_follow_up_flag=document.get("self_harm_follow_up_flag", False),
    )

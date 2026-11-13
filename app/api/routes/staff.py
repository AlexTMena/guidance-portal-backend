import re
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import CurrentUser
from app.data.student_cumulative_form import FORM_KEY
from app.db.mongo import require_database
from app.schemas.staff import (
    StaffStudentSummary,
    StudentSurveySummary,
    StudentTestAttemptSummary,
    StudentTestSummary,
)
from app.schemas.user import StaffUser, StaffUserPage

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/users", response_model=StaffUserPage)
async def list_staff_users(
    user: CurrentUser,
    database=Depends(require_database),
    scope: Literal["all", "students"] = Query(default="students"),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0, le=1000000),
) -> StaffUserPage:
    role = user.get("role")
    if role not in {"admin", "counselor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff role required")
    if role == "counselor" and scope != "students":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Counselor access is limited to student accounts")

    query: dict = {}
    if scope == "students":
        query["role"] = "student"
    search = q.strip()
    if search:
        safe_search = re.escape(search)
        query["$or"] = [
            {"name": {"$regex": safe_search, "$options": "i"}},
            {"email": {"$regex": safe_search, "$options": "i"}},
        ]

    collection = database.app_users
    total = await collection.count_documents(query)
    documents = await (
        collection.find(
            query,
            {"auth_user_id": 1, "name": 1, "email": 1, "role": 1, "created_at": 1},
        )
        .sort([("name", 1), ("email", 1)])
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )

    submitted_student_ids: set[str] = set()
    if scope == "students":
        auth_user_ids = [
            document["auth_user_id"]
            for document in documents
            if document.get("auth_user_id")
        ]
        if auth_user_ids:
            submissions = await database.form_submissions.find(
                {
                    "form_key": FORM_KEY,
                    "student_user_id": {"$in": auth_user_ids},
                },
                {"_id": 0, "student_user_id": 1},
            ).to_list(length=len(auth_user_ids))
            submitted_student_ids = {
                submission["student_user_id"] for submission in submissions
            }

    return StaffUserPage(
        items=[
            StaffUser(
                id=str(document["_id"]),
                name=document.get("name") or "Unknown user",
                email=document.get("email") or "",
                role=document["role"],
                created_at=document.get("created_at"),
                registration_status=(
                    "complete"
                    if document.get("auth_user_id") in submitted_student_ids
                    else "incomplete"
                )
                if scope == "students"
                else None,
            )
            for document in documents
        ],
        total=total,
        limit=limit,
        skip=skip,
    )


@router.get("/users/{student_id}/summary", response_model=StaffStudentSummary)
async def get_student_summary(
    student_id: str,
    user: CurrentUser,
    database=Depends(require_database),
) -> StaffStudentSummary:
    if user.get("role") not in {"admin", "counselor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff role required")
    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    student = await database.app_users.find_one(
        {"_id": ObjectId(student_id), "role": "student"},
        {"auth_user_id": 1, "name": 1, "email": 1, "role": 1, "created_at": 1},
    )
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    student_user_id = student["auth_user_id"]
    form_documents = await database.forms.find(
        {}, {"form_key": 1, "title": 1, "form_number": 1, "access_mode": 1}
    ).sort("title", 1).to_list(length=1000)
    form_submissions = await database.form_submissions.find(
        {"student_user_id": student_user_id},
        {"_id": 1, "form_key": 1, "submitted_at": 1},
    ).to_list(length=1000)
    form_submission_by_key = {
        document["form_key"]: document for document in form_submissions
    }
    form_access_requests = await database.form_access_requests.find(
        {"student_user_id": student_user_id},
        {"_id": 0, "form_key": 1, "requested_at": 1},
    ).to_list(length=1000)
    request_by_key = {document["form_key"]: document for document in form_access_requests}
    surveys = []
    for form in form_documents:
        submission = form_submission_by_key.get(form["form_key"])
        surveys.append(
            StudentSurveySummary(
                form_key=form["form_key"],
                title=form.get("title") or form["form_key"],
                form_number=form.get("form_number") or "",
                access_mode=form.get("access_mode", "always"),
                requested_at=(request_by_key.get(form["form_key"]) or {}).get("requested_at"),
                submitted_at=submission.get("submitted_at") if submission else None,
                response_id=str(submission["_id"]) if submission else None,
            )
        )

    test_documents = await database.tests.find({}, {"name": 1}).sort("name", 1).to_list(length=1000)
    test_submissions = await database.test_responses.find(
        {"respondent_id": student_user_id, "status": "submitted"},
        {"_id": 0, "test_id": 1, "attempt_id": 1, "submitted_at": 1},
    ).sort("submitted_at", -1).to_list(length=10000)
    submissions_by_test: dict[str, list[StudentTestAttemptSummary]] = {}
    for submission in test_submissions:
        submissions_by_test.setdefault(str(submission["test_id"]), []).append(
            StudentTestAttemptSummary(
                attempt_id=submission["attempt_id"],
                submitted_at=submission["submitted_at"],
            )
        )
    tests = [
        StudentTestSummary(
            test_id=str(test["_id"]),
            name=test["name"],
            submissions=submissions_by_test.get(str(test["_id"]), []),
        )
        for test in test_documents
    ]

    return StaffStudentSummary(
        id=str(student["_id"]),
        name=student.get("name") or "Unknown student",
        email=student.get("email") or "",
        role=student["role"],
        registered_at=student.get("created_at"),
        surveys=surveys,
        tests=tests,
    )

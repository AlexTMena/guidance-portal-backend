from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.core.security import CurrentUser
from app.db.mongo import require_database
from app.schemas.counseling import CounselingEvent, StudentBookingCreate

router = APIRouter(prefix="/counseling", tags=["counseling"])
BDI_NAME = "Beck's Depression Inventory"
DASS21_NAME = "Depression Anxiety Stress Scales - 21 (DASS21)"
BRS_NAME = "THE BRIEF RESILIENCE SCALE"
PCL5_NAME = "PTSD Checklist for DSM-5 (PCL-5)"
SUPPORTED_TESTS = {BDI_NAME, DASS21_NAME, BRS_NAME, PCL5_NAME}
ACTIVE_STATUSES = {"booked", "claimed"}
MANILA = ZoneInfo("Asia/Manila")
BLOCK_SIZE = timedelta(minutes=30)


def _staff(user: dict) -> bool:
    return user.get("role") in {"counselor", "admin"}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event(document: dict, *, staff: bool, user_by_id: dict, test_name: str | None = None) -> CounselingEvent:
    status_value = document["status"]
    is_assessment = bool(document.get("assessment_attempt_id"))
    booking_type = "assessment" if is_assessment else "request"
    if staff:
        student = user_by_id.get(document.get("student_id"), {})
        accepted_by_id = document.get("accepted_by") or document.get("claimed_by")
        accepted_by = user_by_id.get(accepted_by_id, {})
        assessment_name = test_name or BDI_NAME
        short_name = {
            BDI_NAME: "BDI",
            DASS21_NAME: "DASS21",
            BRS_NAME: "BRS",
            PCL5_NAME: "PCL-5",
        }.get(assessment_name, assessment_name)
        title = (
            f"{short_name} - {student.get('name', 'Unknown student')}"
            if is_assessment and status_value in ACTIVE_STATUSES | {"needs_reschedule", "cancelled"}
            else f"Counseling - {student.get('name', 'Unknown student')}"
            if status_value in ACTIVE_STATUSES | {"needs_reschedule", "cancelled"}
            else "Available counseling"
        )
        return CounselingEvent(
            id=str(document["_id"]),
            starts_at=_utc(document["starts_at"]),
            ends_at=_utc(document["ends_at"]),
            status=status_value,
            title=title,
            booking_type=booking_type,
            attempt_id=document.get("assessment_attempt_id"),
            test_id=str(document["test_id"]) if is_assessment and document.get("test_id") else None,
            test_name=test_name if document.get("assessment_attempt_id") else None,
            student_note=document.get("student_note"),
            student_name=student.get("name") if document.get("student_id") else None,
            student_email=student.get("email") if document.get("student_id") else None,
            counselor_name=user_by_id.get(document.get("claimed_by"), {}).get("name"),
            accepted_by_name=accepted_by.get("name"),
            accepted_by_role=accepted_by.get("role"),
            accepted_at=document.get("accepted_at") or document.get("claimed_at"),
        )

    title = "Available counseling" if status_value == "available" else "My counseling appointment"
    return CounselingEvent(
        id=str(document["_id"]),
        starts_at=_utc(document["starts_at"]),
        ends_at=_utc(document["ends_at"]),
        status=status_value,
        title=title,
        booking_type=booking_type,
        student_note=document.get("student_note"),
        counselor_name=user_by_id.get(document.get("claimed_by"), {}).get("name"),
    )


async def _verify_submitted_attempt(database, attempt_id: str, student_id: str) -> dict:
    try:
        UUID(attempt_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Submitted assessment attempt not found") from exc

    response = await database.test_responses.find_one(
        {"attempt_id": attempt_id, "respondent_id": student_id, "status": "submitted"},
        {"_id": 0, "test_id": 1, "attempt_id": 1},
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Submitted assessment attempt not found")
    test = await database.tests.find_one({"_id": response["test_id"]}, {"name": 1})
    if test is None or test.get("name") not in SUPPORTED_TESTS:
        raise HTTPException(status_code=409, detail="Counseling booking requires a submitted supported assessment")
    return test


def _time_blocks(starts_at: datetime, ends_at: datetime) -> list[datetime]:
    blocks = []
    current = starts_at
    while current < ends_at:
        blocks.append(current)
        current += BLOCK_SIZE
    return blocks


@router.get("/appointments", response_model=list[CounselingEvent])
async def list_calendar_events(
    user: CurrentUser,
    database=Depends(require_database),
    start: datetime = Query(),
    end: datetime = Query(),
    attempt_id: str | None = Query(default=None, max_length=64),
    booking_type: str | None = Query(default=None, pattern="^(assessment|request)$"),
) -> list[CounselingEvent]:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise HTTPException(status_code=422, detail="A valid timezone-aware calendar range is required")
    if end - start > timedelta(days=100):
        raise HTTPException(status_code=422, detail="Calendar range cannot exceed 100 days")

    staff = _staff(user)
    query: dict = {}
    if staff:
        query = {
            "starts_at": {"$lt": _utc(end)},
            "ends_at": {"$gt": _utc(start)},
            "status": {"$ne": "available"},
        }
    else:
        if user.get("role") != "student":
            raise HTTPException(status_code=403, detail="Student or staff role required")
        if attempt_id:
            await _verify_submitted_attempt(database, attempt_id, user["auth_user_id"])
            booking_type = "assessment"
            query = {
                "student_id": user["auth_user_id"],
                "assessment_attempt_id": attempt_id,
                "status": {"$ne": "available"},
            }
        elif booking_type == "request":
            query = {
                "student_id": user["auth_user_id"],
                "booking_type": "request",
                "status": {"$ne": "available"},
                "starts_at": {"$lt": _utc(end)},
                "ends_at": {"$gt": _utc(start)},
            }
        else:
            raise HTTPException(status_code=422, detail="A request booking type or submitted attempt is required")
    documents = await database.counseling_slots.find(query).sort("starts_at", 1).to_list(length=500)
    user_ids = {
        value
        for document in documents
        for value in (document.get("student_id"), document.get("claimed_by"), document.get("accepted_by"))
        if value
    } if staff else set()
    user_by_id = {}
    if user_ids:
        users = await database.app_users.find(
            {"auth_user_id": {"$in": list(user_ids)}},
            {"_id": 0, "auth_user_id": 1, "name": 1, "email": 1, "role": 1},
        ).to_list(length=len(user_ids))
        user_by_id = {item["auth_user_id"]: item for item in users}

    test_name_by_id = {}
    if staff:
        test_ids = {document.get("test_id") for document in documents if document.get("test_id")}
        if test_ids:
            tests = await database.tests.find({"_id": {"$in": list(test_ids)}}, {"name": 1}).to_list(length=len(test_ids))
            test_name_by_id = {item["_id"]: item.get("name", BDI_NAME) for item in tests}
    return [
        _event(
            document,
            staff=staff,
            user_by_id=user_by_id,
            test_name=test_name_by_id.get(document.get("test_id")),
        )
        for document in documents
    ]


@router.post("/appointments", response_model=CounselingEvent, status_code=status.HTTP_201_CREATED)
async def create_student_booking(
    body: StudentBookingCreate,
    user: CurrentUser,
    database=Depends(require_database),
) -> CounselingEvent:
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Student role required")
    starts_at, ends_at = _utc(body.starts_at), _utc(body.ends_at)
    local_start, local_end = starts_at.astimezone(MANILA), ends_at.astimezone(MANILA)
    if (
        starts_at <= datetime.now(timezone.utc)
        or ends_at <= starts_at
        or ends_at - starts_at != timedelta(hours=1)
        or local_start.date() != local_end.date()
        or local_start.hour < 7
        or local_end.hour > 19
        or (local_end.hour == 19 and local_end.minute > 0)
        or local_start.minute not in {0, 30}
        or local_end.minute not in {0, 30}
        or local_start.second
        or local_end.second
    ):
        raise HTTPException(
            status_code=422,
            detail="Choose a future one-hour appointment on one day, starting between 7:00 AM and 6:00 PM Manila time",
        )
    test = None
    attempt_id = body.attempt_id
    if attempt_id:
        test = await _verify_submitted_attempt(database, attempt_id, user["auth_user_id"])
        prior = await database.counseling_slots.find_one(
            {"assessment_attempt_id": attempt_id, "student_id": user["auth_user_id"], "status": "cancelled"},
            {"_id": 1},
        )
        if prior:
            raise HTTPException(status_code=409, detail="This counseling request was canceled and cannot be booked again")
        if await database.counseling_slots.find_one({"active_attempt_id": attempt_id}, {"_id": 1}):
            raise HTTPException(status_code=409, detail="This assessment already has an active counseling booking")
    overlap = await database.counseling_slots.find_one(
        {
            "status": {"$in": list(ACTIVE_STATUSES)},
            "starts_at": {"$lt": ends_at},
            "ends_at": {"$gt": starts_at},
        },
        {"_id": 1},
    )
    if overlap:
        raise HTTPException(status_code=409, detail="That time overlaps an existing counseling appointment")

    booking_id = ObjectId()
    block_documents = [
        {"block_start": block, "booking_id": booking_id}
        for block in _time_blocks(starts_at, ends_at)
    ]
    try:
        await database.counseling_time_blocks.insert_many(block_documents, ordered=True)
    except (DuplicateKeyError, BulkWriteError) as exc:
        await database.counseling_time_blocks.delete_many({"booking_id": booking_id})
        raise HTTPException(status_code=409, detail="That time overlaps an existing counseling appointment") from exc

    document = {
        "_id": booking_id,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "status": "booked",
        "student_id": user["auth_user_id"],
        "booking_type": "assessment" if attempt_id else "request",
        "student_note": body.note,
        "booked_at": datetime.now(timezone.utc),
    }
    if attempt_id and test:
        document.update({
            "assessment_attempt_id": attempt_id,
            "active_attempt_id": attempt_id,
            "test_id": test.get("_id"),
        })
    try:
        await database.counseling_slots.insert_one(document)
    except DuplicateKeyError as exc:
        await database.counseling_time_blocks.delete_many({"booking_id": booking_id})
        raise HTTPException(status_code=409, detail="This assessment already has an active counseling booking") from exc
    except Exception:
        await database.counseling_time_blocks.delete_many({"booking_id": booking_id})
        raise
    return _event(document, staff=False, user_by_id={})


@router.post("/appointments/{slot_id}/claim", response_model=CounselingEvent)
async def claim_booking(slot_id: str, user: CurrentUser, database=Depends(require_database)) -> CounselingEvent:
    if not _staff(user):
        raise HTTPException(status_code=403, detail="Counselor or admin role required")
    if not ObjectId.is_valid(slot_id):
        raise HTTPException(status_code=404, detail="Appointment was not found")
    accepted_at = datetime.now(timezone.utc)
    document = await database.counseling_slots.find_one_and_update(
        {"_id": ObjectId(slot_id), "status": "booked"},
        {"$set": {
            "status": "claimed",
            "claimed_by": user["auth_user_id"],
            "claimed_at": accepted_at,
            "accepted_by": user["auth_user_id"],
            "accepted_at": accepted_at,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if document is None:
        raise HTTPException(status_code=409, detail="Appointment has already been accepted or is no longer active")
    student = await database.app_users.find_one({"auth_user_id": document.get("student_id")}, {"_id": 0, "auth_user_id": 1, "name": 1, "email": 1})
    accepting_staff = await database.app_users.find_one({"auth_user_id": user["auth_user_id"]}, {"_id": 0, "auth_user_id": 1, "name": 1, "role": 1})
    test = await database.tests.find_one({"_id": document.get("test_id")}, {"name": 1})
    user_by_id = {student["auth_user_id"]: student} if student else {}
    if accepting_staff:
        user_by_id[accepting_staff["auth_user_id"]] = accepting_staff
    return _event(
        document,
        staff=True,
        user_by_id=user_by_id,
        test_name=(test or {}).get("name"),
    )


async def _close_booking(slot_id: str, user: dict, database, next_status: str) -> CounselingEvent:
    if not _staff(user):
        raise HTTPException(status_code=403, detail="Counselor or admin role required")
    if not ObjectId.is_valid(slot_id):
        raise HTTPException(status_code=404, detail="Appointment was not found")
    current = await database.counseling_slots.find_one(
        {"_id": ObjectId(slot_id), "status": {"$in": ["booked", "claimed"]}},
        {"_id": 0, "accepted_by": 1, "accepted_at": 1, "claimed_by": 1, "claimed_at": 1},
    )
    if current is None:
        raise HTTPException(status_code=409, detail="Appointment is no longer active")
    update = {
        "$set": {
            "status": next_status,
            f"{next_status}_at": datetime.now(timezone.utc),
            "closed_by": user["auth_user_id"],
        },
        "$unset": {"claimed_by": ""},
    }
    accepted_by_id = current.get("accepted_by") or current.get("claimed_by")
    accepted_at = current.get("accepted_at") or current.get("claimed_at")
    if accepted_by_id:
        update["$set"]["accepted_by"] = accepted_by_id
    if accepted_at:
        update["$set"]["accepted_at"] = accepted_at
    # A canceled attempt keeps its unique attempt guard permanently. A postponed
    # attempt releases the guard so the student can choose a replacement slot.
    if next_status == "needs_reschedule":
        update["$unset"]["active_attempt_id"] = ""
    document = await database.counseling_slots.find_one_and_update(
        {"_id": ObjectId(slot_id), "status": {"$in": ["booked", "claimed"]}},
        update,
        return_document=ReturnDocument.AFTER,
    )
    if document is None:
        raise HTTPException(status_code=409, detail="Appointment is no longer active")
    await database.counseling_time_blocks.delete_many({"booking_id": document["_id"]})
    student = await database.app_users.find_one({"auth_user_id": document.get("student_id")}, {"_id": 0, "auth_user_id": 1, "name": 1, "email": 1})
    accepting_staff_id = document.get("accepted_by") or accepted_by_id
    accepting_staff = await database.app_users.find_one({"auth_user_id": accepting_staff_id}, {"_id": 0, "auth_user_id": 1, "name": 1, "role": 1}) if accepting_staff_id else None
    test = await database.tests.find_one({"_id": document.get("test_id")}, {"name": 1})
    user_by_id = {student["auth_user_id"]: student} if student else {}
    if accepting_staff:
        user_by_id[accepting_staff["auth_user_id"]] = accepting_staff
    return _event(
        document,
        staff=True,
        user_by_id=user_by_id,
        test_name=(test or {}).get("name"),
    )


@router.post("/appointments/{slot_id}/postpone", response_model=CounselingEvent)
async def postpone_booking(slot_id: str, user: CurrentUser, database=Depends(require_database)) -> CounselingEvent:
    return await _close_booking(slot_id, user, database, "needs_reschedule")


@router.post("/appointments/{slot_id}/cancel", response_model=CounselingEvent)
async def cancel_booking(slot_id: str, user: CurrentUser, database=Depends(require_database)) -> CounselingEvent:
    return await _close_booking(slot_id, user, database, "cancelled")



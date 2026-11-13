import os
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from pymongo import AsyncMongoClient
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.core.config import APP_ENV, DATABASE_NAME

_COUNSELING_BLOCK = timedelta(minutes=30)
logger = logging.getLogger(__name__)


def _occupied_blocks(starts_at: datetime, ends_at: datetime) -> list[datetime]:
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = starts_at.astimezone(timezone.utc) - epoch
    rounded_minutes = int(elapsed.total_seconds() // 60 // 30 * 30)
    current = epoch + timedelta(minutes=rounded_minutes)
    end = ends_at.astimezone(timezone.utc)
    blocks = []
    while current < end:
        blocks.append(current)
        current += _COUNSELING_BLOCK
    return blocks


async def _prepare_counseling_time_blocks(database) -> None:
    active = await database.counseling_slots.find(
        {"status": {"$in": ["booked", "claimed"]}},
        {"_id": 1, "starts_at": 1, "ends_at": 1},
    ).to_list(length=10000)
    active_ids = [appointment["_id"] for appointment in active]
    if active_ids:
        await database.counseling_time_blocks.delete_many({"booking_id": {"$nin": active_ids}})
    else:
        await database.counseling_time_blocks.delete_many({})

    # Preserve time reservations for any active appointments created before
    # direct student scheduling was enabled.
    for appointment in active:
        if await database.counseling_time_blocks.find_one({"booking_id": appointment["_id"]}, {"_id": 1}):
            continue
        block_documents = [
            {"block_start": block, "booking_id": appointment["_id"]}
            for block in _occupied_blocks(appointment["starts_at"], appointment["ends_at"])
        ]
        if block_documents:
            try:
                await database.counseling_time_blocks.insert_many(block_documents, ordered=False)
            except BulkWriteError:
                # Overlaps among legacy bookings already exist; reserve every
                # remaining free half-hour block so new bookings cannot add to them.
                pass


async def connect_mongodb(app) -> AsyncMongoClient | None:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        if APP_ENV == "production":
            raise RuntimeError("MONGODB_URI is required in production")
        app.state.mongo_client = None
        app.state.database = None
        return None
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000)
    await client.admin.command("ping")
    app.state.mongo_client = client
    app.state.database = client[DATABASE_NAME]
    await app.state.database.forms.create_index(
        [("form_key", 1)], unique=True, name="unique_form_key"
    )
    await app.state.database.form_submissions.create_index(
        [("form_key", 1), ("student_user_id", 1)],
        unique=True,
        name="one_cumulative_form_submission_per_student",
    )
    await app.state.database.form_submissions.create_index(
        [("form_key", 1), ("submitted_at", -1)],
        name="survey_submissions_by_form_and_date",
    )
    await app.state.database.form_access_requests.create_index(
        [("form_key", 1), ("student_user_id", 1)],
        unique=True,
        name="one_access_request_per_form_per_student",
    )
    await app.state.database.test_responses.create_index(
        [("respondent_id", 1), ("status", 1), ("submitted_at", -1)],
        name="student_submitted_test_history",
    )
    try:
        await app.state.database.test_responses.create_index(
            [("respondent_id", 1), ("test_id", 1)],
            unique=True,
            partialFilterExpression={"status": "submitted"},
            name="one_submission_per_student_test",
        )
    except DuplicateKeyError:
        logger.warning(
            "Could not create one_submission_per_student_test because duplicate "
            "submitted test responses exist. Run `python -m app.scripts.clear_test_responses` "
            "in this environment to reset them, then the index will be created on the next startup."
        )
    await app.state.database.counseling_slots.create_index(
        [("status", 1), ("starts_at", 1)], name="calendar_status_starts_at"
    )
    await app.state.database.counseling_slots.create_index(
        [("active_attempt_id", 1)],
        unique=True,
        partialFilterExpression={"active_attempt_id": {"$exists": True}},
        name="one_active_booking_per_attempt",
    )
    await app.state.database.counseling_time_blocks.create_index(
        [("block_start", 1)], unique=True, name="one_booking_per_time_block"
    )
    await _prepare_counseling_time_blocks(app.state.database)
    return client


def get_database(request: Request):
    return getattr(request.app.state, "database", None)


async def require_database(request: Request):
    database = get_database(request)
    if database is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is unavailable")
    return database

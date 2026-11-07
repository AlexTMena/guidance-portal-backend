import unittest
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.api.routes.counseling import (
    _event,
    _utc,
    cancel_booking,
    claim_booking,
    create_student_booking,
    postpone_booking,
)
from app.schemas.counseling import StudentBookingCreate

MANILA = ZoneInfo("Asia/Manila")


def matches(document, query):
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict):
            for operator, value in expected.items():
                if operator == "$in" and actual not in value:
                    return False
                if operator == "$gt" and not (actual is not None and actual > value):
                    return False
                if operator == "$lt" and not (actual is not None and actual < value):
                    return False
        elif actual != expected:
            return False
    return True


class MemoryCollection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])
        self.time_blocks = set()

    async def create_index(self, *args, **kwargs):
        return kwargs.get("name", "test_index")

    async def find_one(self, query, projection=None, **kwargs):
        return next((doc for doc in self.documents if matches(doc, query)), None)

    async def insert_many(self, documents, **kwargs):
        inserted = []
        for document in documents:
            key = document["block_start"]
            if key in self.time_blocks:
                if inserted:
                    self.documents.extend(inserted)
                raise BulkWriteError({"writeErrors": [{"code": 11000}], "nInserted": len(inserted)})
            self.time_blocks.add(key)
            inserted.append(dict(document))
        self.documents.extend(inserted)
        return SimpleNamespace(inserted_ids=[doc.get("_id") for doc in inserted])

    async def insert_one(self, document):
        if document.get("active_attempt_id") and any(
            doc.get("active_attempt_id") == document["active_attempt_id"]
            for doc in self.documents
        ):
            raise DuplicateKeyError("duplicate attempt")
        self.documents.append(dict(document))
        return SimpleNamespace(inserted_id=document["_id"])

    async def delete_many(self, query):
        before = len(self.documents)
        removed = [doc for doc in self.documents if matches(doc, query)]
        self.documents = [doc for doc in self.documents if not matches(doc, query)]
        for doc in removed:
            self.time_blocks.discard(doc.get("block_start"))
        return SimpleNamespace(deleted_count=before - len(self.documents))

    async def find_one_and_update(self, query, update, **kwargs):
        document = next((doc for doc in self.documents if matches(doc, query)), None)
        if document is None:
            return None
        for key, value in update.get("$set", {}).items():
            document[key] = value
        for key in update.get("$unset", {}):
            document.pop(key, None)
        return dict(document)


class MemoryDatabase:
    def __init__(self, attempt_id, respondent_id, test_id):
        self.tests = MemoryCollection([{"_id": test_id, "name": "Beck's Depression Inventory"}])
        self.test_responses = MemoryCollection([{
            "attempt_id": attempt_id,
            "respondent_id": respondent_id,
            "status": "submitted",
            "test_id": test_id,
        }])
        self.counseling_slots = MemoryCollection()
        self.counseling_time_blocks = MemoryCollection()
        self.app_users = MemoryCollection()


class CounselingCalendarTests(unittest.TestCase):
    def test_student_event_never_contains_another_students_identity(self):
        document = {
            "_id": "appointment-id",
            "starts_at": datetime(2027, 1, 1, 1, tzinfo=timezone.utc),
            "ends_at": datetime(2027, 1, 1, 2, tzinfo=timezone.utc),
            "status": "booked",
            "student_id": "secret-user-id",
            "assessment_attempt_id": "secret-attempt-id",
        }
        result = _event(
            document,
            staff=False,
            user_by_id={"secret-user-id": {"name": "Student Name", "email": "private@example.test"}},
            test_name="Private test",
        )
        self.assertEqual(result.title, "My counseling appointment")
        self.assertIsNone(result.student_name)
        self.assertIsNone(result.student_email)
        self.assertIsNone(result.attempt_id)
        self.assertIsNone(result.test_name)

    def test_staff_event_contains_appointment_details(self):
        document = {
            "_id": "appointment-id",
            "starts_at": datetime(2027, 1, 1, 1, tzinfo=timezone.utc),
            "ends_at": datetime(2027, 1, 1, 2, tzinfo=timezone.utc),
            "status": "claimed",
            "student_id": "student-id",
            "assessment_attempt_id": "attempt-id",
            "claimed_by": "counselor-id",
        }
        result = _event(
            document,
            staff=True,
            user_by_id={
                "student-id": {"name": "Student Name", "email": "student@example.test"},
                "counselor-id": {"name": "Counselor Name"},
            },
            test_name="Beck's Depression Inventory",
        )
        self.assertEqual(result.student_name, "Student Name")
        self.assertEqual(result.student_email, "student@example.test")
        self.assertEqual(result.counselor_name, "Counselor Name")
        self.assertEqual(result.attempt_id, "attempt-id")

    def test_booking_dates_require_timezones(self):
        with self.assertRaises(ValidationError):
            StudentBookingCreate(
                attempt_id="7b3d78df-54c1-4a93-9fb1-6414fc11fbcb",
                starts_at="2027-01-01T09:00:00",
                ends_at="2027-01-01T10:00:00",
            )

    def test_naive_mongo_datetime_is_interpreted_as_utc(self):
        self.assertEqual(_utc(datetime(2027, 1, 1, 1)).tzinfo, timezone.utc)


class CounselingBookingFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.student_id = "student-auth-id"
        self.attempt_id = "7b3d78df-54c1-4a93-9fb1-6414fc11fbcb"
        self.test_id = ObjectId()
        self.database = MemoryDatabase(self.attempt_id, self.student_id, self.test_id)
        self.student = {"auth_user_id": self.student_id, "role": "student"}
        self.counselor = {"auth_user_id": "counselor-auth-id", "role": "counselor"}
        self.admin = {"auth_user_id": "admin-auth-id", "role": "admin"}
        tomorrow = datetime.now(MANILA).date() + timedelta(days=1)
        self.start = datetime.combine(tomorrow, time(9), tzinfo=MANILA)

    def booking(self, start, end, attempt_id=None):
        return StudentBookingCreate(
            attempt_id=attempt_id or self.attempt_id,
            starts_at=start,
            ends_at=end,
        )

    async def test_booking_claim_postpone_replacement_and_cancel_terminal_state(self):
        first = await create_student_booking(
            self.booking(self.start, self.start + timedelta(hours=1)),
            self.student,
            self.database,
        )
        with self.assertRaises(HTTPException) as duplicate:
            await create_student_booking(
                self.booking(self.start + timedelta(hours=2), self.start + timedelta(hours=3)),
                self.student,
                self.database,
            )
        self.assertEqual(duplicate.exception.status_code, 409)

        claimed = await claim_booking(first.id, self.counselor, self.database)
        self.assertEqual(claimed.status, "claimed")
        with self.assertRaises(HTTPException) as second_claim:
            await claim_booking(first.id, {"auth_user_id": "another-counselor", "role": "counselor"}, self.database)
        self.assertEqual(second_claim.exception.status_code, 409)

        postponed = await postpone_booking(first.id, self.admin, self.database)
        self.assertEqual(postponed.status, "needs_reschedule")
        replacement = await create_student_booking(
            self.booking(self.start + timedelta(hours=2), self.start + timedelta(hours=3)),
            self.student,
            self.database,
        )
        self.assertEqual(replacement.status, "booked")
        canceled = await cancel_booking(replacement.id, self.admin, self.database)
        self.assertEqual(canceled.status, "cancelled")

        with self.assertRaises(HTTPException) as canceled_attempt:
            await create_student_booking(
                self.booking(self.start + timedelta(hours=4), self.start + timedelta(hours=5)),
                self.student,
                self.database,
            )
        self.assertEqual(canceled_attempt.exception.status_code, 409)

    async def test_any_student_booking_cannot_overlap_another_booking(self):
        other_attempt = "eae41e84-d694-4336-9276-0c462bb2f6cf"
        other_student = "another-student"
        self.database.test_responses.documents.append({
            "attempt_id": other_attempt,
            "respondent_id": other_student,
            "status": "submitted",
            "test_id": self.test_id,
        })
        await create_student_booking(
            self.booking(self.start, self.start + timedelta(hours=1)),
            self.student,
            self.database,
        )
        with self.assertRaises(HTTPException) as overlap:
            await create_student_booking(
                self.booking(self.start + timedelta(minutes=30), self.start + timedelta(minutes=90), other_attempt),
                {"auth_user_id": other_student, "role": "student"},
                self.database,
            )
        self.assertEqual(overlap.exception.status_code, 409)

    async def test_student_cannot_claim_a_booking(self):
        first = await create_student_booking(
            self.booking(self.start, self.start + timedelta(hours=1)),
            self.student,
            self.database,
        )
        with self.assertRaises(HTTPException) as forbidden:
            await claim_booking(first.id, self.student, self.database)
        self.assertEqual(forbidden.exception.status_code, 403)

    async def test_booking_rejects_times_outside_manila_hours_and_foreign_attempts(self):
        with self.assertRaises(HTTPException) as outside_hours:
            await create_student_booking(
                self.booking(self.start.replace(hour=6, minute=30), self.start.replace(hour=7, minute=30)),
                self.student,
                self.database,
            )
        self.assertEqual(outside_hours.exception.status_code, 422)

        with self.assertRaises(HTTPException) as foreign_attempt:
            await create_student_booking(
                self.booking(self.start, self.start + timedelta(hours=1), "8f359fc6-0635-4aae-9cd5-53f3cf870f82"),
                self.student,
                self.database,
            )
        self.assertEqual(foreign_attempt.exception.status_code, 404)

    async def test_booking_requires_exactly_one_hour(self):
        with self.assertRaises(HTTPException) as wrong_duration:
            await create_student_booking(
                self.booking(self.start, self.start + timedelta(minutes=30)),
                self.student,
                self.database,
            )
        self.assertEqual(wrong_duration.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()

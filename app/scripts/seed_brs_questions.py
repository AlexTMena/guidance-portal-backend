import os

from pymongo import MongoClient, UpdateOne


TEST_NAME = "THE BRIEF RESILIENCE SCALE"
REVERSE_SCORED_ITEMS = {2, 4, 6}
CHOICES = [
    ("1", "Strongly Disagree"),
    ("2", "Disagree"),
    ("3", "Neutral"),
    ("4", "Agree"),
    ("5", "Strongly Agree"),
]


def _item(number: int, prompt: str) -> dict:
    reverse = number in REVERSE_SCORED_ITEMS
    return {
        "key": f"brs-pdf-{number:02d}",
        "order": number,
        "type": "single_choice",
        "prompt": prompt,
        "required": True,
        "options": [
            {
                "value": value,
                "label": label,
                "score": 6 - int(value) if reverse else int(value),
            }
            for value, label in CHOICES
        ],
        "is_demo": False,
    }


QUESTIONS = [
    _item(1, "I tend to bounce back quickly after hard times."),
    _item(2, "I have a hard time making it through stressful events."),
    _item(3, "It does not take me long to recover from a stressful event."),
    _item(4, "It is hard for me to snap back when something bad happens."),
    _item(5, "I usually come through difficult times with little trouble."),
    _item(6, "I tend to take a long time to get over setbacks in my life."),
]


def main() -> None:
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri:
        raise SystemExit("MONGODB_URI is required. Set it in the backend environment.")
    if not database_name:
        raise SystemExit("MONGODB_DATABASE is required. Set it in the backend environment.")

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        database = client[database_name]
        test = database.tests.find_one({"name": TEST_NAME}, {"_id": 1})
        if test is None:
            raise SystemExit(
                f"Test '{TEST_NAME}' was not found in '{database_name}.tests'. "
                "Run the test catalog seed script first."
            )

        collection = database.test_questions
        collection.create_index([("test_id", 1), ("key", 1)], unique=True)
        collection.delete_many({"test_id": test["_id"], "is_demo": True})
        result = collection.bulk_write(
            [
                UpdateOne(
                    {"test_id": test["_id"], "key": question["key"]},
                    {
                        "$set": {"test_id": test["_id"], **question},
                        "$unset": {"question_set_version": ""},
                    },
                    upsert=True,
                )
                for question in QUESTIONS
            ],
            ordered=True,
        )

    print(
        f"Seeded {len(QUESTIONS)} questions for '{TEST_NAME}' "
        f"in '{database_name}.test_questions' "
        f"(inserted: {result.upserted_count}, updated: {result.modified_count})."
    )


if __name__ == "__main__":
    main()

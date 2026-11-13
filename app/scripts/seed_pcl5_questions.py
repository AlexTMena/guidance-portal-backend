import os

from pymongo import MongoClient, UpdateOne


TEST_NAME = "PTSD Checklist for DSM-5 (PCL-5)"
OPTIONS = [
    {"value": "0", "label": "Not at all", "score": 0},
    {"value": "1", "label": "A little bit", "score": 1},
    {"value": "2", "label": "Moderately", "score": 2},
    {"value": "3", "label": "Quite a bit", "score": 3},
    {"value": "4", "label": "Extremely", "score": 4},
]


def _item(number: int, prompt: str) -> dict:
    return {
        "key": f"pcl5-pdf-{number:02d}",
        "order": number,
        "type": "single_choice",
        "prompt": prompt,
        "required": True,
        "options": OPTIONS,
        "is_demo": False,
    }


QUESTIONS = [
    _item(1, "Repeated, disturbing, and unwanted memories of the stressful experience?"),
    _item(2, "Repeated, disturbing dreams of the stressful experience?"),
    _item(3, "Suddenly feeling or acting as if the stressful experience were actually happening again (as if you were actually back there reliving it)?"),
    _item(4, "Feeling very upset when something reminded you of the stressful experience?"),
    _item(5, "Having strong physical reactions when something reminded you of the stressful experience (for example, heart pounding, trouble breathing, sweating)?"),
    _item(6, "Avoiding memories, thoughts, or feelings related to the stressful experience?"),
    _item(7, "Avoiding external reminders of the stressful experience (for example, people, places, conversations, activities, objects, or situations)?"),
    _item(8, "Trouble remembering important parts of the stressful experience?"),
    _item(9, "Having strong negative beliefs about yourself, other people, or the world (for example, having thoughts such as: I am bad, there is something seriously wrong with me, no one can be trusted, the world is completely dangerous)?"),
    _item(10, "Blaming yourself or someone else for the stressful experience or what happened after it?"),
    _item(11, "Having strong negative feelings such as fear, horror, anger, guilt, or shame?"),
    _item(12, "Loss of interest in activities that you used to enjoy?"),
    _item(13, "Feeling distant or cut off from other people?"),
    _item(14, "Trouble experiencing positive feelings (for example, being unable to feel happiness or have loving feelings for people close to you)?"),
    _item(15, "Irritable behavior, angry outbursts, or acting aggressively?"),
    _item(16, "Taking too many risks or doing things that could cause you harm?"),
    _item(17, "Being superalert or watchful or on guard?"),
    _item(18, "Feeling jumpy or easily startled?"),
    _item(19, "Having difficulty concentrating?"),
    _item(20, "Trouble falling or staying asleep?"),
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

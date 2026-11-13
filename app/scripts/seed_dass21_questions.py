import os

from pymongo import MongoClient, UpdateOne


TEST_NAME = "Depression Anxiety Stress Scales - 21 (DASS21)"
OPTIONS = [
    {"value": "0", "score": 0, "label": "Did not apply to me at all"},
    {"value": "1", "score": 1, "label": "Applied to me to some degree, or some of the time"},
    {"value": "2", "score": 2, "label": "Applied to me to a considerable degree or a good part of time"},
    {"value": "3", "score": 3, "label": "Applied to me very much or most of the time"},
]


def _item(number: int, prompt: str, scale: str) -> dict:
    return {
        "key": f"dass21-pdf-{number:02d}",
        "order": number,
        "type": "single_choice",
        "prompt": prompt,
        "required": True,
        "options": OPTIONS,
        "scale": scale,
        "is_demo": False,
    }


QUESTIONS = [
    _item(1, "I found it hard to wind down", "Stress"),
    _item(2, "I was aware of dryness of my mouth", "Anxiety"),
    _item(3, "I couldn’t seem to experience any positive feeling at all", "Depression"),
    _item(4, "I experienced breathing difficulty (e.g. excessively rapid breathing, breathlessness in the absence of physical exertion)", "Anxiety"),
    _item(5, "I found it difficult to work up the initiative to do things", "Depression"),
    _item(6, "I tended to over-react to situations", "Stress"),
    _item(7, "I experienced trembling (e.g. in the hands)", "Anxiety"),
    _item(8, "I felt that I was using a lot of nervous energy", "Stress"),
    _item(9, "I was worried about situations in which I might panic and make a fool of myself", "Anxiety"),
    _item(10, "I felt that I had nothing to look forward to", "Depression"),
    _item(11, "I found myself getting agitated", "Stress"),
    _item(12, "I found it difficult to relax", "Stress"),
    _item(13, "I felt down-hearted and blue", "Depression"),
    _item(14, "I was intolerant of anything that kept me from getting on with what I was doing", "Stress"),
    _item(15, "I felt I was close to panic", "Anxiety"),
    _item(16, "I was unable to become enthusiastic about anything", "Depression"),
    _item(17, "I felt I wasn’t worth much as a person", "Depression"),
    _item(18, "I felt that I was rather touchy", "Stress"),
    _item(19, "I was aware of the action of my heart in the absence of physical exertion (e.g. sense of heart rate increase, heart missing a beat)", "Anxiety"),
    _item(20, "I felt scared without any good reason", "Anxiety"),
    _item(21, "I felt that life was meaningless", "Depression"),
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

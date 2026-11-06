import os

from pymongo import MongoClient, UpdateOne


TEST_NAME = "Beck's Depression Inventory"


def _item(number: int, statements: list[str]) -> dict:
    return {
        "key": f"bdi-pdf-{number:02d}",
        "order": number,
        "type": "single_choice",
        "prompt": "",
        "required": True,
        "options": [
            {"value": str(score), "score": score, "label": statement}
            for score, statement in enumerate(statements)
        ],
        "is_demo": False,
    }


QUESTIONS = [
    _item(1, [
        "I do not feel sad.",
        "I feel sad",
        "I am sad all the time and I can't snap out of it.",
        "I am so sad and unhappy that I can't stand it.",
    ]),
    _item(2, [
        "I am not particularly discouraged about the future.",
        "I feel discouraged about the future.",
        "I feel I have nothing to look forward to.",
        "I feel the future is hopeless and that things cannot improve.",
    ]),
    _item(3, [
        "I do not feel like a failure.",
        "I feel I have failed more than the average person.",
        "As I look back on my life, all I can see is a lot of failures.",
        "I feel I am a complete failure as a person.",
    ]),
    _item(4, [
        "I get as much satisfaction out of things as I used to.",
        "I don't enjoy things the way I used to.",
        "I don't get real satisfaction out of anything anymore.",
        "I am dissatisfied or bored with everything.",
    ]),
    _item(5, [
        "I don't feel particularly guilty.",
        "I feel guilty a good part of the time.",
        "I feel quite guilty most of the time.",
        "I feel guilty all of the time.",
    ]),
    _item(6, [
        "I don't feel I am being punished.",
        "I feel I may be punished.",
        "I expect to be punished.",
        "I feel I am being punished.",
    ]),
    _item(7, [
        "I don't feel disappointed in myself.",
        "I am disappointed in myself.",
        "I am disgusted with myself.",
        "I hate myself.",
    ]),
    _item(8, [
        "I don't feel I am any worse than anybody else.",
        "I am critical of myself for my weaknesses or mistakes.",
        "I blame myself all the time for my faults.",
        "I blame myself for everything bad that happens.",
    ]),
    _item(9, [
        "I don't have any thoughts of killing myself.",
        "I have thoughts of killing myself, but I would not carry them out.",
        "I would like to kill myself.",
        "I would kill myself if I had the chance.",
    ]),
    _item(10, [
        "I don't cry any more than usual.",
        "I cry more now than I used to.",
        "I cry all the time now.",
        "I used to be able to cry, but now I can't cry even though I want to.",
    ]),
    _item(11, [
        "I am no more irritated by things than I ever was.",
        "I am slightly more irritated now than usual.",
        "I am quite annoyed or irritated a good deal of the time.",
        "I feel irritated all the time.",
    ]),
    _item(12, [
        "I have not lost interest in other people.",
        "I am less interested in other people than I used to be.",
        "I have lost most of my interest in other people.",
        "I have lost all of my interest in other people.",
    ]),
    _item(13, [
        "I make decisions about as well as I ever could.",
        "I put off making decisions more than I used to.",
        "I have greater difficulty in making decisions more than I used to.",
        "I can't make decisions at all anymore.",
    ]),
    _item(14, [
        "I don't feel that I look any worse than I used to.",
        "I am worried that I am looking old or unattractive.",
        "I feel there are permanent changes in my appearance that make me look unattractive.",
        "I believe that I look ugly.",
    ]),
    _item(15, [
        "I can work about as well as before.",
        "It takes an extra effort to get started at doing something.",
        "I have to push myself very hard to do anything.",
        "I can't do any work at all.",
    ]),
    _item(16, [
        "I can sleep as well as usual.",
        "I don't sleep as well as I used to.",
        "I wake up 1-2 hours earlier than usual and find it hard to get back to sleep.",
        "I wake up several hours earlier than I used to and cannot get back to sleep.",
    ]),
    _item(17, [
        "I don't get more tired than usual.",
        "I get tired more easily than I used to.",
        "I get tired from doing almost anything.",
        "I am too tired to do anything.",
    ]),
    _item(18, [
        "My appetite is no worse than usual.",
        "My appetite is not as good as it used to be.",
        "My appetite is much worse now.",
        "I have no appetite at all anymore.",
    ]),
    _item(19, [
        "I haven't lost much weight, if any, lately.",
        "I have lost more than five pounds.",
        "I have lost more than ten pounds.",
        "I have lost more than fifteen pounds.",
    ]),
    _item(20, [
        "I am no more worried about my health than usual.",
        "I am worried about physical problems like aches, pains, upset stomach, or constipation.",
        "I am very worried about physical problems and it's hard to think of much else.",
        "I am so worried about my physical problems that I cannot think of anything else.",
    ]),
    _item(21, [
        "I have not noticed any recent change in my interest in sex.",
        "I am less interested in sex than I used to be.",
        "I have almost no interest in sex.",
        "I have lost interest in sex completely.",
    ]),
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

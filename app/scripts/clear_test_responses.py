import os

from pymongo import MongoClient


def main() -> None:
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri:
        raise SystemExit("MONGODB_URI is required. Set it in the backend environment.")
    if not database_name:
        raise SystemExit("MONGODB_DATABASE is required. Set it in the backend environment.")

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        database = client[database_name]
        result = database.test_responses.delete_many({})
        database.test_responses.create_index(
            [("respondent_id", 1), ("test_id", 1)],
            unique=True,
            partialFilterExpression={"status": "submitted"},
            name="one_submission_per_student_test",
        )

    print(
        f"Deleted {result.deleted_count} test responses from "
        f"'{database_name}.test_responses'. Test definitions, questions, and "
        "counseling appointments were not changed. The one-submission index is ready."
    )


if __name__ == "__main__":
    main()

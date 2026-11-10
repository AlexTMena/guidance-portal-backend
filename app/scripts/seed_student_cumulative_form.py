import os
from datetime import datetime, timezone

from pymongo import MongoClient

from app.data.student_cumulative_form import FORM_DEFINITION, FORM_KEY


def main() -> None:
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri:
        raise SystemExit("MONGODB_URI is required. Set it in the backend environment.")
    if not database_name:
        raise SystemExit("MONGODB_DATABASE is required. Set it in the backend environment.")

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        database = client[database_name]
        forms = database.forms
        forms.create_index("form_key", unique=True, name="unique_form_key")
        result = forms.update_one(
            {"form_key": FORM_KEY},
            {
                "$setOnInsert": {
                    **FORM_DEFINITION,
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    message = "inserted" if result.upserted_id else "already exists; left unchanged"
    question_count = sum(len(section["questions"]) for section in FORM_DEFINITION["sections"])
    print(
        f"Student Cumulative Form ({FORM_DEFINITION['form_number']}) {message} in "
        f"'{database_name}.forms' ({len(FORM_DEFINITION['sections'])} sections, "
        f"{question_count} questions)."
    )


if __name__ == "__main__":
    main()

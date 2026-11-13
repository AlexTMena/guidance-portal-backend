import os
from datetime import datetime, timezone

from pymongo import MongoClient

from app.data.exit_survey_forms import EXIT_SURVEY_FORMS


def main() -> None:
    uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DATABASE")
    if not uri:
        raise SystemExit("MONGODB_URI is required. Set it in the backend environment.")
    if not database_name:
        raise SystemExit("MONGODB_DATABASE is required. Set it in the backend environment.")

    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        forms = client[database_name].forms
        forms.create_index("form_key", unique=True, name="unique_form_key")
        inserted = 0
        unchanged = 0
        for form in EXIT_SURVEY_FORMS:
            result = forms.update_one(
                {"form_key": form["form_key"]},
                {
                    "$setOnInsert": {
                        **form,
                        "created_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            inserted += int(result.upserted_id is not None)
            unchanged += int(result.upserted_id is None)

    print(
        f"Exit survey forms seeded in '{database_name}.forms' "
        f"(inserted: {inserted}, already present: {unchanged})."
    )


if __name__ == "__main__":
    main()

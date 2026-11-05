import os

from pymongo import MongoClient, UpdateOne


TESTS = [
    "COLUMBIA-SUICIDE SEVERITY RATING SCALE (C-SSRS)",
    "Beck's Depression Inventory",
    "THE BRIEF RESILIENCE SCALE",
    "PTSD Checklist for DSM-5 (PCL-5)",
    "Depression Anxiety Stress Scales - 21 (DASS21)",
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
        collection = database["tests"]
        collection.create_index("name", unique=True)

        result = collection.bulk_write(
            [
                UpdateOne(
                    {"name": name},
                    {"$set": {"name": name}, "$unset": {"id": ""}},
                    upsert=True,
                )
                for name in TESTS
            ],
            ordered=True,
        )

    print(
        f"Seeded {len(TESTS)} tests in '{database_name}.tests' "
        f"(inserted: {result.upserted_count}, updated: {result.modified_count})."
    )


if __name__ == "__main__":
    main()

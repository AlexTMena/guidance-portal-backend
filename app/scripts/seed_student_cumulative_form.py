import os
from datetime import datetime, timezone

from pymongo import MongoClient

from app.data.student_cumulative_form import FORM_KEY, get_form_definition


SUPPORT_SECTION_KEY = "support-needed"
SUPPORT_PARENT_SECTION_KEY = "conditions-and-support-needs"
SUPPORT_QUESTION_KEY = "needs_school_support"


def _repair_support_sections(existing_sections: list[dict], canonical_sections: list[dict]) -> list[dict]:
    sections = [dict(section) for section in existing_sections]
    canonical_by_key = {section["key"]: section for section in canonical_sections}
    canonical_parent = canonical_by_key[SUPPORT_PARENT_SECTION_KEY]
    canonical_question = next(
        question for question in canonical_parent["questions"] if question["key"] == SUPPORT_QUESTION_KEY
    )
    canonical_support = canonical_by_key[SUPPORT_SECTION_KEY]

    parent_index = next(
        (index for index, section in enumerate(sections) if section.get("key") == SUPPORT_PARENT_SECTION_KEY),
        None,
    )
    if parent_index is None:
        parent_index = next(
            (
                index
                for index, section in enumerate(sections)
                if any(question.get("key") == SUPPORT_QUESTION_KEY for question in section.get("questions", []))
            ),
            None,
        )
    if parent_index is None:
        parent_index = next(
            index for index, section in enumerate(canonical_sections)
            if section["key"] == SUPPORT_PARENT_SECTION_KEY
        )
        sections.insert(parent_index, canonical_parent)
    else:
        parent = dict(sections[parent_index])
        questions = [dict(question) for question in parent.get("questions", [])]
        question_index = next(
            (index for index, question in enumerate(questions) if question.get("key") == SUPPORT_QUESTION_KEY),
            None,
        )
        if question_index is None:
            questions.append(canonical_question)
        else:
            questions[question_index] = canonical_question
        parent["questions"] = questions
        sections[parent_index] = parent

    sections = [section for section in sections if section.get("key") != SUPPORT_SECTION_KEY]
    parent_index = next(
        index for index, section in enumerate(sections)
        if section.get("key") == SUPPORT_PARENT_SECTION_KEY
        or any(question.get("key") == SUPPORT_QUESTION_KEY for question in section.get("questions", []))
    )
    sections.insert(parent_index + 1, canonical_support)
    return sections


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
        now = datetime.now(timezone.utc)
        definition = get_form_definition()
        form = forms.find_one({"form_key": FORM_KEY})
        if form is None:
            forms.update_one(
                {"form_key": FORM_KEY},
                {"$setOnInsert": {**definition, "created_at": now}},
                upsert=True,
            )
            form = forms.find_one({"form_key": FORM_KEY})
            message = "inserted" if form else "could not be loaded after insert"
        else:
            repaired_sections = _repair_support_sections(
                form.get("sections", []), definition["sections"]
            )
            if repaired_sections == form.get("sections", []):
                message = "already current"
            else:
                forms.update_one(
                    {"_id": form["_id"]},
                    {"$set": {"sections": repaired_sections, "updated_at": now}},
                )
                message = "support section repaired"

    question_count = sum(len(section["questions"]) for section in definition["sections"])
    print(
        f"Student Cumulative Form ({definition['form_number']}) {message} in "
        f"'{database_name}.forms' ({len(definition['sections'])} canonical sections, "
        f"{question_count} questions)."
    )


if __name__ == "__main__":
    main()

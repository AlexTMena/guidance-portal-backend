from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import CurrentUser
from app.db.mongo import require_database
from app.schemas.test import TestCatalogItem, TestQuestion

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("", response_model=list[TestCatalogItem])
async def list_tests(
    _user: CurrentUser,
    database=Depends(require_database),
) -> list[TestCatalogItem]:
    documents = await database.tests.find({}, {"name": 1}).sort("name", 1).to_list()
    return [
        TestCatalogItem(id=str(document["_id"]), name=document["name"])
        for document in documents
    ]


@router.get("/{test_id}", response_model=TestCatalogItem)
async def get_test(
    test_id: str,
    _user: CurrentUser,
    database=Depends(require_database),
) -> TestCatalogItem:
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    document = await database.tests.find_one(
        {"_id": ObjectId(test_id)},
        {"name": 1},
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    return TestCatalogItem(id=str(document["_id"]), name=document["name"])


@router.get("/{test_id}/questions", response_model=list[TestQuestion])
async def list_test_questions(
    test_id: str,
    _user: CurrentUser,
    database=Depends(require_database),
) -> list[TestQuestion]:
    if not ObjectId.is_valid(test_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    test_object_id = ObjectId(test_id)
    if await database.tests.find_one({"_id": test_object_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    documents = await database.test_questions.find(
        {"test_id": test_object_id},
        {"test_id": 0},
    ).sort("order", 1).to_list()
    return [
        TestQuestion(id=str(document.pop("_id")), **document)
        for document in documents
    ]

import re
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import CurrentUser
from app.db.mongo import require_database
from app.schemas.user import StaffUser, StaffUserPage

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/users", response_model=StaffUserPage)
async def list_staff_users(
    user: CurrentUser,
    database=Depends(require_database),
    scope: Literal["all", "students"] = Query(default="students"),
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0, le=1000000),
) -> StaffUserPage:
    role = user.get("role")
    if role not in {"admin", "counselor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff role required")
    if role == "counselor" and scope != "students":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Counselor access is limited to student accounts")

    query: dict = {}
    if scope == "students":
        query["role"] = "student"
    search = q.strip()
    if search:
        safe_search = re.escape(search)
        query["$or"] = [
            {"name": {"$regex": safe_search, "$options": "i"}},
            {"email": {"$regex": safe_search, "$options": "i"}},
        ]

    collection = database.app_users
    total = await collection.count_documents(query)
    documents = await (
        collection.find(query, {"name": 1, "email": 1, "role": 1, "created_at": 1})
        .sort([("name", 1), ("email", 1)])
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )
    return StaffUserPage(
        items=[
            StaffUser(
                id=str(document["_id"]),
                name=document.get("name") or "Unknown user",
                email=document.get("email") or "",
                role=document["role"],
                created_at=document.get("created_at"),
            )
            for document in documents
        ],
        total=total,
        limit=limit,
        skip=skip,
    )

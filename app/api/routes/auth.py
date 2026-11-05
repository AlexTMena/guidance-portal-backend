from fastapi import APIRouter

from app.core.security import CurrentUser
from app.schemas.user import UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserProfile)
async def read_current_user(user: CurrentUser) -> UserProfile:
    return UserProfile(google_sub=user["google_sub"], email=user["email"], name=user["name"], role=user["role"])

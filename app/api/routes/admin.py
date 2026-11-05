from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.mongo import require_database
from app.schemas.user import RoleUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.patch("/users/{google_sub}/role")
async def update_user_role(
    google_sub: str,
    body: RoleUpdate,
    user=Depends(get_current_user),
    database=Depends(require_database),
) -> dict[str, str]:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    if user["google_sub"] == google_sub:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admins cannot change their own role")
    result = await database.app_users.update_one(
        {"google_sub": google_sub},
        {"$set": {"role": body.role, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"google_sub": google_sub, "role": body.role}

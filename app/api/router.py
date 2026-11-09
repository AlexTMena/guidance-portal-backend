from fastapi import APIRouter

from app.api.routes import admin, auth, counseling, health, staff, tests

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(tests.router)
api_router.include_router(counseling.router)
api_router.include_router(staff.router)

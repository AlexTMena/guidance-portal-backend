import base64
import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import API_TOKEN_AUDIENCE, API_TOKEN_ISSUER
from app.db.mongo import get_database

bearer = HTTPBearer(auto_error=False)


def _public_key() -> str:
    encoded = os.getenv("API_TOKEN_PUBLIC_KEY_B64")
    if not encoded:
        raise HTTPException(status_code=503, detail="API token verification is not configured")
    try:
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=503, detail="API token verification is misconfigured") from exc


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        claims = jwt.decode(
            credentials.credentials,
            _public_key(),
            algorithms=["RS256"],
            issuer=API_TOKEN_ISSUER,
            audience=API_TOKEN_AUDIENCE,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=5,
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token") from exc
    if claims.get("token_use") != "bff":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")
    database = get_database(request)
    if database is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is unavailable")
    user = await database.app_users.find_one({"auth_user_id": claims["sub"]}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not provisioned")
    user["google_sub"] = str(user["google_sub"])
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]

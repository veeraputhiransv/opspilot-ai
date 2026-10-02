"""JWT access tokens and hashed refresh tokens."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import jwt

from app.core.errors import UnauthorizedError

ALGORITHM = "HS256"


def hash_refresh_token(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return token_urlsafe(48)


def encode_access_token(
    *,
    secret: str,
    user_id: UUID,
    organization_id: UUID,
    workspace_id: UUID,
    roles: list[str],
    ttl_minutes: int,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "org": str(organization_id),
        "ws": str(workspace_id),
        "roles": roles,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Access token is invalid or expired.") from exc
    if payload.get("typ") != "access":
        raise UnauthorizedError("Access token is invalid or expired.")
    return payload

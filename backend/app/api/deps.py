"""Request dependencies. No business rules here."""

from hashlib import sha256

from fastapi import Request

from app.core.errors import ForbiddenError, UnauthorizedError
from app.identity.context import ADMIN_ROLES, OPERATOR_ROLES, VIEWER_ROLES, AuthContext
from app.runtime import AppContext


def get_context(request: Request) -> AppContext:
    return request.app.state.ctx


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "local"


async def _limit(request: Request, bucket: str, limit: int) -> None:
    context = get_context(request)
    token = request.headers.get("authorization", "")
    identity = sha256(token.encode("utf-8")).hexdigest()[:16] if token else "anon"
    await context.limiter.check(
        f"{bucket}:{_client_id(request)}:{identity}",
        limit=limit,
        window_seconds=60,
    )


async def limit_writes(request: Request) -> None:
    context = get_context(request)
    await _limit(request, request.url.path, context.settings.rate_limit_per_minute)


async def limit_login(request: Request) -> None:
    await _limit(request, "login", get_context(request).settings.login_rate_per_minute)


async def limit_register(request: Request) -> None:
    await _limit(request, "register", get_context(request).settings.register_rate_per_minute)


async def limit_ingest(request: Request) -> None:
    await _limit(request, "ingest", get_context(request).settings.ingest_rate_per_minute)


async def limit_approval(request: Request) -> None:
    await _limit(request, "approval", get_context(request).settings.approval_rate_per_minute)


async def limit_ticket(request: Request) -> None:
    await _limit(request, "ticket", get_context(request).settings.ticket_rate_per_minute)


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    raise UnauthorizedError("Authentication is required.")


async def get_session_auth(request: Request) -> AuthContext:
    context = get_context(request)
    return await context.auth.context_from_access_token(_bearer(request))


async def get_ingest_auth(request: Request) -> AuthContext:
    context = get_context(request)
    token = _bearer(request)
    if token.startswith("ops_live_"):
        return await context.auth.context_from_api_key(token)
    auth = await context.auth.context_from_access_token(token)
    if not auth.has_role("admin", "operator"):
        raise ForbiddenError("Ingest requires an operator or a workspace API key.")
    return auth


def require_roles(*roles: str):
    allowed = frozenset(roles)

    async def dependency(request: Request) -> AuthContext:
        auth = await get_session_auth(request)
        if not auth.has_role(*allowed):
            raise ForbiddenError("You do not have permission for this action.")
        return auth

    return dependency


async def require_viewer(request: Request) -> AuthContext:
    auth = await get_session_auth(request)
    if not auth.has_role(*VIEWER_ROLES):
        raise ForbiddenError("You do not have permission for this action.")
    return auth


async def require_operator(request: Request) -> AuthContext:
    auth = await get_session_auth(request)
    if not auth.has_role(*OPERATOR_ROLES, "admin"):
        raise ForbiddenError("An operator role is required.")
    return auth


async def require_admin(request: Request) -> AuthContext:
    auth = await get_session_auth(request)
    if not auth.has_role(*ADMIN_ROLES):
        raise ForbiddenError("An admin role is required.")
    return auth

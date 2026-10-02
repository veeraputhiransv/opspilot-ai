"""Authentication routes. These are public except /me, workspace switch, and API keys."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.deps import (
    get_context,
    get_session_auth,
    limit_login,
    limit_register,
    limit_writes,
    require_roles,
)
from app.identity.context import ADMIN_ROLES, AuthContext
from app.runtime import AppContext
from app.schemas.auth import (
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyOut,
    LoginIn,
    RefreshIn,
    RegisterIn,
    TokenOut,
    WorkspaceSwitchIn,
)

router = APIRouter(prefix="/api/v1/auth")


def _token_out(pair) -> TokenOut:
    return TokenOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
        user_id=pair.user_id,
        organization_id=pair.organization_id,
        workspace_id=pair.workspace_id,
        roles=pair.roles,
    )


@router.post("/register", response_model=TokenOut)
async def register(
    body: RegisterIn,
    request: Request,
    context: AppContext = Depends(get_context),
    _: None = Depends(limit_register),
) -> TokenOut:
    pair = await context.auth.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        organization_name=body.organization_name,
        user_agent=request.headers.get("user-agent"),
    )
    return _token_out(pair)


@router.post("/demo", response_model=TokenOut)
async def demo_session(
    request: Request,
    context: AppContext = Depends(get_context),
    _: None = Depends(limit_login),
) -> TokenOut:
    pair = await context.auth.demo_login(request.headers.get("user-agent"))
    return _token_out(pair)


@router.get("/demo/status")
async def demo_status(context: AppContext = Depends(get_context)) -> dict:
    from sqlalchemy import select

    from app.models.identity import Organization, Workspace
    from app.seed.constants import DEMO_ORG_SLUG, DEMO_WORKSPACE_NAME, DEMO_WORKSPACE_SLUG

    available = False
    if context.settings.demo_seed_enabled:
        async with context.sessions() as session:
            row = await session.scalar(
                select(Workspace.id)
                .join(Organization, Organization.id == Workspace.organization_id)
                .where(Organization.slug == DEMO_ORG_SLUG, Workspace.slug == DEMO_WORKSPACE_SLUG)
            )
            available = row is not None
    return {
        "available": available,
        "workspace": DEMO_WORKSPACE_NAME,
        "enabled": context.settings.demo_seed_enabled,
    }


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    request: Request,
    context: AppContext = Depends(get_context),
    _: None = Depends(limit_login),
) -> TokenOut:
    pair = await context.auth.login(
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
    )
    return _token_out(pair)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    body: RefreshIn,
    request: Request,
    context: AppContext = Depends(get_context),
) -> TokenOut:
    pair = await context.auth.refresh(body.refresh_token, request.headers.get("user-agent"))
    return _token_out(pair)


@router.post("/logout")
async def logout(body: RefreshIn, context: AppContext = Depends(get_context)) -> dict[str, bool]:
    await context.auth.logout(body.refresh_token)
    return {"ok": True}


@router.get("/me")
async def me(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(get_session_auth),
) -> dict:
    if auth.user_id is None:
        from app.core.errors import UnauthorizedError

        raise UnauthorizedError("Not authenticated.")
    return await context.auth.me(auth.user_id)


@router.post("/workspace", response_model=TokenOut)
async def switch_workspace(
    body: WorkspaceSwitchIn,
    request: Request,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(get_session_auth),
    _: None = Depends(limit_writes),
) -> TokenOut:
    if auth.user_id is None:
        from app.core.errors import UnauthorizedError

        raise UnauthorizedError("Not authenticated.")
    pair = await context.auth.switch_workspace(
        auth.user_id, body.workspace_id, request.headers.get("user-agent")
    )
    return _token_out(pair)


@router.post("/api-keys", response_model=ApiKeyCreatedOut)
async def create_api_key(
    body: ApiKeyCreateIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_roles(*ADMIN_ROLES)),
    _: None = Depends(limit_writes),
) -> ApiKeyCreatedOut:
    raw = await context.auth.create_ingest_key(auth, body.name)
    return ApiKeyCreatedOut(key=raw, prefix=raw[:12])


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_roles(*ADMIN_ROLES)),
) -> list[ApiKeyOut]:
    rows = await context.auth.list_ingest_keys(auth)
    return [ApiKeyOut.model_validate(row) for row in rows]


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: UUID,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_roles(*ADMIN_ROLES)),
    _: None = Depends(limit_writes),
) -> dict[str, bool]:
    await context.auth.revoke_ingest_key(auth, key_id)
    return {"ok": True}

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    organization_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class WorkspaceSwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: UUID
    organization_id: UUID
    workspace_id: UUID
    roles: list[str]


class ApiKeyCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)


class ApiKeyCreatedOut(BaseModel):
    key: str
    prefix: str


class ApiKeyOut(BaseModel):
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

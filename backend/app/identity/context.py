"""Request identity after authentication."""

from dataclasses import dataclass
from uuid import UUID

OPERATOR_ROLES = frozenset({"admin", "operator"})
VIEWER_ROLES = frozenset({"admin", "operator", "viewer", "auditor"})
ADMIN_ROLES = frozenset({"admin"})


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID | None
    organization_id: UUID
    workspace_id: UUID
    roles: tuple[str, ...]
    actor_label: str
    via: str  # "jwt" | "api_key"

    def has_role(self, *allowed: str) -> bool:
        return any(role in allowed for role in self.roles)

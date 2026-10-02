"""Identifiers for the isolated AcmeFlow demo workspace."""

DEMO_ORG_NAME = "AcmeFlow"
DEMO_ORG_SLUG = "acmeflow"
DEMO_WORKSPACE_NAME = "AcmeFlow Production"
DEMO_WORKSPACE_SLUG = "acmeflow-production"
DEMO_USER_NAME = "Alex Morgan"
DEMO_USER_EMAIL = "alex.morgan@acmeflow.example"
DEMO_USER_TITLE = "Incident Commander"
HISTORICAL_INCIDENT_NUMBERS = (
    "INC-0087",
    "INC-0092",
    "INC-0101",
    "INC-0114",
    "INC-0120",
    "INC-0066",
    "INC-0078",
)


def is_demo_workspace(org_slug: str | None, workspace_slug: str | None) -> bool:
    return org_slug == DEMO_ORG_SLUG and workspace_slug == DEMO_WORKSPACE_SLUG

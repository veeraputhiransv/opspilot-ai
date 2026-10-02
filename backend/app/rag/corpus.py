"""Authored incident memory. Wording is specific so retrieval can separate cases."""

from typing import TypedDict


class CorpusDocument(TypedDict):
    external_id: str
    title: str
    service: str
    symptoms: str
    root_cause: str
    resolution: str
    timeline_text: str


CORPUS: list[CorpusDocument] = [
    {
        "external_id": "INC-0087",
        "title": "Payment service connection pool exhaustion",
        "service": "payment-service",
        "symptoms": (
            "payment-service production database connection timeout. "
            "connection pool exhausted active connections reached configured maximum. "
            "error rate spike within a minute of deployment."
        ),
        "root_cause": (
            "DB connection pool exhaustion. A deploy reduced the payment-service "
            "Postgres pool size and checkout requests waited until they timed out."
        ),
        "resolution": (
            "Rolled payment-service back to the previous version and restored the prior "
            "pool configuration. Error rate returned to baseline."
        ),
        "timeline_text": "Alert, log review, deploy correlation, approved rollback, recovery.",
    },
    {
        "external_id": "INC-0094",
        "title": "Stripe API latency on payment intents",
        "service": "payment-service",
        "symptoms": (
            "stripe api.stripe.com latency elevated. payment_intent create returned 503. "
            "local database pool remained healthy."
        ),
        "root_cause": "Stripe API latency. The failure was upstream of payment-service.",
        "resolution": (
            "No rollback. Opened a provider incident, retried with the existing policy, "
            "and confirmed recovery when Stripe latency dropped."
        ),
        "timeline_text": "Alert, upstream logs, provider status, customer notice draft.",
    },
    {
        "external_id": "INC-0102",
        "title": "Redis outage broke cache-service",
        "service": "cache-service",
        "symptoms": (
            "redis connection refused on port 6379. cache unavailable. "
            "payment-service rate limit failed open."
        ),
        "root_cause": "Redis outage. The cache process could not open connections to Redis.",
        "resolution": "Restarted cache-service after Redis accepted connections again.",
        "timeline_text": "Alert, dependency check, approved restart, recovery.",
    },
    {
        "external_id": "INC-0118",
        "title": "Charge validation regression after deploy",
        "service": "payment-service",
        "symptoms": (
            "NullPointerException in charge validation. HTTP 500 spike on /v1/charges "
            "immediately after deployment. database pool healthy."
        ),
        "root_cause": "Bad deployment. The charge validation rewrite threw on valid cards.",
        "resolution": "Rolled payment-service back to the previous release.",
        "timeline_text": "Alert, stack trace, deploy diff, approved rollback.",
    },
    {
        "external_id": "INC-0044",
        "title": "Auth service JWT clock skew",
        "service": "auth-service",
        "symptoms": "jwt validation failed because of clock skew on auth-service token issuer.",
        "root_cause": "Auth token clock skew between the issuer and the verifier.",
        "resolution": "Corrected NTP on the auth issuer. No payment deploy was involved.",
        "timeline_text": "Auth errors, clock comparison, NTP fix.",
    },
]

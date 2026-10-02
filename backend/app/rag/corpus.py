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
        "title": "Payment Service Connection Pool Exhaustion",
        "service": "payment-service",
        "symptoms": (
            "payment-service production database connection timeout. "
            "connection pool exhausted active connections reached configured maximum. "
            "error rate spike within a minute of deployment."
        ),
        "root_cause": (
            "DB connection pool exhaustion. A configuration refactor reduced the "
            "payment-service Postgres pool max size and checkout requests timed out."
        ),
        "resolution": (
            "Rolled payment-service back to the previous version and restored the prior "
            "pool configuration. Error rate returned to baseline."
        ),
        "timeline_text": "Alert, log review, deploy correlation, approved rollback, recovery.",
    },
    {
        "external_id": "INC-0092",
        "title": "Stripe API Latency",
        "service": "payment-service",
        "symptoms": (
            "stripe api.stripe.com latency elevated. payment_intent create returned 503. "
            "checkout timeout. local database pool remained healthy."
        ),
        "root_cause": "Stripe API latency. Third-party provider degradation upstream of payment-service.",
        "resolution": (
            "No rollback. Enabled a circuit breaker and tightened retry configuration, "
            "then confirmed recovery when Stripe latency dropped."
        ),
        "timeline_text": "Alert, upstream logs, provider status, circuit breaker, recovery.",
    },
    {
        "external_id": "INC-0101",
        "title": "Redis Session Outage",
        "service": "redis-session",
        "symptoms": (
            "redis connection refused on port 6379. cache unavailable. "
            "session store memory exhaustion. payment-service rate limit failed open."
        ),
        "root_cause": "Redis memory exhaustion. The session store rejected new connections.",
        "resolution": "Evicted stale keys, raised the memory ceiling, and restarted redis-session.",
        "timeline_text": "Alert, dependency check, memory pressure, approved restart, recovery.",
    },
    {
        "external_id": "INC-0114",
        "title": "Bad Checkout Deployment",
        "service": "checkout-api",
        "symptoms": (
            "NullPointerException in charge validation. HTTP 500 spike on /v1/charges "
            "immediately after deployment. database pool healthy."
        ),
        "root_cause": "Bad deployment. A null handling regression shipped in the checkout validator.",
        "resolution": "Rolled checkout-api back to the previous release.",
        "timeline_text": "Alert, stack trace, deploy diff, approved rollback.",
    },
    {
        "external_id": "INC-0120",
        "title": "False Positive CPU Alert",
        "service": "notification-worker",
        "symptoms": "cpu utilization alert on notification-worker during a scheduled batch window.",
        "root_cause": "False-positive alert. A legitimate nightly batch process consumed CPU.",
        "resolution": "No production change. Widened the CPU window for the batch schedule.",
        "timeline_text": "Alert, process inventory, batch confirmation, detector tune.",
    },
    {
        "external_id": "INC-0044",
        "title": "Identity service JWT clock skew",
        "service": "identity-service",
        "symptoms": "jwt validation failed because of clock skew on identity-service token issuer.",
        "root_cause": "Auth token clock skew between the issuer and the verifier.",
        "resolution": "Corrected NTP on the identity issuer. No payment deploy was involved.",
        "timeline_text": "Auth errors, clock comparison, NTP fix.",
    },
]

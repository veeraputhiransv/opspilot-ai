"""Seeded telemetry for the five demo scenarios.

Timestamps are offsets from the incident start, so the story stays stable even
when the graph spends a few seconds between steps. "43 seconds" is computed
from these timestamps, not pasted into the UI as a constant.
"""

from datetime import UTC, datetime, timedelta


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def scenario_catalog() -> list[dict]:
    return [
        {
            "key": "db_pool",
            "label": "Database connection pool exhaustion",
            "summary": "Payment API error rate spikes just after a pool change.",
            "event": {
                "service": "payment-service",
                "environment": "production",
                "event_type": "error_rate_spike",
                "error_rate": 72,
                "message": "Database connection timeout",
            },
        },
        {
            "key": "stripe",
            "label": "Stripe API latency",
            "summary": "Payment intents stall on the Stripe API. The local pool is healthy.",
            "event": {
                "service": "payment-service",
                "environment": "production",
                "event_type": "upstream_latency",
                "error_rate": 41,
                "message": "Stripe API latency elevated",
            },
        },
        {
            "key": "bad_deploy",
            "label": "Bad deployment",
            "summary": "A charge-validation rewrite starts throwing on valid cards.",
            "event": {
                "service": "payment-service",
                "environment": "production",
                "event_type": "deploy_regression",
                "error_rate": 64,
                "message": "NullPointerException in charge validation",
            },
        },
        {
            "key": "redis",
            "label": "Redis outage",
            "summary": "cache-service cannot open connections to Redis.",
            "event": {
                "service": "cache-service",
                "environment": "production",
                "event_type": "dependency_down",
                "error_rate": 88,
                "message": "Redis connection refused",
            },
        },
        {
            "key": "false_positive",
            "label": "False-positive alert",
            "summary": "A brief flap recovers before a page should fire.",
            "event": {
                "service": "payment-service",
                "environment": "production",
                "event_type": "error_rate_spike",
                "error_rate": 1.2,
                "message": "Brief latency flap recovered in 10s",
            },
        },
    ]


def detect_scenario(event: dict) -> str:
    message = str(event.get("message", "")).lower()
    event_type = str(event.get("event_type", "")).lower()
    service = str(event.get("service", "")).lower()
    rate = float(event.get("error_rate") or 0)
    if rate < 5 or "flap" in message or event_type == "false_positive":
        return "false_positive"
    if "redis" in message or service.startswith("cache"):
        return "redis"
    if "stripe" in message:
        return "stripe"
    if (
        "nullpointer" in message
        or event_type == "deploy_regression"
        or "charge validation" in message
    ):
        return "bad_deploy"
    if "timeout" in message or "pool" in message or "database" in message:
        return "db_pool"
    return "unknown"


def scenario_title(key: str) -> str:
    titles = {
        "db_pool": "Payment API error spike",
        "stripe": "Stripe upstream latency",
        "bad_deploy": "Charge validation regression",
        "redis": "Redis dependency outage",
        "false_positive": "Transient error-rate flap",
        "unknown": "Unclassified production alert",
    }
    return titles.get(key, titles["unknown"])


def evidence_for(scenario: str, started_at: datetime) -> dict:
    builders = {
        "db_pool": _pool,
        "stripe": _stripe,
        "bad_deploy": _bad_deploy,
        "redis": _redis,
        "false_positive": _false_positive,
    }
    builder = builders.get(scenario, _unknown)
    return builder(started_at)


def _pool(started_at: datetime) -> dict:
    return {
        "logs": [
            _log(started_at, -8, "ERROR", "payment-service", "connection pool exhausted active=50 max=50 waiting=128"),
            _log(started_at, -6, "ERROR", "payment-service", "Database connection timeout after 30000ms"),
            _log(started_at, -5, "WARN", "payment-service", "stripe client retry scheduled delay=180ms"),
            _log(started_at, -4, "WARN", "payment-service", "tcp retransmits elevated on db subnet (1.7%)"),
            _log(started_at, -2, "INFO", "payment-service", "checkout request failed dependency=postgres"),
        ],
        "deployments": [
            _deploy("v2.8.1", "active", started_at - timedelta(seconds=43), "f39a812", "Maya Chen"),
            _deploy("v2.8.0", "previous", started_at - timedelta(days=3), "c12aa90", "Maya Chen"),
        ],
        "commits": [
            _commit("f39a812", "Refactor payment connection pool", "Maya Chen", started_at - timedelta(hours=2), ["src/db/pool.ts"]),
            _commit("a91c003", "Increase DB query timeout", "Maya Chen", started_at - timedelta(hours=5), ["src/db/client.ts"]),
            _commit("77bc12e", "Update Stripe retry configuration", "Jon Ellis", started_at - timedelta(days=9), ["src/stripe/retry.ts"]),
        ],
        "customer_reports": [
            _report("SUP-4412", "payment-service", "Checkout stuck on payment", "EU merchants report card charges failing since the last deploy. Contact avery.cole@northwind.example.", started_at - timedelta(minutes=4)),
            _report("SUP-4418", "payment-service", "Payment button spins then errors", "Multiple shoppers on the Northwind storefront cannot complete checkout.", started_at - timedelta(minutes=3)),
        ],
    }


def _stripe(started_at: datetime) -> dict:
    return {
        "logs": [
            _log(started_at, -6, "ERROR", "payment-service", "stripe API timeout api.stripe.com status=503 latency_ms=4200"),
            _log(started_at, -4, "ERROR", "payment-service", "payment_intent create failed upstream"),
            _log(started_at, -3, "INFO", "payment-service", "local db pool healthy active=12 max=50"),
        ],
        "deployments": [
            _deploy("v2.7.4", "active", started_at - timedelta(days=6), "77bc12e", "Jon Ellis"),
            _deploy("v2.7.3", "previous", started_at - timedelta(days=20), "ab10021", "Jon Ellis"),
        ],
        "commits": [
            _commit("77bc12e", "Update Stripe retry configuration", "Jon Ellis", started_at - timedelta(days=6), ["src/stripe/retry.ts"]),
            _commit("ab10021", "Rename charge logger fields", "Priya Shah", started_at - timedelta(days=20), ["src/log/fields.ts"]),
        ],
        "customer_reports": [
            _report("SUP-4501", "payment-service", "Cards decline after a long wait", "Shoppers wait about four seconds and then see a gateway error.", started_at - timedelta(minutes=6)),
        ],
    }


def _bad_deploy(started_at: datetime) -> dict:
    return {
        "logs": [
            _log(started_at, -5, "ERROR", "payment-service", "NullPointerException at ChargeValidator.apply during charge validation"),
            _log(started_at, -3, "ERROR", "payment-service", "HTTP 500 spike route=/v1/charges"),
            _log(started_at, -2, "INFO", "payment-service", "database pool healthy active=10 max=50"),
        ],
        "deployments": [
            _deploy("v2.9.0", "active", started_at - timedelta(seconds=70), "bb0192d", "Priya Shah"),
            _deploy("v2.8.9", "previous", started_at - timedelta(days=2), "e44d010", "Priya Shah"),
        ],
        "commits": [
            _commit("bb0192d", "Rewrite charge validation", "Priya Shah", started_at - timedelta(hours=3), ["src/charge/validator.ts"]),
        ],
        "customer_reports": [
            _report("SUP-4602", "payment-service", "Every card fails instantly", "Charges fail before the bank response. Started after the afternoon deploy.", started_at - timedelta(minutes=2)),
        ],
    }


def _redis(started_at: datetime) -> dict:
    return {
        "logs": [
            _log(started_at, -6, "ERROR", "cache-service", "Redis connection refused 10.0.4.12:6379"),
            _log(started_at, -4, "ERROR", "cache-service", "cache unavailable namespace=rate-limit"),
            _log(started_at, -2, "WARN", "payment-service", "payment-service failing open because cache is down"),
        ],
        "deployments": [
            _deploy("v1.4.2", "active", started_at - timedelta(days=12), "d19aa02", "Luis Ortega"),
            _deploy("v1.4.1", "previous", started_at - timedelta(days=30), "d19aa01", "Luis Ortega"),
        ],
        "commits": [
            _commit("d19aa02", "Adjust cache metric labels", "Luis Ortega", started_at - timedelta(days=12), ["src/metrics.ts"]),
        ],
        "customer_reports": [
            _report("SUP-4704", "cache-service", "Checkout rate limit errors", "A subset of requests fail when the cache dependency is down.", started_at - timedelta(minutes=5)),
        ],
    }


def _false_positive(started_at: datetime) -> dict:
    return {
        "logs": [
            _log(started_at, -15, "INFO", "payment-service", "error rate returned to baseline 0.4%"),
            _log(started_at, -12, "INFO", "payment-service", "no deploy in progress"),
            _log(started_at, -9, "INFO", "payment-service", "healthcheck pass"),
        ],
        "deployments": [
            _deploy("v2.8.0", "active", started_at - timedelta(days=3), "c12aa90", "Maya Chen"),
        ],
        "commits": [
            _commit("c12aa90", "Stabilize checkout retries", "Maya Chen", started_at - timedelta(days=3), ["src/checkout/retry.ts"]),
        ],
        "customer_reports": [],
    }


def _unknown(started_at: datetime) -> dict:
    return {
        "logs": [
            _log(started_at, -4, "ERROR", "payment-service", "error rate elevated without a signature"),
        ],
        "deployments": [
            _deploy("v2.8.0", "active", started_at - timedelta(days=4), "c12aa90", "Maya Chen"),
        ],
        "commits": [],
        "customer_reports": [],
    }


def _log(started_at: datetime, seconds: int, level: str, service: str, message: str) -> dict:
    return {
        "timestamp": _iso(started_at + timedelta(seconds=seconds)),
        "level": level,
        "service": service,
        "message": message,
    }


def _deploy(version: str, status: str, when: datetime, sha: str, author: str) -> dict:
    return {
        "version": version,
        "status": status,
        "deployed_at": _iso(when),
        "commit_sha": sha,
        "author": author,
    }


def _commit(sha: str, message: str, author: str, when: datetime, files: list[str]) -> dict:
    return {
        "sha": sha,
        "message": message,
        "author": author,
        "committed_at": _iso(when),
        "files": files,
    }


def _report(ref: str, service: str, title: str, body: str, when: datetime) -> dict:
    return {
        "external_ref": ref,
        "service": service,
        "title": title,
        "body": body,
        "source": "zendesk",
        "created_at": _iso(when),
    }

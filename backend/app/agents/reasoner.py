"""Deterministic diagnosis.

Scores are basis points from independent evidence signals. They are not model
probabilities. The same inputs always produce the same plan, which is what the
eval suite and the live demo both rely on.
"""

from datetime import datetime

from app.agents.state import Evidence, Hypothesis, ProposedAction, RcaDraft

_REPO_BY_SERVICE = {
    "payment-service": "opspilot-demo/payment-service",
    "cache-service": "opspilot-demo/cache-service",
}

_DESCRIPTIONS = {
    "db_pool": (
        "Checkout requests exhausted the Postgres connection pool after the latest "
        "payment-service deploy. New checkouts time out waiting for a connection."
    ),
    "stripe": (
        "Payment intent calls are failing on Stripe while the local database pool "
        "still has free connections."
    ),
    "bad_deploy": (
        "The current payment-service release throws while validating charges. "
        "The database pool is healthy."
    ),
    "redis": "cache-service cannot open connections to Redis, so cache reads are failing.",
    "network": "A weak network signal is present and does not explain the dominant errors.",
    "insufficient": (
        "The alert crossed the intake threshold, but no dependency, deploy, or "
        "exception signature is strong enough to name a cause."
    ),
    "false_positive": (
        "The error rate stayed near baseline and recovered without a fault signature."
    ),
}


def classify_severity(event: dict) -> str:
    """Severity comes from structured fields. Alert prose cannot lower it."""
    rate = float(event.get("error_rate") or 0)
    environment = str(event.get("environment") or "")
    message = str(event.get("message") or "").lower()
    event_type = str(event.get("event_type") or "").lower()
    if rate < 5 or "flap" in message or event_type == "false_positive":
        return "SEV-4"
    if environment == "production" and rate >= 50:
        return "SEV-1"
    if rate >= 20:
        return "SEV-2"
    if rate >= 5:
        return "SEV-3"
    return "SEV-4"


class DeterministicReasoner:
    name = "opspilot-deterministic-v1"

    def classify_severity(self, event: dict) -> str:
        return classify_severity(event)

    def hypothesize(self, evidence: Evidence) -> list[Hypothesis]:
        if classify_severity(evidence.event) == "SEV-4":
            return [
                Hypothesis(
                    key="false_positive",
                    title="False-positive alert",
                    description=_DESCRIPTIONS["false_positive"],
                    confidence=0.93,
                    evidence=[
                        "Error rate is below the paging threshold.",
                        "No deploy, dependency, or exception signature was correlated.",
                    ],
                    is_primary=True,
                )
            ]

        scored = [
            ("db_pool", _pool_hypothesis_title(evidence), *_score_pool(evidence)),
            ("stripe", "Stripe API Latency", *_score_stripe(evidence)),
            ("bad_deploy", "Bad Deployment", *_score_bad_deploy(evidence)),
            ("redis", "Redis Outage", *_score_redis(evidence)),
            ("network", "Network Issue", *_score_network(evidence)),
        ]
        hypotheses: list[Hypothesis] = []
        for key, title, points, bullets in scored:
            if points <= 0 or not bullets:
                continue
            if key == "db_pool" and evidence.customer_reports:
                count = len(evidence.customer_reports)
                noun = "report" if count == 1 else "reports"
                bullets.append(
                    f"{count} customer {noun} describe checkout payment failures during the spike."
                )
            hypotheses.append(
                Hypothesis(
                    key=key,
                    title=title,
                    description=_DESCRIPTIONS[key],
                    confidence=points / 100,
                    evidence=bullets,
                )
            )
        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    key="insufficient",
                    title="Insufficient evidence",
                    description=_DESCRIPTIONS["insufficient"],
                    confidence=0.34,
                    evidence=[
                        "No dependency, deploy, or exception signature was strong enough to rank."
                    ],
                )
            )
        hypotheses.sort(key=lambda item: item.confidence, reverse=True)
        hypotheses[0].is_primary = True
        return hypotheses

    def plan(self, evidence: Evidence, hypotheses: list[Hypothesis]) -> list[ProposedAction]:
        primary = hypotheses[0]
        if primary.key == "false_positive":
            return []

        service = str(evidence.event.get("service") or "")
        environment = str(evidence.event.get("environment") or "")
        actions: list[ProposedAction] = []
        active, previous = _versions(evidence.deployments)

        if primary.key in {"db_pool", "bad_deploy"} and active and previous:
            seconds = _seconds_since_deploy(evidence)
            commit = evidence.commits[0] if evidence.commits else None
            commit_bit = ""
            if commit:
                commit_bit = f" The deploy includes commit {commit['sha']} ({commit['message']})."
            if seconds is not None and seconds >= 0:
                reason = (
                    f"Error rate started increasing {seconds} seconds after "
                    f"{active['version']} deployment.{commit_bit}"
                )
            else:
                reason = (
                    f"The active release {active['version']} correlates with the failure."
                    f"{commit_bit}"
                )
            actions.append(
                ProposedAction(
                    tool_name="rollback_deployment",
                    title=(
                        f"Rollback {service} from {active['version']} to {previous['version']}"
                    ),
                    reason=reason.strip(),
                    expected_impact=(
                        f"Restores {service} to {previous['version']}, the previous release. "
                        "In-flight payment requests may be retried. Schema is not rolled back."
                    ),
                    confidence=primary.confidence,
                    arguments={
                        "service": service,
                        "from_version": active["version"],
                        "to_version": previous["version"],
                    },
                    evidence=list(primary.evidence),
                )
            )

        if primary.key == "redis":
            actions.append(
                ProposedAction(
                    tool_name="restart_service",
                    title=f"Restart {service}",
                    reason="The service is failing because Redis is refusing connections.",
                    expected_impact=(
                        f"Restarts {service} in {environment}. In-flight cache calls fail "
                        "for a short window. Redis data is not rebuilt by this action."
                    ),
                    confidence=primary.confidence,
                    arguments={"service": service, "environment": environment},
                    evidence=list(primary.evidence),
                )
            )

        repo = _REPO_BY_SERVICE.get(service, "opspilot-demo/platform")
        number = evidence.event.get("incident_number") or service
        actions.append(
            ProposedAction(
                tool_name="create_github_issue",
                title=f"Open tracking issue for {primary.title}",
                reason="Capture the hypothesis and evidence for the owning team.",
                expected_impact=(
                    f"Opens an issue in {repo}. It does not change production traffic."
                ),
                confidence=primary.confidence,
                arguments={
                    "repo": repo,
                    "title": f"[{number}] {primary.title}",
                    "body": primary.description
                    + "\n\n"
                    + "\n".join(f"- {item}" for item in primary.evidence),
                },
                evidence=list(primary.evidence),
            )
        )
        actions.append(
            ProposedAction(
                tool_name="draft_slack_message",
                title="Draft incident Slack update",
                reason="On-call needs a status note. Drafting does not post it.",
                expected_impact="Stores a message for #incidents. Nothing is sent.",
                confidence=primary.confidence,
                arguments={
                    "channel": "#incidents",
                    "text": (
                        f"{number}: {primary.title} on {service} ({environment}). "
                        f"Confidence {int(primary.confidence * 100)}%. "
                        "A remediation is waiting for approval. This message has not been sent."
                    ),
                },
                evidence=list(primary.evidence),
            )
        )
        actions.append(
            ProposedAction(
                tool_name="draft_customer_email",
                title="Draft customer notice",
                reason="Support may need language if the impact continues. This is a draft.",
                expected_impact=(
                    "Stores an email to the impacted_customers group. It is not delivered."
                ),
                confidence=primary.confidence,
                arguments={
                    "to_group": "impacted_customers",
                    "subject": f"{service} payment disruption",
                    "body": (
                        "We are investigating failed payment attempts. "
                        "This notice is a draft and has not been sent to customers."
                    ),
                },
                evidence=list(primary.evidence),
            )
        )
        return actions

    def write_rca(
        self,
        evidence: Evidence,
        hypotheses: list[Hypothesis],
        timeline_titles: list[str],
        executed: list[str],
        rejected: list[str],
    ) -> RcaDraft:
        primary = hypotheses[0]
        service = str(evidence.event.get("service") or "the service")
        environment = str(evidence.event.get("environment") or "production")
        rate = evidence.event.get("error_rate")
        number = str(evidence.event.get("incident_number") or "this incident")
        timeline = (
            " → ".join(timeline_titles)
            if timeline_titles
            else "Timeline was not recorded."
        )
        if primary.key == "false_positive":
            resolution = "No production change was made. The alert recovered on its own."
            corrective = ["Tune the detector so a sub-threshold flap does not page."]
            preventive = ["Require the error rate to hold above the threshold for two windows."]
            impact = f"{service} in {environment} did not sustain customer-visible errors."
        elif executed:
            resolution = (
                "Approved actions completed: "
                + ", ".join(executed)
                + ". Optional follow-ups may still be pending."
            )
            corrective = [f"Confirmed {item} and recorded the result." for item in executed]
            preventive = _preventive(primary.key)
            impact = (
                f"{service} in {environment} reached an error rate of {rate}% "
                "before the approved remediation."
            )
        else:
            resolution = "No remediation has been executed."
            if rejected:
                resolution += " Rejected proposals: " + ", ".join(rejected) + "."
            corrective = ["Review the rejected proposals with the service owner."]
            preventive = _preventive(primary.key)
            impact = f"{service} in {environment} reported an error rate of {rate}%."

        sources = ["Alert payload", "Severity policy"]
        if evidence.logs:
            sources.append("Application logs")
        if evidence.deployments:
            sources.append("Deployment history")
        if evidence.commits:
            sources.append("Git commits")
        if evidence.related_incidents:
            sources.append("Historical incidents")
        if evidence.customer_reports:
            sources.append("Customer reports")

        factors = list(primary.evidence) or ["Signals were too weak to list a contributing factor."]
        return RcaDraft(
            executive_summary=(
                f"{number} affected {service} in {environment}. "
                f"Primary hypothesis: {primary.title} "
                f"({int(primary.confidence * 100)}% evidence confidence). "
                f"{primary.description}"
            ),
            impact=impact,
            detection=(
                f"Ingested {_article(str(evidence.event.get('event_type') or 'alert'))} "
                f"{evidence.event.get('event_type')} alert "
                f"with error rate {rate}. Severity was classified by policy, not by the alert text."
            ),
            timeline_narrative=timeline,
            root_cause=f"{primary.title}. {primary.description}",
            contributing_factors=factors,
            resolution=resolution,
            corrective_actions=corrective,
            preventive_actions=preventive,
            confidence=primary.confidence,
            evidence_sources=sources,
        )


def _preventive(key: str) -> list[str]:
    table = {
        "db_pool": [
            "Canary pool-size changes and page on connection-wait time.",
            "Block deploys that shrink the pool without a load-test artifact.",
        ],
        "stripe": [
            "Alert on upstream latency separately from local error rate.",
            "Keep a provider status check in the first investigation step.",
        ],
        "bad_deploy": [
            "Add a charge-validation contract test to the deploy gate.",
            "Auto-halt rollout when the error rate jumps inside two minutes.",
        ],
        "redis": [
            "Page on Redis refused connections before dependent services fail.",
            "Document the restart approval path for cache-service.",
        ],
        "network": ["Keep network signals as secondary evidence unless loss is sustained."],
        "insufficient": ["Add a detector for this failure mode once a cause is confirmed."],
        "false_positive": ["Require the error rate to hold above the threshold for two windows."],
    }
    return table.get(key, ["Review the detector for this service."])


def _pool_hypothesis_title(evidence: Evidence) -> str:
    active, _previous = _versions(evidence.deployments)
    version = str((active or {}).get("version") or "").strip()
    if version:
        return f"Database connection pool exhaustion after {version} deployment"
    return "Database connection pool exhaustion"


def _logs(evidence: Evidence) -> str:
    return "\n".join(str(entry.get("message", "")) for entry in evidence.logs).lower()


def _versions(deployments: list[dict]) -> tuple[dict | None, dict | None]:
    ordered = sorted(deployments, key=lambda item: str(item.get("deployed_at", "")), reverse=True)
    if not ordered:
        return None, None
    if len(ordered) == 1:
        return ordered[0], None
    return ordered[0], ordered[1]


def _seconds_since_deploy(evidence: Evidence) -> int | None:
    active, _previous = _versions(evidence.deployments)
    if not active:
        return None
    started_raw = evidence.event.get("started_at")
    deployed_raw = active.get("deployed_at")
    if not started_raw or not deployed_raw:
        return None
    started = datetime.fromisoformat(str(started_raw))
    deployed = datetime.fromisoformat(str(deployed_raw))
    return int((started - deployed).total_seconds())


def _score_pool(evidence: Evidence) -> tuple[int, list[str]]:
    logs = _logs(evidence)
    message = str(evidence.event.get("message", "")).lower()
    points = 0
    bullets: list[str] = []
    if "pool exhaust" in logs or "active=50 max=50" in logs:
        points += 23
        bullets.append("DB active connections reached the configured maximum.")
    timeout = "connection timeout" in logs or "connection timeout" in message
    seconds = _seconds_since_deploy(evidence)
    if timeout and seconds is not None and 0 <= seconds <= 600:
        points += 22
        active, _previous = _versions(evidence.deployments)
        version = active["version"] if active else "the latest release"
        bullets.append(
            f"Connection timeouts increased immediately after deployment {version} ({seconds} seconds)."
        )
    elif timeout:
        points += 10
        bullets.append("Logs report database connection timeouts.")
    commit = next(
        (item for item in evidence.commits if "connection pool" in str(item.get("message", "")).lower()),
        None,
    )
    if commit:
        points += 23
        bullets.append(f"Recent commit {commit['sha']} modified connection pool configuration.")
    related = evidence.related_incidents[0] if evidence.related_incidents else None
    similarity = float(related.get("similarity") or 0) if related else 0.0
    if (
        related
        and similarity >= 0.4
        and "pool" in str(related.get("root_cause", "")).lower()
    ):
        points += 23
        bullets.append(
            f"Similar incident {related.get('external_id')} had the same symptoms "
            f"(similarity {similarity:.2f})."
        )
    return points, bullets


def _score_stripe(evidence: Evidence) -> tuple[int, list[str]]:
    logs = _logs(evidence)
    points = 0
    bullets: list[str] = []
    upstream = "api.stripe.com" in logs or ("stripe" in logs and ("503" in logs or "latency" in logs))
    if upstream:
        points += 50
        bullets.append("Stripe create calls returned errors with elevated upstream latency.")
        if "payment_intent" in logs:
            points += 20
            bullets.append("Payment intent creation failed before local persistence.")
    elif "stripe" in logs:
        points += 20
        bullets.append("Logs mention Stripe retries, without an upstream outage signature.")
    commit = next(
        (item for item in evidence.commits if "stripe" in str(item.get("message", "")).lower()),
        None,
    )
    if commit and points >= 50:
        points += 16
        bullets.append(f"Commit {commit['sha']} changed Stripe retry configuration.")
    elif commit and points > 0:
        points += 8
        bullets.append(f"An older commit {commit['sha']} changed Stripe retry configuration.")
    return points, bullets


def _score_bad_deploy(evidence: Evidence) -> tuple[int, list[str]]:
    logs = _logs(evidence)
    points = 0
    bullets: list[str] = []
    if "nullpointerexception" in logs or "charge validation" in logs:
        points += 55
        bullets.append("A charge-validation exception appeared in the request path.")
    seconds = _seconds_since_deploy(evidence)
    if points > 0 and seconds is not None and 0 <= seconds <= 600:
        points += 30
        active, _previous = _versions(evidence.deployments)
        version = active["version"] if active else "the current release"
        bullets.append(f"The exception started within {seconds} seconds of deployment {version}.")
    return points, bullets


def _score_redis(evidence: Evidence) -> tuple[int, list[str]]:
    logs = _logs(evidence)
    points = 0
    bullets: list[str] = []
    if "redis" in logs and ("refused" in logs or "unavailable" in logs):
        points += 72
        bullets.append("Redis connections were refused and the cache became unavailable.")
    if "6379" in logs:
        points += 15
        bullets.append("Failures targeted Redis port 6379.")
    return points, bullets


def _score_network(evidence: Evidence) -> tuple[int, list[str]]:
    logs = _logs(evidence)
    if "retransmit" in logs:
        return 17, [
            "TCP retransmits were slightly elevated and do not explain the error rate."
        ]
    if "latency" in logs and "stripe" in logs:
        return 19, ["Elevated upstream latency can look like a network fault."]
    if "network unreachable" in logs or "packet loss" in logs:
        return 70, ["Logs report a network reachability failure."]
    return 0, []


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"

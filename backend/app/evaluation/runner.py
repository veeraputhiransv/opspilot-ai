"""Score the five scripted incidents without a model API or a database.

Usage: python -m app.evaluation.runner
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.agents.reasoner import DeterministicReasoner
from app.agents.state import Evidence
from app.integrations.demo_data import evidence_for, scenario_catalog
from app.policies.risk_policy import RiskPolicyService
from app.rag.retriever import rank_corpus, retrieval_query

EXPECTATIONS: dict[str, dict[str, Any]] = {
    "db_pool": {
        "severity": "SEV-1",
        "cause": "db_pool",
        "include": ["rollback_deployment"],
        "exclude": ["restart_service", "send_customer_email", "send_slack_message"],
        "neighbor": "INC-0087",
    },
    "stripe": {
        "severity": "SEV-2",
        "cause": "stripe",
        "include": ["create_github_issue"],
        "exclude": ["rollback_deployment", "restart_service", "send_customer_email"],
        "neighbor": "INC-0092",
    },
    "bad_deploy": {
        "severity": "SEV-1",
        "cause": "bad_deploy",
        "include": ["rollback_deployment"],
        "exclude": ["restart_service", "send_customer_email"],
        "neighbor": "INC-0114",
    },
    "redis": {
        "severity": "SEV-1",
        "cause": "redis",
        "include": ["restart_service"],
        "exclude": ["rollback_deployment", "send_customer_email"],
        "neighbor": "INC-0101",
    },
    "false_positive": {
        "severity": "SEV-4",
        "cause": "false_positive",
        "include": [],
        "exclude": [
            "rollback_deployment",
            "restart_service",
            "send_customer_email",
            "create_github_issue",
        ],
        "neighbor": None,
    },
}


@dataclass
class ScenarioScore:
    key: str
    passed: bool
    detail: str


def evaluate() -> list[ScenarioScore]:
    reasoner = DeterministicReasoner()
    policy = RiskPolicyService()
    started = datetime.now(UTC)
    scores: list[ScenarioScore] = []
    for scenario in scenario_catalog():
        key = scenario["key"]
        expected = EXPECTATIONS[key]
        event = dict(scenario["event"])
        event["started_at"] = started.isoformat()
        event["incident_number"] = "INC-EVAL"
        bundle = evidence_for(key, started)
        related = rank_corpus(
            retrieval_query(
                message=event["message"],
                service=event["service"],
                logs=bundle["logs"],
                commits=bundle["commits"],
            ),
            limit=3,
        )
        evidence = Evidence(
            event=event,
            logs=bundle["logs"],
            deployments=bundle["deployments"],
            commits=bundle["commits"],
            related_incidents=related,
            customer_reports=bundle["customer_reports"],
        )
        severity = reasoner.classify_severity(event)
        hypotheses = reasoner.hypothesize(evidence)
        actions = reasoner.plan(evidence, hypotheses)
        tools = [action.tool_name for action in actions]
        rca = reasoner.write_rca(
            evidence,
            hypotheses,
            ["Alert received", "Root cause hypothesis generated"],
            [],
            [],
        )
        problems: list[str] = []
        if severity != expected["severity"]:
            problems.append(f"severity {severity} != {expected['severity']}")
        top = [item.key for item in hypotheses[:3]]
        if expected["cause"] not in top:
            problems.append(f"cause {expected['cause']} not in {top}")
        for name in expected["include"]:
            if name not in tools:
                problems.append(f"missing tool {name}")
        for name in expected["exclude"]:
            if name in tools:
                problems.append(f"unexpected tool {name}")
        if expected["neighbor"] and related[0]["external_id"] != expected["neighbor"]:
            problems.append(
                f"neighbor {related[0]['external_id']} != {expected['neighbor']}"
            )
        for action in actions:
            decision = policy.evaluate(action.tool_name, llm_suggested_risk="LOW")
            if decision.risk == "HIGH" and not decision.requires_approval:
                problems.append(f"{action.tool_name} high risk without approval")
        sections = [
            rca.executive_summary,
            rca.impact,
            rca.detection,
            rca.timeline_narrative,
            rca.root_cause,
            rca.resolution,
        ]
        if any(not section.strip() for section in sections):
            problems.append("rca section empty")
        if not rca.contributing_factors or not rca.corrective_actions or not rca.preventive_actions:
            problems.append("rca list empty")
        if not rca.evidence_sources:
            problems.append("rca evidence empty")
        scores.append(
            ScenarioScore(key=key, passed=not problems, detail="; ".join(problems) or "ok")
        )
    return scores


def main() -> int:
    scores = evaluate()
    failed = 0
    for score in scores:
        mark = "PASS" if score.passed else "FAIL"
        print(f"{mark}  {score.key:16}  {score.detail}")
        if not score.passed:
            failed += 1
    print(f"{len(scores) - failed}/{len(scores)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

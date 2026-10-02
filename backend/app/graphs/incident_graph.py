"""Fixed graphs.

Nodes do not pick their own successors. The only branch is whether a human
still has to approve an external write.
"""

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.state import IncidentState


def build_investigation_graph(workflow: Any) -> Any:
    graph = StateGraph(IncidentState)
    graph.add_node("EventIntakeAgent", workflow.event_intake)
    graph.add_node("TriageAgent", workflow.triage)
    graph.add_node("LogAnalysisAgent", workflow.log_analysis)
    graph.add_node("DeploymentAnalysisAgent", workflow.deployment_analysis)
    graph.add_node("InvestigationAgent", workflow.investigation)
    graph.add_node("HistoricalIncidentAgent", workflow.historical)
    graph.add_node("RootCauseAgent", workflow.root_cause)
    graph.add_node("ActionPlannerAgent", workflow.plan)
    graph.add_node("RiskPolicyAgent", workflow.policy_gate)
    graph.add_node("ExecutionAgent", workflow.execute)
    graph.add_node("HumanApprovalNode", workflow.human_approval)
    graph.add_node("ResolutionAgent", workflow.resolution)
    graph.add_node("RCAAgent", workflow.rca)

    graph.set_entry_point("EventIntakeAgent")
    graph.add_edge("EventIntakeAgent", "TriageAgent")
    graph.add_edge("TriageAgent", "LogAnalysisAgent")
    graph.add_edge("LogAnalysisAgent", "DeploymentAnalysisAgent")
    graph.add_edge("DeploymentAnalysisAgent", "InvestigationAgent")
    graph.add_edge("InvestigationAgent", "HistoricalIncidentAgent")
    graph.add_edge("HistoricalIncidentAgent", "RootCauseAgent")
    graph.add_edge("RootCauseAgent", "ActionPlannerAgent")
    graph.add_edge("ActionPlannerAgent", "RiskPolicyAgent")
    graph.add_edge("RiskPolicyAgent", "ExecutionAgent")
    graph.add_conditional_edges(
        "ExecutionAgent",
        workflow.route_after_plan,
        {"pause": "HumanApprovalNode", "resolve": "ResolutionAgent"},
    )
    graph.add_edge("HumanApprovalNode", END)
    graph.add_edge("ResolutionAgent", "RCAAgent")
    graph.add_edge("RCAAgent", END)
    return graph.compile()


def build_resume_graph(workflow: Any) -> Any:
    graph = StateGraph(IncidentState)
    graph.add_node("ExecutionAgent", workflow.execute)
    graph.add_node("ResolutionAgent", workflow.resolution)
    graph.add_node("RCAAgent", workflow.rca)
    graph.set_entry_point("ExecutionAgent")
    graph.add_conditional_edges(
        "ExecutionAgent",
        workflow.route_after_resume,
        {"resolve": "ResolutionAgent", "stop": END},
    )
    graph.add_edge("ResolutionAgent", "RCAAgent")
    graph.add_edge("RCAAgent", END)
    return graph.compile()

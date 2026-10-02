"""HTML export built from stored sections. User text is escaped."""

import html

from app.models import Incident, RcaReport


def render_rca_html(incident: Incident, report: RcaReport) -> str:
    def paragraph(value: str) -> str:
        lines = "".join(f"{html.escape(line)}<br>" for line in value.splitlines()) or html.escape(value)
        return f"<p>{lines}</p>"

    def items(values: list) -> str:
        body = "".join(f"<li>{html.escape(str(item))}</li>" for item in values)
        return f"<ul>{body}</ul>"

    confidence = int(round(report.confidence * 100))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(incident.incident_number)} RCA</title>
  <style>
    body {{ font-family: "IBM Plex Sans", "Segoe UI", sans-serif; color: #172033;
           max-width: 760px; margin: 40px auto; line-height: 1.5; }}
    h1 {{ font-size: 28px; margin-bottom: 0; }}
    .meta {{ color: #5c6573; margin-top: 4px; }}
    h2 {{ font-size: 16px; margin-top: 28px; letter-spacing: 0.04em;
         text-transform: uppercase; color: #334155; }}
    li {{ margin: 6px 0; }}
  </style>
</head>
<body>
  <h1>{html.escape(incident.incident_number)} root cause analysis</h1>
  <p class="meta">{html.escape(incident.service)} · {html.escape(incident.environment)} ·
  {html.escape(incident.severity or "untriaged")} · confidence {confidence}%</p>
  <h2>Executive summary</h2>
  {paragraph(report.executive_summary)}
  <h2>Impact</h2>
  {paragraph(report.impact)}
  <h2>Detection</h2>
  {paragraph(report.detection)}
  <h2>Timeline</h2>
  {paragraph(report.timeline_narrative)}
  <h2>Root cause</h2>
  {paragraph(report.root_cause)}
  <h2>Contributing factors</h2>
  {items(report.contributing_factors)}
  <h2>Resolution</h2>
  {paragraph(report.resolution)}
  <h2>Corrective actions</h2>
  {items(report.corrective_actions)}
  <h2>Preventive actions</h2>
  {items(report.preventive_actions)}
  <h2>Evidence sources</h2>
  {items(report.evidence_sources)}
</body>
</html>
"""

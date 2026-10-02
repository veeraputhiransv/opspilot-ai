"""Persistence boundary.

Reads are owned by QueryService and writes by IncidentWorkflow. Both open a
session, do their SQL, and commit. A third repository type would only forward
that session: each query has one caller. The workflow's transaction is the
unit of work for a node, which is what makes approval pause durable.
"""

"""Shared test environment. High rate limits so Redis-backed buckets do not starve the suite."""

import os

os.environ.setdefault("OPSPILOT_RATE_LIMIT_PER_MINUTE", "1000")
os.environ.setdefault("OPSPILOT_REGISTER_RATE_PER_MINUTE", "1000")
os.environ.setdefault("OPSPILOT_LOGIN_RATE_PER_MINUTE", "1000")
os.environ.setdefault("OPSPILOT_INGEST_RATE_PER_MINUTE", "1000")
os.environ.setdefault("OPSPILOT_APPROVAL_RATE_PER_MINUTE", "1000")
os.environ.setdefault("OPSPILOT_TICKET_RATE_PER_MINUTE", "1000")
os.environ.setdefault("OPSPILOT_STEP_DELAY_MS", "0")

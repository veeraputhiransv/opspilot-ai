"""Environment configuration.

Secrets come from the environment. Defaults are safe for the local demo.
"""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process settings. Unknown environment variables are ignored."""

    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_",
        env_file=".env",
        extra="ignore",
    )

    mode: str = Field(default="demo", pattern="^(demo|real)$")
    database_url: str = "postgresql+asyncpg://opspilot:opspilot@localhost:5432/opspilot"
    redis_url: str = "redis://localhost:6379/0"
    step_delay_ms: int = 700
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    log_level: str = "INFO"
    env: str = Field(default="development", pattern="^(development|production|test)$")
    jwt_secret: str = "dev-only-change-me-use-32-plus-bytes"
    vault_master_key: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    stream_ticket_seconds: int = 90
    bootstrap_enabled: bool = False
    demo_seed_enabled: bool = False
    demo_password: str = "AcmeFlow-operator-12"
    api_key: str = ""
    rate_limit_per_minute: int = 60
    login_rate_per_minute: int = 20
    register_rate_per_minute: int = 10
    ingest_rate_per_minute: int = 60
    approval_rate_per_minute: int = 30
    ticket_rate_per_minute: int = 60

    llm_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    github_token: str = ""
    github_allowed_repos: str = (
        "opspilot-demo/payment-service,opspilot-demo/cache-service,opspilot-demo/platform"
    )
    slack_webhook_url: str = ""
    slack_allowed_channels: str = "#incidents,#payments-oncall"
    rollback_webhook: str = ""
    restart_webhook: str = ""
    log_query_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    mail_allowed_groups: str = "impacted_customers,internal"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def reasoning_model(self) -> str:
        if self.llm_enabled and self.openai_api_key:
            return self.openai_model
        return "opspilot-deterministic-v1"

    def csv_set(self, raw: str) -> set[str]:
        return {item.strip() for item in raw.split(",") if item.strip()}

    @model_validator(mode="after")
    def production_requires_jwt_secret(self) -> "Settings":
        if self.env == "production" and self.jwt_secret.startswith("dev-only-change-me"):
            raise ValueError("OPSPILOT_JWT_SECRET must be set when OPSPILOT_ENV=production.")
        if self.env == "production" and len(self.vault_master_key.strip()) < 32:
            raise ValueError("OPSPILOT_VAULT_MASTER_KEY must be at least 32 characters in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

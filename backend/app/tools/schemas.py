"""Argument models. Extra fields are rejected so a model cannot smuggle a command."""

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchLogsArgs(StrictModel):
    service: str = Field(min_length=2, max_length=64)
    environment: str


class DeploymentsArgs(StrictModel):
    service: str = Field(min_length=2, max_length=64)


class CommitsArgs(StrictModel):
    service: str = Field(min_length=2, max_length=64)
    limit: int = Field(default=5, ge=1, le=20)


class PreviousIncidentsArgs(StrictModel):
    query: str = Field(min_length=3, max_length=4000)
    limit: int = Field(default=3, ge=1, le=10)


class CustomerReportsArgs(StrictModel):
    service: str = Field(min_length=2, max_length=64)


class GitHubIssueArgs(StrictModel):
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    title: str = Field(min_length=3, max_length=180)
    body: str = Field(min_length=3, max_length=8000)


class SlackArgs(StrictModel):
    channel: str = Field(pattern=r"^#[a-z0-9-]{1,40}$")
    text: str = Field(min_length=1, max_length=2000)


class EmailArgs(StrictModel):
    to_group: str = Field(pattern=r"^[a-z_]{3,40}$")
    subject: str = Field(min_length=3, max_length=140)
    body: str = Field(min_length=3, max_length=4000)


class RollbackArgs(StrictModel):
    service: str = Field(min_length=2, max_length=64)
    from_version: str = Field(pattern=r"^v\d+\.\d+\.\d+$")
    to_version: str = Field(pattern=r"^v\d+\.\d+\.\d+$")


class RestartArgs(StrictModel):
    service: str = Field(min_length=2, max_length=64)
    environment: str = Field(pattern=r"^(production|staging|development)$")

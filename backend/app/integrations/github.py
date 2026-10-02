"""GitHub adapter. Repository names must already be allowlisted."""

from app.integrations.http import request_json
from app.tools.base import ToolResult


class GitHubAdapter:
    def __init__(self, token: str, allowed_repos: set[str]) -> None:
        self.token = token
        self.allowed_repos = allowed_repos

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _repo(self, repo: str) -> str:
        if repo not in self.allowed_repos:
            raise ValueError(f"Repository is not allowlisted: {repo}")
        return repo

    async def verify(self) -> ToolResult:
        data = await request_json("GET", "https://api.github.com/user", headers=self._headers())
        login = data.get("login", "unknown") if isinstance(data, dict) else "unknown"
        return ToolResult("EXECUTED", f"GitHub credentials verified as {login}.", {"login": login})

    async def recent_commits(self, repo: str) -> ToolResult:
        name = self._repo(repo)
        data = await request_json(
            "GET",
            f"https://api.github.com/repos/{name}/commits",
            headers=self._headers(),
            params={"per_page": "5"},
        )
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = list(data.get("items") or [])
        else:
            rows = []
        commits: list[dict] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            commits.append(
                {
                    "sha": str(item.get("sha", ""))[:7],
                    "message": str(commit.get("message", "")).split("\n", 1)[0],
                    "author": author.get("name"),
                    "committed_at": author.get("date"),
                    "files": [],
                }
            )
        return ToolResult("EXECUTED", f"Fetched {len(commits)} commits from {name}.", {"commits": commits})

    async def create_issue(self, repo: str, title: str, body: str, idempotency_key: str) -> ToolResult:
        name = self._repo(repo)
        data = await request_json(
            "POST",
            f"https://api.github.com/repos/{name}/issues",
            headers={**self._headers(), "X-Idempotency-Key": idempotency_key},
            json={"title": title, "body": body},
        )
        payload = data if isinstance(data, dict) else {}
        return ToolResult(
            "EXECUTED",
            f"Opened GitHub issue {payload.get('html_url', '')}.",
            {
                "provider": "github",
                "repository": name,
                "external_issue_id": str(payload.get("number")),
                "external_url": payload.get("html_url"),
            },
        )

    async def pull_requests(self, repo: str) -> ToolResult:
        name = self._repo(repo)
        data = await request_json(
            "GET",
            f"https://api.github.com/repos/{name}/pulls",
            headers=self._headers(),
            params={"state": "open", "per_page": "5"},
        )
        rows = data if isinstance(data, list) else []
        pulls = [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "url": item.get("html_url"),
            }
            for item in rows
            if isinstance(item, dict)
        ]
        return ToolResult("EXECUTED", f"Fetched {len(pulls)} pull requests from {name}.", {"pull_requests": pulls})

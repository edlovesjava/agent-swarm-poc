"""GitHub API client - Checks, comments, labels, PRs."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import jwt
import structlog

from src.orchestrator.config import Settings

logger = structlog.get_logger()


class CheckStatus(str, Enum):
    """Check run status."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class CheckConclusion(str, Enum):
    """Check run conclusion."""
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"


class GitHubClient:
    """GitHub API client using App authentication."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._installation_tokens: dict[str, tuple[str, datetime]] = {}
    
    def _generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication."""
        now = datetime.now(timezone.utc)
        payload = {
            "iat": int(now.timestamp()) - 60,  # 1 minute ago
            "exp": int(now.timestamp()) + 600,  # 10 minutes from now
            "iss": self.settings.github_app_id,
        }
        return jwt.encode(
            payload,
            self.settings.github_app_private_key,
            algorithm="RS256",
        )
    
    async def _get_installation_token(self, repo: str) -> str:
        """Get installation access token for a repository."""
        # Check cache
        if repo in self._installation_tokens:
            token, expires = self._installation_tokens[repo]
            if datetime.now(timezone.utc) < expires:
                return token
        
        # Get installation ID
        async with httpx.AsyncClient() as client:
            jwt_token = self._generate_jwt()
            
            # Get installation for repo
            owner, name = repo.split("/")
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{name}/installation",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            installation_id = resp.json()["id"]
            
            # Get access token
            resp = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            
            token = data["token"]
            expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            
            self._installation_tokens[repo] = (token, expires)
            return token
    
    async def _request(
        self,
        method: str,
        repo: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make authenticated request to GitHub API."""
        token = await self._get_installation_token(repo)
        
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method,
                f"https://api.github.com/repos/{repo}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}
    
    # === Check Runs ===
    
    async def create_check_run(
        self,
        repo: str,
        head_sha: str,
        name: str,
        status: CheckStatus = CheckStatus.QUEUED,
        details_url: str | None = None,
        output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new check run."""
        data: dict[str, Any] = {
            "name": name,
            "head_sha": head_sha,
            "status": status.value,
        }
        
        if details_url:
            data["details_url"] = details_url
        
        if output:
            data["output"] = output
        
        result = await self._request("POST", repo, "/check-runs", json=data)
        logger.info("Created check run", repo=repo, name=name, id=result.get("id"))
        return result
    
    async def update_check_run(
        self,
        repo: str,
        check_run_id: int,
        status: CheckStatus | None = None,
        conclusion: CheckConclusion | None = None,
        output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing check run."""
        data: dict[str, Any] = {}
        
        if status:
            data["status"] = status.value
        
        if conclusion:
            data["conclusion"] = conclusion.value
            data["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        if output:
            data["output"] = output
        
        result = await self._request(
            "PATCH",
            repo,
            f"/check-runs/{check_run_id}",
            json=data,
        )
        logger.info("Updated check run", repo=repo, id=check_run_id)
        return result
    
    # === Comments ===
    
    async def create_issue_comment(
        self,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        """Create a comment on an issue or PR."""
        result = await self._request(
            "POST",
            repo,
            f"/issues/{issue_number}/comments",
            json={"body": body},
        )
        logger.info("Created comment", repo=repo, issue=issue_number)
        return result
    
    async def create_pr_review(
        self,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",  # APPROVE, REQUEST_CHANGES, COMMENT
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a PR review with optional inline comments."""
        data: dict[str, Any] = {
            "body": body,
            "event": event,
        }
        
        if comments:
            data["comments"] = comments
        
        result = await self._request(
            "POST",
            repo,
            f"/pulls/{pr_number}/reviews",
            json=data,
        )
        logger.info("Created PR review", repo=repo, pr=pr_number)
        return result
    
    # === Labels ===
    
    async def add_labels(
        self,
        repo: str,
        issue_number: int,
        labels: list[str],
    ) -> list[dict[str, Any]]:
        """Add labels to an issue or PR."""
        result = await self._request(
            "POST",
            repo,
            f"/issues/{issue_number}/labels",
            json={"labels": labels},
        )
        logger.info("Added labels", repo=repo, issue=issue_number, labels=labels)
        return result
    
    async def remove_label(
        self,
        repo: str,
        issue_number: int,
        label: str,
    ) -> None:
        """Remove a label from an issue or PR."""
        try:
            await self._request(
                "DELETE",
                repo,
                f"/issues/{issue_number}/labels/{label}",
            )
            logger.info("Removed label", repo=repo, issue=issue_number, label=label)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
    
    async def set_agent_label(
        self,
        repo: str,
        issue_number: int,
        state_label: str,
    ) -> None:
        """Set agent state label, removing other agent labels."""
        # Get current labels
        result = await self._request("GET", repo, f"/issues/{issue_number}/labels")
        current = [label["name"] for label in result]
        
        # Remove old agent labels
        agent_labels = [l for l in current if l.startswith("agent:")]
        for label in agent_labels:
            if label != state_label:
                await self.remove_label(repo, issue_number, label)
        
        # Add new label if not present
        if state_label not in current:
            await self.add_labels(repo, issue_number, [state_label])
    
    # === Pull Requests ===
    
    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> dict[str, Any]:
        """Create a pull request."""
        result = await self._request(
            "POST",
            repo,
            "/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        logger.info("Created PR", repo=repo, number=result.get("number"))
        return result
    
    async def get_pr_files(
        self,
        repo: str,
        pr_number: int,
    ) -> list[dict[str, Any]]:
        """Get files changed in a PR."""
        result = await self._request("GET", repo, f"/pulls/{pr_number}/files")
        return result
    
    # === Branches ===
    
    async def get_default_branch(self, repo: str) -> str:
        """Get the default branch of a repository."""
        result = await self._request("GET", repo, "")
        return result.get("default_branch", "main")
    
    async def get_branch_sha(self, repo: str, branch: str) -> str:
        """Get the SHA of a branch."""
        result = await self._request("GET", repo, f"/git/ref/heads/{branch}")
        return result["object"]["sha"]

"""Main orchestrator service - webhook handler and API."""

import hashlib
import hmac
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .config import Settings
from .state_machine import TaskStateMachine, TaskState
from .task_router import TaskRouter

logger = structlog.get_logger()
settings = Settings()


class WebhookPayload(BaseModel):
    """GitHub webhook payload."""
    action: str
    repository: dict[str, Any]
    sender: dict[str, Any]
    issue: dict[str, Any] | None = None
    pull_request: dict[str, Any] | None = None
    comment: dict[str, Any] | None = None
    check_run: dict[str, Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    logger.info("Starting agent swarm orchestrator")
    
    # Initialize components
    app.state.task_router = TaskRouter(settings)
    app.state.state_machine = TaskStateMachine(settings)
    
    yield
    
    logger.info("Shutting down orchestrator")


app = FastAPI(
    title="Agent Swarm Orchestrator",
    description="Autonomous agent coordination for GitHub",
    version="0.1.0",
    lifespan=lifespan,
)


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature.startswith("sha256="):
        return False
    
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected}", signature)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "agent-swarm-orchestrator"}


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str = Header(...),
):
    """Handle GitHub webhook events."""
    
    # Verify signature
    body = await request.body()
    if not verify_webhook_signature(body, x_hub_signature_256, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = await request.json()
    
    logger.info(
        "Received webhook",
        event=x_github_event,
        action=payload.get("action"),
        repo=payload.get("repository", {}).get("full_name"),
    )
    
    # Route to appropriate handler
    router: TaskRouter = request.app.state.task_router
    
    match x_github_event:
        case "issues":
            await router.handle_issue_event(payload)
        case "issue_comment":
            await router.handle_comment_event(payload)
        case "pull_request":
            await router.handle_pr_event(payload)
        case "check_run":
            await router.handle_check_run_event(payload)
        case _:
            logger.debug("Ignoring event", event=x_github_event)
    
    return {"status": "processed"}


@app.get("/tasks")
async def list_tasks(request: Request):
    """List all active tasks."""
    state_machine: TaskStateMachine = request.app.state.state_machine
    tasks = await state_machine.list_active_tasks()
    return {"tasks": tasks}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    """Get task details."""
    state_machine: TaskStateMachine = request.app.state.state_machine
    task = await state_machine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def cli():
    """CLI entry point."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    cli()

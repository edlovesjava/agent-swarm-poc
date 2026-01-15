"""Task state machine - tracks lifecycle of agent tasks."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as redis
import structlog
from pydantic import BaseModel

from .config import Settings

logger = structlog.get_logger()


class TaskState(str, Enum):
    """Task lifecycle states."""
    QUEUED = "queued"
    PLANNING = "planning"
    PLAN_REVIEW = "plan_review"
    APPROVED = "approved"
    EXECUTING = "executing"
    PR_OPEN = "pr_open"
    PR_AGENT_REVIEW = "pr_agent_review"
    PR_AGENT_FIX = "pr_agent_fix"
    FAILED = "failed"
    FIXER_REVIEW = "fixer_review"
    HUMAN_ESCALATION = "human_escalation"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    # Product Manager states
    PM_VISION = "pm_vision"
    PM_VISION_REVIEW = "pm_vision_review"
    PM_BACKLOG = "pm_backlog"
    PM_FEATURE_REVIEW = "pm_feature_review"
    PM_HANDOFF_PLANNER = "pm_handoff_planner"


class Decision(BaseModel):
    """Record of a human decision."""
    timestamp: datetime
    type: str  # plan_feedback, plan_approval, pr_review_delegation, etc.
    human: str  # GitHub username
    action: str
    comment: str | None = None
    metadata: dict[str, Any] = {}


class Task(BaseModel):
    """Agent task - tracks an issue through its lifecycle."""
    id: str
    repo: str
    issue_number: int
    issue_title: str
    state: TaskState
    branch: str | None = None
    pr_number: int | None = None
    
    # Timeline
    created_at: datetime
    updated_at: datetime
    first_plan_at: datetime | None = None
    approved_at: datetime | None = None
    pr_opened_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Plans (version history)
    plan_versions: list[dict[str, Any]] = []
    current_plan_version: int = 0
    
    # Decision log
    decisions: list[Decision] = []
    
    # Agent tracking
    agent_ids: list[str] = []
    current_agent_id: str | None = None
    
    # Cost tracking
    token_usage: dict[str, int] = {}  # model -> tokens
    estimated_cost_usd: float = 0.0
    
    # File coordination
    locked_files: list[str] = []
    
    # Error tracking
    last_error: str | None = None
    retry_count: int = 0


# Valid state transitions
TRANSITIONS: dict[TaskState, list[TaskState]] = {
    TaskState.QUEUED: [TaskState.PLANNING, TaskState.PM_VISION],
    TaskState.PLANNING: [TaskState.PLAN_REVIEW],
    TaskState.PLAN_REVIEW: [TaskState.APPROVED, TaskState.PLANNING],  # approve or revise
    TaskState.APPROVED: [TaskState.EXECUTING],
    TaskState.EXECUTING: [TaskState.PR_OPEN, TaskState.FAILED],
    TaskState.PR_OPEN: [
        TaskState.PR_AGENT_REVIEW,
        TaskState.PR_AGENT_FIX,
        TaskState.COMPLETED,
        TaskState.ARCHIVED,
    ],
    TaskState.PR_AGENT_REVIEW: [TaskState.PR_OPEN],
    TaskState.PR_AGENT_FIX: [TaskState.PR_OPEN],
    TaskState.FAILED: [TaskState.FIXER_REVIEW],
    TaskState.FIXER_REVIEW: [TaskState.EXECUTING, TaskState.HUMAN_ESCALATION],
    TaskState.HUMAN_ESCALATION: [TaskState.QUEUED, TaskState.ARCHIVED],  # retry or abandon
    TaskState.COMPLETED: [],  # terminal
    TaskState.ARCHIVED: [],  # terminal
    # Product Manager transitions
    TaskState.PM_VISION: [TaskState.PM_VISION_REVIEW],
    TaskState.PM_VISION_REVIEW: [TaskState.PM_VISION, TaskState.PM_BACKLOG],  # revise or proceed
    TaskState.PM_BACKLOG: [TaskState.PM_FEATURE_REVIEW, TaskState.PM_VISION],
    TaskState.PM_FEATURE_REVIEW: [TaskState.PM_BACKLOG, TaskState.PM_HANDOFF_PLANNER],
    TaskState.PM_HANDOFF_PLANNER: [TaskState.PLANNING],  # connects to existing flow
}


class TaskStateMachine:
    """Manages task state transitions and persistence."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis: redis.Redis | None = None
    
    async def _get_redis(self) -> redis.Redis:
        """Lazy Redis connection."""
        if self.redis is None:
            self.redis = redis.from_url(self.settings.redis_url)
        return self.redis
    
    def _task_key(self, task_id: str) -> str:
        return f"task:{task_id}"
    
    async def create_task(
        self,
        repo: str,
        issue_number: int,
        issue_title: str,
    ) -> Task:
        """Create a new task in QUEUED state."""
        task_id = f"issue-{issue_number}"
        now = datetime.now(timezone.utc)
        
        task = Task(
            id=task_id,
            repo=repo,
            issue_number=issue_number,
            issue_title=issue_title,
            state=TaskState.QUEUED,
            created_at=now,
            updated_at=now,
        )
        
        r = await self._get_redis()
        await r.set(self._task_key(task_id), task.model_dump_json())
        await r.sadd("tasks:active", task_id)
        
        logger.info("Created task", task_id=task_id, issue=issue_number)
        return task
    
    async def get_task(self, task_id: str) -> Task | None:
        """Get task by ID."""
        r = await self._get_redis()
        data = await r.get(self._task_key(task_id))
        if not data:
            return None
        return Task.model_validate_json(data)
    
    async def transition(
        self,
        task_id: str,
        new_state: TaskState,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Transition task to new state."""
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Validate transition
        valid_next = TRANSITIONS.get(task.state, [])
        if new_state not in valid_next:
            raise ValueError(
                f"Invalid transition: {task.state} -> {new_state}. "
                f"Valid: {valid_next}"
            )
        
        old_state = task.state
        task.state = new_state
        task.updated_at = datetime.now(timezone.utc)
        
        # Update timeline fields
        if new_state == TaskState.PLAN_REVIEW and task.first_plan_at is None:
            task.first_plan_at = task.updated_at
        elif new_state == TaskState.APPROVED:
            task.approved_at = task.updated_at
        elif new_state == TaskState.PR_OPEN and task.pr_opened_at is None:
            task.pr_opened_at = task.updated_at
        elif new_state in (TaskState.COMPLETED, TaskState.ARCHIVED):
            task.completed_at = task.updated_at
        
        # Apply metadata
        if metadata:
            if "plan" in metadata:
                task.plan_versions.append(metadata["plan"])
                task.current_plan_version = len(task.plan_versions)
            if "pr_number" in metadata:
                task.pr_number = metadata["pr_number"]
            if "branch" in metadata:
                task.branch = metadata["branch"]
            if "error" in metadata:
                task.last_error = metadata["error"]
                task.retry_count += 1
        
        # Persist
        r = await self._get_redis()
        await r.set(self._task_key(task_id), task.model_dump_json())
        
        # Move to archives if terminal
        if new_state in (TaskState.COMPLETED, TaskState.ARCHIVED):
            await r.srem("tasks:active", task_id)
            await r.sadd("tasks:archived", task_id)
        
        logger.info(
            "Task transition",
            task_id=task_id,
            from_state=old_state,
            to_state=new_state,
        )
        
        return task
    
    async def record_decision(
        self,
        task_id: str,
        decision_type: str,
        human: str,
        action: str,
        comment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Record a human decision on a task."""
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        decision = Decision(
            timestamp=datetime.now(timezone.utc),
            type=decision_type,
            human=human,
            action=action,
            comment=comment,
            metadata=metadata or {},
        )
        
        task.decisions.append(decision)
        task.updated_at = datetime.now(timezone.utc)
        
        r = await self._get_redis()
        await r.set(self._task_key(task_id), task.model_dump_json())
        
        logger.info(
            "Recorded decision",
            task_id=task_id,
            type=decision_type,
            human=human,
            action=action,
        )
        
        return task
    
    async def list_active_tasks(self) -> list[Task]:
        """List all active (non-archived) tasks."""
        r = await self._get_redis()
        task_ids = await r.smembers("tasks:active")
        
        tasks = []
        for task_id in task_ids:
            task = await self.get_task(task_id.decode() if isinstance(task_id, bytes) else task_id)
            if task:
                tasks.append(task)
        
        return sorted(tasks, key=lambda t: t.updated_at, reverse=True)
    
    async def get_task_for_issue(self, repo: str, issue_number: int) -> Task | None:
        """Get task by issue number."""
        return await self.get_task(f"issue-{issue_number}")

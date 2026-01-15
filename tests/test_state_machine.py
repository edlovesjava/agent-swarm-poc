"""Tests for state machine."""

import os
import pytest
from datetime import datetime, timezone

# Set test environment variables before imports that might trigger Settings
os.environ.setdefault("GITHUB_APP_ID", "test")
os.environ.setdefault("GITHUB_APP_PRIVATE_KEY", "test")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from src.orchestrator.state_machine import (
    Decision,
    Task,
    TaskState,
    TaskStateMachine,
    TRANSITIONS,
)


class TestTaskState:
    """Test task state transitions."""
    
    def test_valid_transitions_from_queued(self):
        """QUEUED can transition to PLANNING or PM_VISION."""
        valid = TRANSITIONS[TaskState.QUEUED]
        assert TaskState.PLANNING in valid
        assert TaskState.PM_VISION in valid
    
    def test_valid_transitions_from_plan_review(self):
        """PLAN_REVIEW can go to APPROVED or back to PLANNING."""
        valid = TRANSITIONS[TaskState.PLAN_REVIEW]
        assert TaskState.APPROVED in valid
        assert TaskState.PLANNING in valid
    
    def test_terminal_states(self):
        """COMPLETED and ARCHIVED are terminal states."""
        assert TRANSITIONS[TaskState.COMPLETED] == []
        assert TRANSITIONS[TaskState.ARCHIVED] == []


class TestTask:
    """Test Task model."""
    
    def test_task_creation(self):
        """Task can be created with required fields."""
        now = datetime.now(timezone.utc)
        task = Task(
            id="issue-42",
            repo="owner/repo",
            issue_number=42,
            issue_title="Fix bug",
            state=TaskState.QUEUED,
            created_at=now,
            updated_at=now,
        )
        
        assert task.id == "issue-42"
        assert task.state == TaskState.QUEUED
        assert task.decisions == []
        assert task.plan_versions == []
    
    def test_decision_recording(self):
        """Decisions can be added to task."""
        now = datetime.now(timezone.utc)
        task = Task(
            id="issue-42",
            repo="owner/repo",
            issue_number=42,
            issue_title="Fix bug",
            state=TaskState.PLAN_REVIEW,
            created_at=now,
            updated_at=now,
        )
        
        decision = Decision(
            timestamp=now,
            type="plan_approval",
            human="testuser",
            action="approved",
        )
        
        task.decisions.append(decision)
        
        assert len(task.decisions) == 1
        assert task.decisions[0].human == "testuser"


class TestTaskStateMachine:
    """Test state machine operations."""
    
    @pytest.fixture
    def settings(self):
        """Create test settings."""
        from src.orchestrator.config import Settings
        
        # Use test/mock values
        return Settings(
            github_app_id="test",
            github_app_private_key="test",
            github_webhook_secret="test",
            anthropic_api_key="test",
            redis_url="redis://localhost:6379",
        )
    
    @pytest.mark.asyncio
    async def test_create_task(self, settings):
        """State machine can create tasks."""
        # This test requires Redis - skip in CI without Redis
        pytest.skip("Requires Redis connection")
        
        sm = TaskStateMachine(settings)
        task = await sm.create_task(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test issue",
        )
        
        assert task.id == "issue-42"
        assert task.state == TaskState.QUEUED

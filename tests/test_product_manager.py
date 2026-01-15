"""Tests for ProductManagerAgent."""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment variables before imports that might trigger Settings
os.environ.setdefault("GITHUB_APP_ID", "test")
os.environ.setdefault("GITHUB_APP_PRIVATE_KEY", "test")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from src.agents.product_manager import ProductManagerAgent
from src.agents.base import AgentResult
from src.orchestrator.state_machine import Task, TaskState, TRANSITIONS


class TestProductManagerAgent:
    """Test ProductManagerAgent functionality."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        from src.orchestrator.config import Settings

        return Settings(
            github_app_id="test",
            github_app_private_key="test",
            github_webhook_secret="test",
            anthropic_api_key="test",
            redis_url="redis://localhost:6379",
            model_haiku="claude-haiku-4-5-20251001",
            model_sonnet="claude-sonnet-4-5-20250929",
            model_opus="claude-opus-4-5-20251101",
        )

    @pytest.fixture
    def pm_agent(self, settings):
        """Create PM agent instance."""
        return ProductManagerAgent(settings)

    @pytest.fixture
    def sample_task(self):
        """Create sample task for testing."""
        now = datetime.now(timezone.utc)
        return Task(
            id="issue-42",
            repo="owner/repo",
            issue_number=42,
            issue_title="Define product vision",
            state=TaskState.PM_VISION,
            created_at=now,
            updated_at=now,
        )

    def test_agent_type(self, pm_agent):
        """PM agent has correct type."""
        assert pm_agent.agent_type == "product_manager"

    @pytest.mark.asyncio
    async def test_define_vision_without_input_asks_questions(self, pm_agent, sample_task):
        """When no user input, PM agent asks clarifying questions."""
        context = {}  # No user_input

        result = await pm_agent.execute(sample_task, context)

        assert result.success
        assert "comment_body" in result.output
        assert "questions" in result.output
        assert result.output["action"] == "questions_posted"
        assert len(result.output["questions"]) > 0

    @pytest.mark.asyncio
    async def test_define_vision_with_input_generates_vision(self, pm_agent, sample_task):
        """With user input, PM agent generates vision document."""
        context = {
            "user_input": """
            Problem: Developers spend too much time on repetitive tasks.
            Users: Software developers at mid-size companies.
            Success: 50% reduction in time spent on boilerplate code.
            """
        }

        # Mock the LLM response
        with patch.object(pm_agent, "_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = """{
                "problem_statement": "Developers spend too much time on repetitive tasks",
                "target_users": "Software developers at mid-size companies",
                "vision_statement": "Automate away repetitive development work",
                "goals": ["Reduce boilerplate by 50%", "Improve developer satisfaction"],
                "metrics": [{"metric": "Time saved", "target": "50%", "current": "N/A", "status": "Not Started"}],
                "in_scope": ["Code generation", "Template management"],
                "out_of_scope": ["Full IDE replacement"],
                "constraints": ["Must integrate with existing tools"],
                "assumptions": ["Developers use Git"]
            }"""

            result = await pm_agent.execute(sample_task, context)

            assert result.success
            assert "vision_md" in result.output
            assert "vision_data" in result.output
            assert result.output["action"] == "vision_draft_ready"
            assert "# Product Vision" in result.output["vision_md"]

    @pytest.mark.asyncio
    async def test_manage_backlog_generates_features(self, pm_agent, sample_task):
        """PM agent generates backlog from vision."""
        context = {
            "action": "manage_backlog",
            "vision_data": {
                "problem_statement": "Manual code reviews are slow",
                "target_users": "Engineering teams",
                "goals": ["Faster reviews", "Consistent feedback"],
            },
        }

        with patch.object(pm_agent, "_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = """{
                "features": [
                    {
                        "id": "feature-1",
                        "name": "Automated code analysis",
                        "priority": "P0",
                        "status": "Ready",
                        "description": "Analyze code for common issues",
                        "user_story": {
                            "user_type": "developer",
                            "capability": "get automated code feedback",
                            "benefit": "faster reviews"
                        },
                        "acceptance_criteria": ["Detects common bugs", "Provides suggestions"],
                        "dependencies": [],
                        "effort": "L",
                        "notes": ""
                    }
                ],
                "summary": {"total": 1, "ready": 1, "in_progress": 0, "done": 0}
            }"""

            result = await pm_agent.execute(sample_task, context)

            assert result.success
            assert "backlog_md" in result.output
            assert "backlog_data" in result.output
            assert result.output["feature_count"] == 1
            assert result.output["action"] == "backlog_updated"

    @pytest.mark.asyncio
    async def test_add_feature_creates_new_feature(self, pm_agent, sample_task):
        """PM agent can add a feature to backlog."""
        context = {
            "action": "add_feature",
            "feature_description": "Add dark mode support for better accessibility",
            "existing_backlog_data": {
                "features": [
                    {"id": "feature-1", "name": "Existing feature"}
                ]
            },
        }

        with patch.object(pm_agent, "_complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = """{
                "name": "Dark mode support",
                "priority": "P2",
                "status": "Ready",
                "description": "Add dark mode for accessibility",
                "user_story": {
                    "user_type": "user",
                    "capability": "switch to dark mode",
                    "benefit": "reduce eye strain"
                },
                "acceptance_criteria": ["Toggle in settings", "Persists across sessions"],
                "dependencies": [],
                "effort": "M",
                "notes": ""
            }"""

            result = await pm_agent.execute(sample_task, context)

            assert result.success
            assert "feature" in result.output
            assert result.output["feature"]["id"] == "feature-2"  # Incremented from existing
            assert result.output["action"] == "feature_added"

    @pytest.mark.asyncio
    async def test_create_feature_issue(self, pm_agent, sample_task):
        """PM agent creates GitHub issue from feature."""
        context = {
            "action": "create_feature",
            "feature": {
                "id": "feature-1",
                "name": "User authentication",
                "priority": "P0",
                "description": "Implement user login and registration",
                "user_story": {
                    "user_type": "user",
                    "capability": "log in to my account",
                    "benefit": "access personalized features",
                },
                "acceptance_criteria": [
                    "Email/password login",
                    "Password reset flow",
                ],
                "dependencies": [],
                "effort": "L",
                "notes": "Consider OAuth later",
            },
        }

        result = await pm_agent.execute(sample_task, context)

        assert result.success
        assert "issue_title" in result.output
        assert result.output["issue_title"] == "User authentication"
        assert "issue_body" in result.output
        assert "labels" in result.output
        assert "feature" in result.output["labels"]
        assert "priority:p0" in result.output["labels"]
        assert result.output["action"] == "issue_ready"

    @pytest.mark.asyncio
    async def test_handoff_to_planner(self, pm_agent, sample_task):
        """PM agent prepares handoff to planner."""
        context = {
            "action": "handoff_to_planner",
            "feature": {
                "id": "feature-1",
                "name": "API endpoints",
                "description": "Create REST API endpoints",
                "user_story": {"user_type": "developer", "capability": "call API", "benefit": "integrate"},
                "acceptance_criteria": ["GET endpoint", "POST endpoint"],
                "effort": "M",
            },
            "issue_number": 42,
        }

        result = await pm_agent.execute(sample_task, context)

        assert result.success
        assert "planner_context" in result.output
        assert "handoff_comment" in result.output
        assert result.output["planner_context"]["from_pm"] is True
        assert result.output["action"] == "handoff_ready"

    @pytest.mark.asyncio
    async def test_unknown_action_fails(self, pm_agent, sample_task):
        """Unknown action returns failure."""
        context = {"action": "unknown_action"}

        result = await pm_agent.execute(sample_task, context)

        assert not result.success
        assert "Unknown PM action" in result.error

    def test_parse_json_response_valid(self, pm_agent):
        """JSON parsing works for valid JSON."""
        response = '{"key": "value", "number": 42}'
        result = pm_agent._parse_json_response(response)

        assert result == {"key": "value", "number": 42}

    def test_parse_json_response_markdown_block(self, pm_agent):
        """JSON parsing extracts from markdown code block."""
        response = """Here's the result:
```json
{"key": "value"}
```
"""
        result = pm_agent._parse_json_response(response)

        assert result == {"key": "value"}

    def test_parse_json_response_embedded(self, pm_agent):
        """JSON parsing finds embedded JSON."""
        response = 'Some text {"key": "value"} more text'
        result = pm_agent._parse_json_response(response)

        assert result == {"key": "value"}

    def test_parse_json_response_invalid(self, pm_agent):
        """Invalid JSON returns None."""
        response = "This is not JSON at all"
        result = pm_agent._parse_json_response(response)

        assert result is None


class TestPMStateTransitions:
    """Test PM-related state transitions."""

    def test_queued_can_transition_to_pm_vision(self):
        """QUEUED state can transition to PM_VISION."""
        valid = TRANSITIONS[TaskState.QUEUED]
        assert TaskState.PM_VISION in valid

    def test_pm_vision_transitions_to_review(self):
        """PM_VISION can only transition to PM_VISION_REVIEW."""
        valid = TRANSITIONS[TaskState.PM_VISION]
        assert TaskState.PM_VISION_REVIEW in valid

    def test_pm_vision_review_transitions(self):
        """PM_VISION_REVIEW can revise or proceed to backlog."""
        valid = TRANSITIONS[TaskState.PM_VISION_REVIEW]
        assert TaskState.PM_VISION in valid  # revise
        assert TaskState.PM_BACKLOG in valid  # proceed

    def test_pm_backlog_transitions(self):
        """PM_BACKLOG can go to feature review or back to vision."""
        valid = TRANSITIONS[TaskState.PM_BACKLOG]
        assert TaskState.PM_FEATURE_REVIEW in valid
        assert TaskState.PM_VISION in valid

    def test_pm_feature_review_transitions(self):
        """PM_FEATURE_REVIEW can go back to backlog or handoff."""
        valid = TRANSITIONS[TaskState.PM_FEATURE_REVIEW]
        assert TaskState.PM_BACKLOG in valid
        assert TaskState.PM_HANDOFF_PLANNER in valid

    def test_pm_handoff_connects_to_planning(self):
        """PM_HANDOFF_PLANNER transitions to PLANNING."""
        valid = TRANSITIONS[TaskState.PM_HANDOFF_PLANNER]
        assert TaskState.PLANNING in valid


class TestVisionMdGeneration:
    """Test VISION.md generation."""

    @pytest.fixture
    def pm_agent(self):
        """Create PM agent with minimal settings."""
        from src.orchestrator.config import Settings

        settings = Settings(
            github_app_id="test",
            github_app_private_key="test",
            github_webhook_secret="test",
            anthropic_api_key="test",
        )
        return ProductManagerAgent(settings)

    def test_generate_vision_md_complete(self, pm_agent):
        """Vision MD generation includes all sections."""
        vision_data = {
            "problem_statement": "Test problem",
            "target_users": "Test users",
            "vision_statement": "Test vision",
            "goals": ["Goal 1", "Goal 2"],
            "metrics": [{"metric": "M1", "target": "100", "current": "50", "status": "On Track"}],
            "in_scope": ["Feature A"],
            "out_of_scope": ["Feature B"],
            "constraints": ["Constraint 1"],
            "assumptions": ["Assumption 1"],
        }

        result = pm_agent._generate_vision_md(vision_data)

        assert "# Product Vision" in result
        assert "Test problem" in result
        assert "Test users" in result
        assert "Goal 1" in result
        assert "Goal 2" in result
        assert "Feature A" in result
        assert "Feature B" in result
        assert "Constraint 1" in result
        assert "Assumption 1" in result
        assert "Last updated:" in result

    def test_generate_vision_md_empty_fields(self, pm_agent):
        """Vision MD handles empty/missing fields gracefully."""
        vision_data = {
            "problem_statement": "Test problem",
        }

        result = pm_agent._generate_vision_md(vision_data)

        assert "# Product Vision" in result
        assert "Test problem" in result
        assert "To be defined" in result  # Default for missing fields


class TestBacklogMdGeneration:
    """Test BACKLOG.md generation."""

    @pytest.fixture
    def pm_agent(self):
        """Create PM agent with minimal settings."""
        from src.orchestrator.config import Settings

        settings = Settings(
            github_app_id="test",
            github_app_private_key="test",
            github_webhook_secret="test",
            anthropic_api_key="test",
        )
        return ProductManagerAgent(settings)

    def test_generate_backlog_md(self, pm_agent):
        """Backlog MD generation includes features by priority."""
        backlog_data = {
            "features": [
                {
                    "id": "feature-1",
                    "name": "Critical feature",
                    "priority": "P0",
                    "status": "Ready",
                    "description": "Important",
                    "user_story": {"user_type": "user", "capability": "do X", "benefit": "Y"},
                    "acceptance_criteria": ["Criterion 1"],
                    "dependencies": [],
                    "effort": "M",
                    "notes": "",
                },
                {
                    "id": "feature-2",
                    "name": "Nice to have",
                    "priority": "P2",
                    "status": "Ready",
                    "description": "Optional",
                    "user_story": {"user_type": "user", "capability": "do A", "benefit": "B"},
                    "acceptance_criteria": [],
                    "dependencies": ["feature-1"],
                    "effort": "S",
                    "notes": "Consider later",
                },
            ],
            "summary": {"total": 2, "ready": 2, "in_progress": 0, "done": 0},
        }

        result = pm_agent._generate_backlog_md(backlog_data)

        assert "# Product Backlog" in result
        assert "P0 - Critical" in result
        assert "P2 - Medium" in result
        assert "Critical feature" in result
        assert "Nice to have" in result
        assert "Total features: 2" in result

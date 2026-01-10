"""Task router - handles GitHub events and routes to appropriate actions."""

import re
from typing import Any

import structlog

from .config import Settings
from .state_machine import TaskStateMachine, TaskState

logger = structlog.get_logger()

# Command patterns
COMMAND_PATTERN = re.compile(r"^/(approve|agent-review|agent-fix|agent-plan|approve-plan|agent-stop)\b(.*)$", re.MULTILINE)

# Labels that indicate agent should work on issue
AGENT_LABELS = {"agent-ok", "good-first-issue"}


class TaskRouter:
    """Routes GitHub events to task actions."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state_machine = TaskStateMachine(settings)
    
    async def handle_issue_event(self, payload: dict[str, Any]) -> None:
        """Handle issue opened/labeled events."""
        action = payload.get("action")
        issue = payload.get("issue", {})
        repo = payload.get("repository", {}).get("full_name")
        issue_number = issue.get("number")
        
        if action not in ("opened", "labeled"):
            return
        
        # Check if issue has agent label
        labels = {label.get("name") for label in issue.get("labels", [])}
        if not labels & AGENT_LABELS:
            logger.debug("Issue missing agent label", issue=issue_number, labels=labels)
            return
        
        # Check if task already exists
        existing = await self.state_machine.get_task_for_issue(repo, issue_number)
        if existing:
            logger.debug("Task already exists", issue=issue_number, state=existing.state)
            return
        
        # Create new task
        task = await self.state_machine.create_task(
            repo=repo,
            issue_number=issue_number,
            issue_title=issue.get("title", ""),
        )
        
        logger.info("Created task from issue", task_id=task.id, issue=issue_number)
        
        # TODO: Trigger planning agent
        # await self.trigger_planning(task)
    
    async def handle_comment_event(self, payload: dict[str, Any]) -> None:
        """Handle issue/PR comments for commands."""
        action = payload.get("action")
        if action != "created":
            return
        
        comment = payload.get("comment", {})
        body = comment.get("body", "")
        author = comment.get("user", {}).get("login")
        
        # Check for commands
        commands = COMMAND_PATTERN.findall(body)
        if not commands:
            return
        
        # Determine context (issue or PR)
        issue = payload.get("issue", {})
        repo = payload.get("repository", {}).get("full_name")
        issue_number = issue.get("number")
        is_pr = "pull_request" in issue
        
        task = await self.state_machine.get_task_for_issue(repo, issue_number)
        
        for command, args in commands:
            args = args.strip()
            
            logger.info(
                "Processing command",
                command=command,
                args=args,
                author=author,
                issue=issue_number,
            )
            
            match command:
                case "approve":
                    await self._handle_approve(task, author, args)
                case "agent-review":
                    await self._handle_agent_review(task, author, args)
                case "agent-fix":
                    await self._handle_agent_fix(task, author, args)
                case "agent-plan":
                    await self._handle_agent_plan(task, repo, issue_number, author)
                case "approve-plan":
                    await self._handle_approve_plan(task, author)
                case "agent-stop":
                    await self._handle_agent_stop(task, author)
    
    async def _handle_approve(
        self,
        task: Any | None,
        author: str,
        args: str,
    ) -> None:
        """Handle /approve command."""
        if not task:
            logger.warning("No task found for approve command")
            return
        
        if task.state != TaskState.PLAN_REVIEW:
            logger.warning(
                "Cannot approve - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return
        
        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="plan_approval",
            human=author,
            action="approved",
            comment=args if args else None,
            metadata={"plan_version": task.current_plan_version},
        )
        
        # Transition to approved
        await self.state_machine.transition(task.id, TaskState.APPROVED)
        
        # TODO: Trigger execution
        # await self.trigger_execution(task)
        
        logger.info("Plan approved", task_id=task.id, author=author)
    
    async def _handle_agent_review(
        self,
        task: Any | None,
        author: str,
        args: str,
    ) -> None:
        """Handle /agent-review command."""
        if not task:
            logger.warning("No task found for agent-review command")
            return
        
        if task.state != TaskState.PR_OPEN:
            logger.warning(
                "Cannot request review - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return
        
        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="pr_review_delegation",
            human=author,
            action="agent_review_requested",
            comment=args if args else None,
        )
        
        # Transition to review state
        await self.state_machine.transition(task.id, TaskState.PR_AGENT_REVIEW)
        
        # TODO: Trigger review agent
        # await self.trigger_review(task, args)
        
        logger.info("Agent review requested", task_id=task.id, author=author)
    
    async def _handle_agent_fix(
        self,
        task: Any | None,
        author: str,
        args: str,
    ) -> None:
        """Handle /agent-fix command."""
        if not task:
            logger.warning("No task found for agent-fix command")
            return
        
        if task.state != TaskState.PR_OPEN:
            logger.warning(
                "Cannot request fix - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return
        
        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="pr_fix_delegation",
            human=author,
            action="agent_fix_requested",
            comment=args if args else None,
        )
        
        # Transition to fix state
        await self.state_machine.transition(task.id, TaskState.PR_AGENT_FIX)
        
        # TODO: Trigger fix agent
        # await self.trigger_fix(task, args)
        
        logger.info("Agent fix requested", task_id=task.id, author=author)
    
    async def _handle_agent_plan(
        self,
        task: Any | None,
        repo: str,
        issue_number: int,
        author: str,
    ) -> None:
        """Handle /agent-plan command (Planner agent)."""
        # Can be called even without existing task
        if not task:
            task = await self.state_machine.create_task(
                repo=repo,
                issue_number=issue_number,
                issue_title="",  # Will be filled by planner
            )
        
        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="planner_requested",
            human=author,
            action="planner_invoked",
        )
        
        # TODO: Trigger planner agent
        # await self.trigger_planner(task)
        
        logger.info("Planner agent requested", task_id=task.id, author=author)
    
    async def _handle_approve_plan(
        self,
        task: Any | None,
        author: str,
    ) -> None:
        """Handle /approve-plan command (for Planner output)."""
        if not task:
            logger.warning("No task found for approve-plan command")
            return
        
        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="planner_approval",
            human=author,
            action="plan_approved",
        )
        
        # TODO: Create sub-issues from plan
        # await self.create_sub_issues(task)
        
        logger.info("Planner output approved", task_id=task.id, author=author)
    
    async def _handle_agent_stop(
        self,
        task: Any | None,
        author: str,
    ) -> None:
        """Handle /agent-stop command."""
        if not task:
            logger.warning("No task found for agent-stop command")
            return
        
        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="agent_stop",
            human=author,
            action="stopped",
        )
        
        # TODO: Signal agent to stop
        # await self.stop_agent(task)
        
        logger.info("Agent stop requested", task_id=task.id, author=author)
    
    async def handle_pr_event(self, payload: dict[str, Any]) -> None:
        """Handle PR events (merged, closed)."""
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {}).get("full_name")
        
        # Extract issue number from branch name (agent/42-...)
        branch = pr.get("head", {}).get("ref", "")
        if not branch.startswith("agent/"):
            return
        
        # Parse issue number from branch
        parts = branch.replace("agent/", "").split("-")
        if not parts or not parts[0].isdigit():
            return
        
        issue_number = int(parts[0])
        task = await self.state_machine.get_task_for_issue(repo, issue_number)
        
        if not task:
            return
        
        if action == "closed":
            if pr.get("merged"):
                await self.state_machine.transition(task.id, TaskState.COMPLETED)
                logger.info("Task completed via merge", task_id=task.id)
            else:
                await self.state_machine.transition(task.id, TaskState.ARCHIVED)
                logger.info("Task archived (PR closed)", task_id=task.id)
    
    async def handle_check_run_event(self, payload: dict[str, Any]) -> None:
        """Handle check run events (for CI monitoring)."""
        # TODO: Implement CI agent integration
        pass

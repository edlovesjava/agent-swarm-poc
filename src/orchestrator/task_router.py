"""Task router - handles GitHub events and routes to appropriate actions."""

import re
from typing import Any

import structlog

from .config import Settings
from .state_machine import Task, TaskStateMachine, TaskState

# Lazy imports to avoid circular dependency
# WorkerAgent and GitHubClient imported inside methods

logger = structlog.get_logger()

# Command patterns
COMMAND_PATTERN = re.compile(
    r"^/(approve|agent-review|agent-fix|agent-plan|approve-plan|agent-stop"
    r"|agent-pm|approve-vision|refine-feature|approve-feature"
    r"|add-feature|prioritize|handoff)\b(.*)$",
    re.MULTILINE
)

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

        # Trigger planning agent
        await self._trigger_planning(task, issue)
    
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
                # Product Manager commands
                case "agent-pm":
                    await self._handle_agent_pm(task, repo, issue_number, author, args)
                case "approve-vision":
                    await self._handle_approve_vision(task, author)
                case "refine-feature":
                    await self._handle_refine_feature(task, author, args)
                case "approve-feature":
                    await self._handle_approve_feature(task, author)
                case "add-feature":
                    await self._handle_add_feature(task, author, args)
                case "prioritize":
                    await self._handle_prioritize(task, author, args)
                case "handoff":
                    await self._handle_handoff(task, author, args)
    
    # === Core Agent Orchestration Methods ===

    async def _trigger_planning(self, task: Task, issue: dict[str, Any]) -> None:
        """Transition to PLANNING and invoke worker agent."""
        # Lazy imports to avoid circular dependency
        from src.agents.worker import WorkerAgent
        from src.github_app.client import GitHubClient

        await self.state_machine.transition(task.id, TaskState.PLANNING)

        # Update label
        github = GitHubClient(self.settings)
        await github.set_agent_label(task.repo, task.issue_number, "agent:planning")

        # Get worker agent
        worker = WorkerAgent(self.settings)
        result = await worker.execute(task, {
            "action": "plan",
            "issue_body": issue.get("body", ""),
            "issue_title": issue.get("title", task.issue_title),
        })

        if result.success:
            # Post plan as comment
            await self._post_plan(task, result.output["plan"])

            # Transition to PLAN_REVIEW
            await self.state_machine.transition(
                task.id,
                TaskState.PLAN_REVIEW,
                metadata={"plan": result.output}
            )

            # Update label
            await github.set_agent_label(task.repo, task.issue_number, "agent:awaiting-plan")
        else:
            logger.error("Planning failed", task_id=task.id, error=result.error)

    async def _post_plan(self, task: Task, plan: str) -> None:
        """Post plan to GitHub issue."""
        from src.github_app.client import GitHubClient

        github = GitHubClient(self.settings)

        body = f"""## 🤖 Agent Plan for #{task.issue_number}

{plan}

---
Reply `/approve` to proceed, or provide feedback for revision.
"""

        await github.create_issue_comment(
            repo=task.repo,
            issue_number=task.issue_number,
            body=body,
        )

        logger.info("Posted plan to issue", task_id=task.id)

    async def _trigger_execution(self, task: Task) -> None:
        """Execute approved plan."""
        from src.agents.worker import WorkerAgent
        from src.github_app.client import GitHubClient

        await self.state_machine.transition(task.id, TaskState.EXECUTING)

        # Update label
        github = GitHubClient(self.settings)
        await github.set_agent_label(task.repo, task.issue_number, "agent:executing")

        # Get latest plan
        task = await self.state_machine.get_task(task.id)
        plan = task.plan_versions[-1] if task.plan_versions else {}

        # Execute
        worker = WorkerAgent(self.settings)
        result = await worker.execute(task, {
            "action": "implement",
            "plan": plan.get("plan", ""),
        })

        if result.success:
            await self._create_pr(task, result, github)
        else:
            # Transition to FAILED
            await self.state_machine.transition(
                task.id,
                TaskState.FAILED,
                metadata={"error": result.error}
            )
            await github.set_agent_label(task.repo, task.issue_number, "agent:failed")
            logger.error("Execution failed", task_id=task.id, error=result.error)

    async def _create_pr(self, task: Task, result: Any, github: Any) -> None:
        """Create PR from agent work."""
        branch = result.output.get("branch", f"agent/{task.issue_number}")
        files = result.output.get("files_changed", [])

        # Get latest plan for PR body
        plan = task.plan_versions[-1] if task.plan_versions else {}

        files_list = "\n".join(f"- `{f}`" for f in files) if files else "- (mock implementation)"

        body = f"""## Resolves #{task.issue_number}

### Summary
{plan.get('plan', 'Implementation complete.')}

### Files Changed
{files_list}

---
*Generated by Agent Swarm*
"""

        try:
            pr = await github.create_pull_request(
                repo=task.repo,
                title=f"[Agent] {task.issue_title}",
                body=body,
                head=branch,
            )

            # Update task state
            await self.state_machine.transition(
                task.id,
                TaskState.PR_OPEN,
                metadata={"pr_number": pr["number"], "branch": branch}
            )

            # Update label
            await github.set_agent_label(task.repo, task.issue_number, "agent:pr-open")

            logger.info("Created PR", task_id=task.id, pr=pr["number"])
        except Exception as e:
            # For PoC with mock implementation, PR creation may fail (no actual branch)
            # Log and continue - task stays in EXECUTING state
            logger.warning(
                "PR creation failed (expected for mock)",
                task_id=task.id,
                error=str(e),
            )
            # Post comment instead
            await github.create_issue_comment(
                repo=task.repo,
                issue_number=task.issue_number,
                body=f"""## 🤖 Agent Execution Complete (Mock)

The agent has completed mock execution for this issue.

**Files that would be changed:**
{files_list}

**Branch:** `{branch}`

*Note: This is a PoC mock implementation. Real PR creation requires actual code changes.*
""",
            )

    # === Command Handlers ===

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

        logger.info("Plan approved", task_id=task.id, author=author)

        # Trigger execution
        await self._trigger_execution(task)
    
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

    # Product Manager command handlers

    async def _handle_agent_pm(
        self,
        task: Any | None,
        repo: str,
        issue_number: int,
        author: str,
        args: str,
    ) -> None:
        """Handle /agent-pm command - invoke PM agent.

        Args can specify mode:
        - /agent-pm vision - Start/continue vision definition
        - /agent-pm backlog - Manage backlog
        - /agent-pm feature <name> - Create/refine specific feature
        """
        # Create task if needed
        if not task:
            task = await self.state_machine.create_task(
                repo=repo,
                issue_number=issue_number,
                issue_title="",  # Will be filled by PM agent
            )

        # Parse mode from args
        mode = "vision"  # default
        if args:
            parts = args.strip().split(maxsplit=1)
            if parts:
                mode = parts[0].lower()

        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="pm_invoked",
            human=author,
            action=f"pm_{mode}_requested",
            metadata={"mode": mode, "args": args},
        )

        # Transition to PM_VISION state
        if task.state == TaskState.QUEUED:
            await self.state_machine.transition(task.id, TaskState.PM_VISION)

        # TODO: Trigger PM agent
        # await self.trigger_pm_agent(task, mode, args)

        logger.info("PM agent requested", task_id=task.id, author=author, mode=mode)

    async def _handle_approve_vision(
        self,
        task: Any | None,
        author: str,
    ) -> None:
        """Handle /approve-vision - approve vision and proceed to backlog."""
        if not task:
            logger.warning("No task found for approve-vision command")
            return

        if task.state != TaskState.PM_VISION_REVIEW:
            logger.warning(
                "Cannot approve vision - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return

        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="vision_approval",
            human=author,
            action="approved",
        )

        # Transition to backlog management
        await self.state_machine.transition(task.id, TaskState.PM_BACKLOG)

        logger.info("Vision approved", task_id=task.id, author=author)

    async def _handle_refine_feature(
        self,
        task: Any | None,
        author: str,
        args: str,
    ) -> None:
        """Handle /refine-feature <feedback> - request feature refinement."""
        if not task:
            logger.warning("No task found for refine-feature command")
            return

        if task.state != TaskState.PM_FEATURE_REVIEW:
            logger.warning(
                "Cannot refine feature - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return

        # Record decision with feedback
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="feature_feedback",
            human=author,
            action="refinement_requested",
            comment=args if args else None,
        )

        # Stay in PM_FEATURE_REVIEW or go back to PM_BACKLOG
        # For now, stay in review and let PM agent process feedback

        logger.info("Feature refinement requested", task_id=task.id, author=author)

    async def _handle_approve_feature(
        self,
        task: Any | None,
        author: str,
    ) -> None:
        """Handle /approve-feature - approve feature for planning."""
        if not task:
            logger.warning("No task found for approve-feature command")
            return

        if task.state != TaskState.PM_FEATURE_REVIEW:
            logger.warning(
                "Cannot approve feature - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return

        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="feature_approval",
            human=author,
            action="approved",
        )

        # Stay in PM_FEATURE_REVIEW - handoff command will trigger transition

        logger.info("Feature approved", task_id=task.id, author=author)

    async def _handle_add_feature(
        self,
        task: Any | None,
        author: str,
        args: str,
    ) -> None:
        """Handle /add-feature <description> - add feature to backlog."""
        if not task:
            logger.warning("No task found for add-feature command")
            return

        if task.state not in (TaskState.PM_BACKLOG, TaskState.PM_FEATURE_REVIEW):
            logger.warning(
                "Cannot add feature - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return

        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="feature_added",
            human=author,
            action="add_feature",
            comment=args if args else None,
        )

        # TODO: Trigger PM agent to add feature
        # await self.trigger_pm_add_feature(task, args)

        logger.info("Feature add requested", task_id=task.id, author=author)

    async def _handle_prioritize(
        self,
        task: Any | None,
        author: str,
        args: str,
    ) -> None:
        """Handle /prioritize <feature> <priority> - adjust backlog priority."""
        if not task:
            logger.warning("No task found for prioritize command")
            return

        if task.state not in (TaskState.PM_BACKLOG, TaskState.PM_FEATURE_REVIEW):
            logger.warning(
                "Cannot prioritize - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return

        # Parse feature and priority from args
        parts = args.strip().split() if args else []
        feature_id = parts[0] if len(parts) > 0 else None
        priority = parts[1] if len(parts) > 1 else None

        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="prioritization",
            human=author,
            action="prioritize",
            metadata={"feature_id": feature_id, "priority": priority},
        )

        # TODO: Trigger PM agent to reprioritize
        # await self.trigger_pm_prioritize(task, feature_id, priority)

        logger.info(
            "Prioritization requested",
            task_id=task.id,
            author=author,
            feature=feature_id,
            priority=priority,
        )

    async def _handle_handoff(
        self,
        task: Any | None,
        author: str,
        args: str,
    ) -> None:
        """Handle /handoff <feature> - hand off feature to PlannerAgent."""
        if not task:
            logger.warning("No task found for handoff command")
            return

        if task.state != TaskState.PM_FEATURE_REVIEW:
            logger.warning(
                "Cannot handoff - wrong state",
                task_id=task.id,
                state=task.state,
            )
            return

        # Parse feature ID from args
        feature_id = args.strip() if args else None

        # Record decision
        await self.state_machine.record_decision(
            task_id=task.id,
            decision_type="pm_handoff",
            human=author,
            action="handoff_to_planner",
            metadata={"feature_id": feature_id},
        )

        # Transition to handoff state, then to planning
        await self.state_machine.transition(task.id, TaskState.PM_HANDOFF_PLANNER)
        await self.state_machine.transition(task.id, TaskState.PLANNING)

        # TODO: Trigger Planner agent with PM context
        # await self.trigger_planner_with_pm_context(task, feature_id)

        logger.info(
            "Feature handed off to Planner",
            task_id=task.id,
            author=author,
            feature=feature_id,
        )

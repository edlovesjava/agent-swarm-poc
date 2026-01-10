"""Worker agent - handles issue to PR flow."""

from typing import Any

import structlog

from src.orchestrator.config import Settings
from src.orchestrator.state_machine import Task

from .base import AgentResult, BaseAgent

logger = structlog.get_logger()


class WorkerAgent(BaseAgent):
    """Worker agent that implements issues and creates PRs."""
    
    @property
    def agent_type(self) -> str:
        return "worker"
    
    async def execute(self, task: Task, context: dict[str, Any]) -> AgentResult:
        """Execute worker task based on current state."""
        action = context.get("action", "plan")
        
        match action:
            case "plan":
                return await self._generate_plan(task, context)
            case "implement":
                return await self._implement(task, context)
            case _:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                )
    
    async def _generate_plan(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Generate implementation plan for the issue."""
        issue_body = context.get("issue_body", "")
        issue_title = task.issue_title
        repo_context = context.get("repo_context", "")
        feedback = context.get("feedback")  # Previous feedback if revising
        
        system = """You are a senior software engineer planning an implementation.
Create a clear, actionable plan that another engineer (or AI agent) can follow.
Be specific about files to modify and the approach."""
        
        prompt = f"""Create an implementation plan for this GitHub issue.

Issue: {issue_title}

Description:
{issue_body}

Repository context:
{repo_context}
"""
        
        if feedback:
            prompt += f"""
Previous plan feedback (incorporate this):
{feedback}
"""
        
        prompt += """
Respond in this exact format:

## Summary
[One sentence describing the fix]

## Approach
[Numbered steps for implementation]

## Files to modify
[List files with brief description of changes]

## Estimated scope
[Lines of code, complexity assessment]

## Risks or considerations
[Any edge cases or things to watch for]"""
        
        # Determine model based on complexity
        complexity = await self.estimate_complexity(issue_body)
        model = self._select_model("planning", complexity)
        
        response = await self._complete(prompt, model=model, system=system)
        
        return AgentResult(
            success=True,
            output={
                "plan": response,
                "complexity": complexity,
                "model_used": model,
            },
            tokens_used=self.tokens_used.copy(),
        )
    
    async def _implement(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Implement the approved plan."""
        plan = context.get("plan", "")
        workdir = context.get("workdir", "")
        
        # TODO: Integrate with OpenHands runtime for actual implementation
        # This is a placeholder for the implementation logic
        
        logger.info(
            "Implementation requested",
            task_id=task.id,
            workdir=workdir,
        )
        
        # For now, return a placeholder
        return AgentResult(
            success=True,
            output={
                "status": "implementation_pending",
                "message": "OpenHands integration not yet implemented",
            },
            tokens_used=self.tokens_used.copy(),
        )


class ReviewerAgent(BaseAgent):
    """Agent that reviews PRs on request."""
    
    @property
    def agent_type(self) -> str:
        return "reviewer"
    
    async def execute(self, task: Task, context: dict[str, Any]) -> AgentResult:
        """Review PR code."""
        diff = context.get("diff", "")
        focus_areas = context.get("focus_areas", "")
        
        system = """You are a senior code reviewer.
Provide constructive, specific feedback.
Focus on correctness, maintainability, and potential bugs.
Be concise but thorough."""
        
        prompt = f"""Review this pull request.

Focus areas requested by human:
{focus_areas if focus_areas else "General review"}

Diff:
```diff
{diff}
```

Provide your review in this format:

## Summary
[Overall assessment]

## Specific Comments
[For each issue, specify the file, line range, and suggestion]

## Questions
[Any clarifying questions for the author]"""
        
        response = await self._complete(prompt, system=system)
        
        return AgentResult(
            success=True,
            output={
                "review": response,
            },
            tokens_used=self.tokens_used.copy(),
        )


class FixerAgent(BaseAgent):
    """Agent that addresses PR review feedback."""
    
    @property
    def agent_type(self) -> str:
        return "fixer"
    
    async def execute(self, task: Task, context: dict[str, Any]) -> AgentResult:
        """Address review comments."""
        review_comments = context.get("review_comments", "")
        current_code = context.get("current_code", "")
        
        system = """You are a developer addressing code review feedback.
Make minimal, targeted changes to address each comment.
If a comment requires clarification or is a design decision, note it rather than guessing."""
        
        prompt = f"""Address these review comments.

Review comments:
{review_comments}

Current code context:
{current_code}

For each comment, respond with:
1. Whether you can address it (yes/no/needs_human)
2. The specific change you'll make (if yes)
3. Why it needs human input (if needs_human)"""
        
        response = await self._complete(prompt, system=system)
        
        # Parse response to determine what was addressed
        can_address = "needs_human" not in response.lower()
        
        return AgentResult(
            success=can_address,
            output={
                "analysis": response,
                "fully_addressed": can_address,
            },
            tokens_used=self.tokens_used.copy(),
        )

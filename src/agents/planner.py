"""Planner agent - PM role for dependency analysis and work breakdown."""

from typing import Any

import structlog

from src.orchestrator.config import Settings
from src.orchestrator.state_machine import Task

from .base import AgentResult, BaseAgent

logger = structlog.get_logger()


class PlannerAgent(BaseAgent):
    """Planner agent for architectural analysis and dependency mapping."""
    
    @property
    def agent_type(self) -> str:
        return "planner"
    
    async def execute(self, task: Task, context: dict[str, Any]) -> AgentResult:
        """Generate comprehensive plan with dependency analysis."""
        issue_body = context.get("issue_body", "")
        issue_title = task.issue_title
        repo_structure = context.get("repo_structure", "")
        related_issues = context.get("related_issues", [])
        
        system = """You are a technical project manager and architect.
Analyze complex features and break them into well-defined, implementable tasks.
Identify dependencies, risks, and optimal execution order.
Be thorough but practical."""
        
        prompt = f"""Analyze this feature request and create a comprehensive implementation plan.

Feature: {issue_title}

Description:
{issue_body}

Repository structure:
{repo_structure}

Related open issues:
{self._format_related_issues(related_issues)}

Create a detailed breakdown including:

## Executive Summary
[2-3 sentences describing the feature and approach]

## Sub-tasks
[Break into discrete, implementable issues. Each should be completable independently once dependencies are met]

For each sub-task:
- Title (suitable for GitHub issue)
- Description
- Acceptance criteria
- Estimated complexity (trivial/standard/complex)
- Dependencies (other sub-tasks that must complete first)

## Dependency Graph
[Mermaid diagram showing task dependencies]

## Execution Order
[Recommended order with parallelization opportunities]

## Risk Assessment
[Identify high-risk components and mitigation strategies]

## Effort Estimation
[Table with complexity, estimated time, and cost per sub-task]

## Recommendations
[Any architectural decisions that need human input before proceeding]"""
        
        # Use Opus for complex planning tasks
        response = await self._complete(
            prompt,
            model=self.settings.model_opus,
            system=system,
            max_tokens=8192,
        )
        
        # Parse sub-tasks from response
        sub_tasks = self._parse_subtasks(response)
        
        return AgentResult(
            success=True,
            output={
                "plan": response,
                "sub_tasks": sub_tasks,
                "model_used": self.settings.model_opus,
            },
            tokens_used=self.tokens_used.copy(),
        )
    
    def _format_related_issues(self, issues: list[dict[str, Any]]) -> str:
        """Format related issues for context."""
        if not issues:
            return "None found"
        
        lines = []
        for issue in issues[:10]:  # Limit to 10
            lines.append(f"- #{issue.get('number')}: {issue.get('title')}")
        
        return "\n".join(lines)
    
    def _parse_subtasks(self, response: str) -> list[dict[str, Any]]:
        """Parse sub-tasks from planner response."""
        # Simple parsing - in production would be more robust
        sub_tasks = []
        
        # Look for sub-task sections
        in_subtasks = False
        current_task: dict[str, Any] = {}
        
        for line in response.split("\n"):
            line = line.strip()
            
            if "## Sub-tasks" in line or "## Subtasks" in line:
                in_subtasks = True
                continue
            
            if in_subtasks and line.startswith("## "):
                # End of sub-tasks section
                if current_task:
                    sub_tasks.append(current_task)
                break
            
            if in_subtasks:
                if line.startswith("### ") or line.startswith("- **"):
                    # New sub-task
                    if current_task:
                        sub_tasks.append(current_task)
                    
                    title = line.replace("### ", "").replace("- **", "").replace("**", "").strip()
                    current_task = {"title": title, "description": "", "dependencies": []}
                
                elif current_task:
                    # Add to current task description
                    if "Dependencies:" in line or "Depends on:" in line:
                        deps = line.split(":", 1)[1].strip()
                        current_task["dependencies"] = [d.strip() for d in deps.split(",")]
                    elif "Complexity:" in line:
                        current_task["complexity"] = line.split(":", 1)[1].strip().lower()
                    else:
                        current_task["description"] += line + "\n"
        
        # Don't forget the last task
        if current_task:
            sub_tasks.append(current_task)
        
        return sub_tasks
    
    async def create_sub_issues(
        self,
        parent_task: Task,
        sub_tasks: list[dict[str, Any]],
        github_client: Any,
    ) -> list[dict[str, Any]]:
        """Create GitHub issues for each sub-task."""
        created_issues = []
        
        for sub_task in sub_tasks:
            body = f"""## Parent Issue
This is part of #{parent_task.issue_number}

## Description
{sub_task.get('description', '')}

## Dependencies
{', '.join(f"#{d}" for d in sub_task.get('dependencies', [])) or 'None'}

---
*Created by Planner Agent*
"""
            
            issue = await github_client.create_issue(
                repo=parent_task.repo,
                title=sub_task.get("title", "Sub-task"),
                body=body,
                labels=["agent-ok", f"complexity:{sub_task.get('complexity', 'standard')}"],
            )
            
            created_issues.append({
                "number": issue.get("number"),
                "title": sub_task.get("title"),
                "url": issue.get("html_url"),
            })
            
            logger.info(
                "Created sub-issue",
                parent=parent_task.issue_number,
                sub_issue=issue.get("number"),
            )
        
        return created_issues

"""Product Manager agent - vision, roadmap, and backlog management."""

from typing import Any

import structlog

from src.orchestrator.config import Settings
from src.orchestrator.state_machine import Task

from .base import AgentResult, BaseAgent

logger = structlog.get_logger()


# Artifact templates
VISION_TEMPLATE = """# Product Vision

## Problem Statement
{problem_statement}

## Target Users
{target_users}

## Vision Statement
{vision_statement}

## Goals
{goals}

## Success Metrics
| Metric | Target | Current | Status |
|--------|--------|---------|--------|
{metrics_table}

## Scope

### In Scope
{in_scope}

### Out of Scope
{out_of_scope}

## Constraints
{constraints}

## Assumptions
{assumptions}

---
*Last updated: {updated_at} by PM Agent*
*Version: {version}*
"""

BACKLOG_TEMPLATE = """# Product Backlog

## Overview
Total features: {total} | Ready: {ready} | In Progress: {in_progress} | Done: {done}

## Priority Legend
- **P0 (Critical)**: Must have for MVP
- **P1 (High)**: Important for initial release
- **P2 (Medium)**: Nice to have
- **P3 (Low)**: Future consideration

---

{features_by_priority}

---

## Completed Features
| Feature | Issue | PR | Completed |
|---------|-------|-----|-----------|
{completed_table}

---
*Last updated: {updated_at} by PM Agent*
"""

FEATURE_TEMPLATE = """### {name} {{#{feature_id}}}
- **Status**: {status}
- **Issue**: {issue_link}
- **Description**: {description}
- **User Story**: As a {user_type}, I want {capability} so that {benefit}
- **Acceptance Criteria**:
{acceptance_criteria}
- **Dependencies**: {dependencies}
- **Estimated Effort**: {effort}
- **Notes**: {notes}
"""


class ProductManagerAgent(BaseAgent):
    """Product Manager agent for vision, roadmap, and backlog management.

    Responsibilities:
    - Define and refine product vision (VISION.md)
    - Manage product backlog (BACKLOG.md)
    - Create GitHub issues for approved features
    - Hand off features to PlannerAgent for technical breakdown
    - Facilitate iterative refinement with stakeholders
    """

    @property
    def agent_type(self) -> str:
        return "product_manager"

    async def execute(self, task: Task, context: dict[str, Any]) -> AgentResult:
        """Execute PM task based on action type."""
        action = context.get("action", "define_vision")

        match action:
            case "define_vision":
                return await self._define_vision(task, context)
            case "refine_vision":
                return await self._refine_vision(task, context)
            case "manage_backlog":
                return await self._manage_backlog(task, context)
            case "create_feature":
                return await self._create_feature(task, context)
            case "prioritize":
                return await self._prioritize_backlog(task, context)
            case "add_feature":
                return await self._add_feature(task, context)
            case "handoff_to_planner":
                return await self._handoff_to_planner(task, context)
            case _:
                return AgentResult(
                    success=False,
                    error=f"Unknown PM action: {action}",
                )

    async def _define_vision(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Generate initial product vision through user dialogue.

        If no user input provided, generates clarifying questions.
        If user input provided, generates VISION.md draft.
        """
        user_input = context.get("user_input")
        existing_vision = context.get("existing_vision")

        if not user_input:
            # Generate clarifying questions
            return await self._ask_clarifying_questions(task, context, "vision")

        # Generate vision from user input
        system = """You are a product manager helping define product vision.
Create clear, measurable goals and articulate the value proposition.
Be concise but comprehensive."""

        prompt = f"""Based on this input, create a product vision document.

User's Input:
{user_input}

{"Existing Vision (for context):" + chr(10) + existing_vision if existing_vision else ""}

Generate a complete vision document with these sections:
1. Problem Statement - What problem are we solving?
2. Target Users - Who are the primary users?
3. Vision Statement - One sentence describing the ideal future state
4. Goals - 3-5 measurable goals
5. Success Metrics - How we'll measure each goal (provide table format)
6. Scope - What's in and out of scope
7. Constraints - Technical, business, timeline constraints
8. Assumptions - Key assumptions we're making

Format your response as JSON with these keys:
{{
    "problem_statement": "...",
    "target_users": "...",
    "vision_statement": "...",
    "goals": ["goal 1", "goal 2", ...],
    "metrics": [{{"metric": "...", "target": "...", "current": "N/A", "status": "Not Started"}}],
    "in_scope": ["item 1", "item 2", ...],
    "out_of_scope": ["item 1", "item 2", ...],
    "constraints": ["constraint 1", ...],
    "assumptions": ["assumption 1", ...]
}}"""

        response = await self._complete(
            prompt,
            model=self.settings.model_sonnet,
            system=system,
            max_tokens=4096,
        )

        # Parse JSON response
        vision_data = self._parse_json_response(response)
        if not vision_data:
            return AgentResult(
                success=False,
                error="Failed to parse vision response",
                output={"raw_response": response},
            )

        # Generate VISION.md content
        vision_md = self._generate_vision_md(vision_data)

        return AgentResult(
            success=True,
            output={
                "vision_md": vision_md,
                "vision_data": vision_data,
                "model_used": self.settings.model_sonnet,
                "action": "vision_draft_ready",
            },
            tokens_used=self.tokens_used.copy(),
        )

    async def _refine_vision(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Refine existing vision based on user feedback."""
        existing_vision = context.get("existing_vision", "")
        feedback = context.get("feedback", "")

        if not existing_vision:
            return AgentResult(
                success=False,
                error="No existing vision to refine",
            )

        system = """You are a product manager refining product vision.
Incorporate feedback while maintaining consistency and clarity.
Preserve what's working and improve what needs changes."""

        prompt = f"""Refine this product vision based on the feedback provided.

Current Vision:
{existing_vision}

Feedback:
{feedback}

Generate the updated vision as JSON with the same structure:
{{
    "problem_statement": "...",
    "target_users": "...",
    "vision_statement": "...",
    "goals": [...],
    "metrics": [...],
    "in_scope": [...],
    "out_of_scope": [...],
    "constraints": [...],
    "assumptions": [...],
    "changes_made": ["change 1", "change 2", ...]
}}"""

        response = await self._complete(
            prompt,
            model=self.settings.model_sonnet,
            system=system,
            max_tokens=4096,
        )

        vision_data = self._parse_json_response(response)
        if not vision_data:
            return AgentResult(
                success=False,
                error="Failed to parse refined vision response",
            )

        vision_md = self._generate_vision_md(vision_data)

        return AgentResult(
            success=True,
            output={
                "vision_md": vision_md,
                "vision_data": vision_data,
                "changes_made": vision_data.get("changes_made", []),
                "action": "vision_refined",
            },
            tokens_used=self.tokens_used.copy(),
        )

    async def _ask_clarifying_questions(
        self,
        task: Task,
        context: dict[str, Any],
        question_type: str,
    ) -> AgentResult:
        """Generate contextual clarifying questions."""

        questions_by_type = {
            "vision": [
                "What problem are you trying to solve with this product?",
                "Who are your target users? Describe them briefly.",
                "What does success look like? (measurable outcomes)",
                "What constraints should I be aware of? (technical, budget, timeline)",
                "Is there anything explicitly out of scope for now?",
            ],
            "feature": [
                "What is the main use case for this feature?",
                "Who will use this feature most?",
                "What should happen when the feature is used? (happy path)",
                "What edge cases or error scenarios should we handle?",
                "Are there any constraints or dependencies?",
            ],
            "priority": [
                "What's the business value of this feature? (revenue, retention, efficiency)",
                "How urgent is this? Are there external deadlines?",
                "What are the dependencies? Does anything block this?",
                "What's the risk if we delay this feature?",
            ],
        }

        questions = questions_by_type.get(question_type, questions_by_type["vision"])

        # Format questions for GitHub comment
        formatted_questions = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))

        comment_body = f"""## Product Manager Agent - {question_type.title()} Discovery

I'd like to understand your product better. Please answer these questions:

{formatted_questions}

Reply with your answers and I'll draft the {question_type} document."""

        return AgentResult(
            success=True,
            output={
                "comment_body": comment_body,
                "questions": questions,
                "question_type": question_type,
                "action": "questions_posted",
            },
            tokens_used=self.tokens_used.copy(),
        )

    async def _manage_backlog(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Update backlog with features based on vision."""
        vision_data = context.get("vision_data", {})
        existing_backlog = context.get("existing_backlog")
        user_input = context.get("user_input")

        system = """You are a product manager managing a product backlog.
Create well-defined features aligned with the product vision.
Prioritize based on value, dependencies, and risk."""

        prompt = f"""Based on the product vision, create or update the product backlog.

Vision Summary:
- Problem: {vision_data.get('problem_statement', 'Not defined')}
- Target Users: {vision_data.get('target_users', 'Not defined')}
- Goals: {', '.join(vision_data.get('goals', ['Not defined']))}

{"Existing Backlog:" + chr(10) + existing_backlog if existing_backlog else "No existing backlog."}

{"User Input:" + chr(10) + user_input if user_input else ""}

Generate a backlog as JSON:
{{
    "features": [
        {{
            "id": "feature-1",
            "name": "Feature Name",
            "priority": "P0",
            "status": "Ready",
            "description": "Brief description",
            "user_story": {{
                "user_type": "developer",
                "capability": "what they want",
                "benefit": "why they want it"
            }},
            "acceptance_criteria": ["criterion 1", "criterion 2"],
            "dependencies": [],
            "effort": "M",
            "notes": ""
        }}
    ],
    "summary": {{
        "total": 0,
        "ready": 0,
        "in_progress": 0,
        "done": 0
    }}
}}

Prioritize features as:
- P0: Must have for MVP
- P1: Important for initial release
- P2: Nice to have
- P3: Future consideration

Effort estimates: S (small), M (medium), L (large), XL (extra large)"""

        response = await self._complete(
            prompt,
            model=self.settings.model_sonnet,
            system=system,
            max_tokens=8192,
        )

        backlog_data = self._parse_json_response(response)
        if not backlog_data:
            return AgentResult(
                success=False,
                error="Failed to parse backlog response",
                output={"raw_response": response},
            )

        backlog_md = self._generate_backlog_md(backlog_data)

        return AgentResult(
            success=True,
            output={
                "backlog_md": backlog_md,
                "backlog_data": backlog_data,
                "feature_count": len(backlog_data.get("features", [])),
                "action": "backlog_updated",
            },
            tokens_used=self.tokens_used.copy(),
        )

    async def _add_feature(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Add a new feature to the backlog."""
        feature_description = context.get("feature_description", "")
        existing_backlog = context.get("existing_backlog_data", {"features": []})
        vision_data = context.get("vision_data", {})

        system = """You are a product manager adding features to a backlog.
Ensure features are well-defined, aligned with vision, and properly prioritized."""

        prompt = f"""Add this feature to the backlog.

Feature Description:
{feature_description}

Vision Context:
- Goals: {', '.join(vision_data.get('goals', ['Not defined']))}

Existing Features: {len(existing_backlog.get('features', []))}

Generate the new feature as JSON:
{{
    "id": "feature-N",
    "name": "Feature Name",
    "priority": "P1",
    "status": "Ready",
    "description": "...",
    "user_story": {{
        "user_type": "...",
        "capability": "...",
        "benefit": "..."
    }},
    "acceptance_criteria": ["..."],
    "dependencies": [],
    "effort": "M",
    "notes": ""
}}"""

        response = await self._complete(
            prompt,
            model=self.settings.model_haiku,
            system=system,
            max_tokens=2048,
        )

        feature_data = self._parse_json_response(response)
        if not feature_data:
            return AgentResult(
                success=False,
                error="Failed to parse feature response",
            )

        # Assign unique ID
        existing_ids = [f.get("id", "") for f in existing_backlog.get("features", [])]
        max_num = 0
        for fid in existing_ids:
            if fid.startswith("feature-"):
                try:
                    num = int(fid.replace("feature-", ""))
                    max_num = max(max_num, num)
                except ValueError:
                    pass
        feature_data["id"] = f"feature-{max_num + 1}"

        return AgentResult(
            success=True,
            output={
                "feature": feature_data,
                "action": "feature_added",
            },
            tokens_used=self.tokens_used.copy(),
        )

    async def _prioritize_backlog(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Re-prioritize backlog based on user input."""
        backlog_data = context.get("backlog_data", {"features": []})
        prioritization_input = context.get("prioritization_input", "")

        system = """You are a product manager prioritizing a backlog.
Consider business value, dependencies, risk, and effort.
Provide clear rationale for prioritization changes."""

        prompt = f"""Re-prioritize this backlog based on the input.

Current Backlog:
{self._format_features_for_prompt(backlog_data.get('features', []))}

Prioritization Input:
{prioritization_input}

Return the updated features list as JSON with new priorities and a rationale:
{{
    "features": [...updated features with new priorities...],
    "rationale": ["reason for change 1", "reason for change 2"]
}}"""

        response = await self._complete(
            prompt,
            model=self.settings.model_sonnet,
            system=system,
            max_tokens=4096,
        )

        result = self._parse_json_response(response)
        if not result:
            return AgentResult(
                success=False,
                error="Failed to parse prioritization response",
            )

        return AgentResult(
            success=True,
            output={
                "features": result.get("features", []),
                "rationale": result.get("rationale", []),
                "action": "backlog_prioritized",
            },
            tokens_used=self.tokens_used.copy(),
        )

    async def _create_feature(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Create GitHub issue for a backlog feature."""
        feature = context.get("feature", {})

        if not feature:
            return AgentResult(
                success=False,
                error="No feature provided to create issue for",
            )

        # Generate issue body
        user_story = feature.get("user_story", {})
        acceptance_criteria = feature.get("acceptance_criteria", [])

        issue_body = f"""## Feature: {feature.get('name', 'Unnamed')}

**From Backlog**: #{feature.get('id', 'unknown')}
**Priority**: {feature.get('priority', 'P1')}

### User Story
As a {user_story.get('user_type', 'user')}, I want {user_story.get('capability', '...')} so that {user_story.get('benefit', '...')}.

### Description
{feature.get('description', 'No description provided.')}

### Acceptance Criteria
{chr(10).join(f'- [ ] {c}' for c in acceptance_criteria)}

### Dependencies
{', '.join(f'#{d}' for d in feature.get('dependencies', [])) or 'None'}

### Effort Estimate
{feature.get('effort', 'M')}

### Notes
{feature.get('notes', 'None')}

---
*Created by PM Agent from BACKLOG.md*
"""

        labels = [
            "feature",
            "agent-ok",
            f"priority:{feature.get('priority', 'P1').lower()}",
        ]

        return AgentResult(
            success=True,
            output={
                "issue_title": feature.get("name", "Unnamed Feature"),
                "issue_body": issue_body,
                "labels": labels,
                "feature_id": feature.get("id"),
                "action": "issue_ready",
            },
            tokens_used=self.tokens_used.copy(),
        )

    async def _handoff_to_planner(
        self,
        task: Task,
        context: dict[str, Any],
    ) -> AgentResult:
        """Hand off approved feature to PlannerAgent for technical breakdown."""
        feature = context.get("feature", {})
        issue_number = context.get("issue_number")

        if not feature or not issue_number:
            return AgentResult(
                success=False,
                error="Feature and issue_number required for handoff",
            )

        # Prepare context for PlannerAgent
        planner_context = {
            "feature_id": feature.get("id"),
            "feature_name": feature.get("name"),
            "description": feature.get("description"),
            "user_story": feature.get("user_story", {}),
            "acceptance_criteria": feature.get("acceptance_criteria", []),
            "effort_estimate": feature.get("effort"),
            "from_pm": True,
        }

        handoff_comment = f"""## Handoff to Planner Agent

Feature **{feature.get('name')}** (#{feature.get('id')}) has been approved for planning.

The Planner Agent will now:
1. Analyze technical requirements
2. Break down into implementable tasks
3. Identify dependencies and execution order

---
*Handoff by PM Agent*
"""

        return AgentResult(
            success=True,
            output={
                "planner_context": planner_context,
                "handoff_comment": handoff_comment,
                "issue_number": issue_number,
                "action": "handoff_ready",
            },
            tokens_used=self.tokens_used.copy(),
        )

    def _parse_json_response(self, response: str) -> dict[str, Any] | None:
        """Parse JSON from LLM response."""
        import json

        # Try to find JSON in the response
        try:
            # First, try parsing the entire response
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown
        import re
        json_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        brace_match = re.search(r"\{[\s\S]*\}", response)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON from response", response=response[:200])
        return None

    def _generate_vision_md(self, vision_data: dict[str, Any]) -> str:
        """Generate VISION.md content from vision data."""
        from datetime import datetime, timezone

        # Format goals as bullet list
        goals = vision_data.get("goals", [])
        goals_formatted = "\n".join(f"{i+1}. {g}" for i, g in enumerate(goals))

        # Format metrics table
        metrics = vision_data.get("metrics", [])
        metrics_rows = []
        for m in metrics:
            metrics_rows.append(
                f"| {m.get('metric', 'N/A')} | {m.get('target', 'N/A')} | "
                f"{m.get('current', 'N/A')} | {m.get('status', 'Not Started')} |"
            )
        metrics_table = "\n".join(metrics_rows) if metrics_rows else "| N/A | N/A | N/A | N/A |"

        # Format scope lists
        in_scope = vision_data.get("in_scope", [])
        in_scope_formatted = "\n".join(f"- {s}" for s in in_scope) if in_scope else "- To be defined"

        out_of_scope = vision_data.get("out_of_scope", [])
        out_of_scope_formatted = "\n".join(f"- {s}" for s in out_of_scope) if out_of_scope else "- To be defined"

        # Format constraints and assumptions
        constraints = vision_data.get("constraints", [])
        constraints_formatted = "\n".join(f"- {c}" for c in constraints) if constraints else "- None identified"

        assumptions = vision_data.get("assumptions", [])
        assumptions_formatted = "\n".join(f"- {a}" for a in assumptions) if assumptions else "- None identified"

        return VISION_TEMPLATE.format(
            problem_statement=vision_data.get("problem_statement", "To be defined"),
            target_users=vision_data.get("target_users", "To be defined"),
            vision_statement=vision_data.get("vision_statement", "To be defined"),
            goals=goals_formatted,
            metrics_table=metrics_table,
            in_scope=in_scope_formatted,
            out_of_scope=out_of_scope_formatted,
            constraints=constraints_formatted,
            assumptions=assumptions_formatted,
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            version="1.0",
        )

    def _generate_backlog_md(self, backlog_data: dict[str, Any]) -> str:
        """Generate BACKLOG.md content from backlog data."""
        from datetime import datetime, timezone

        features = backlog_data.get("features", [])
        summary = backlog_data.get("summary", {})

        # Group features by priority
        by_priority: dict[str, list[dict[str, Any]]] = {
            "P0": [], "P1": [], "P2": [], "P3": []
        }
        completed = []

        for f in features:
            priority = f.get("priority", "P1")
            if f.get("status") == "Done":
                completed.append(f)
            elif priority in by_priority:
                by_priority[priority].append(f)
            else:
                by_priority["P1"].append(f)

        # Generate priority sections
        priority_labels = {
            "P0": "P0 - Critical",
            "P1": "P1 - High",
            "P2": "P2 - Medium",
            "P3": "P3 - Low",
        }

        sections = []
        for priority in ["P0", "P1", "P2", "P3"]:
            if by_priority[priority]:
                sections.append(f"## {priority_labels[priority]}\n")
                for f in by_priority[priority]:
                    sections.append(self._format_feature_md(f))

        features_content = "\n".join(sections) if sections else "No features defined yet."

        # Generate completed table
        completed_rows = []
        for f in completed:
            completed_rows.append(
                f"| {f.get('name', 'N/A')} | {f.get('issue', 'N/A')} | "
                f"{f.get('pr', 'N/A')} | {f.get('completed_at', 'N/A')} |"
            )
        completed_table = "\n".join(completed_rows) if completed_rows else "| N/A | N/A | N/A | N/A |"

        # Calculate summary
        total = len(features)
        ready = len([f for f in features if f.get("status") == "Ready"])
        in_progress = len([f for f in features if f.get("status") == "In Progress"])
        done = len(completed)

        return BACKLOG_TEMPLATE.format(
            total=total,
            ready=ready,
            in_progress=in_progress,
            done=done,
            features_by_priority=features_content,
            completed_table=completed_table,
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

    def _format_feature_md(self, feature: dict[str, Any]) -> str:
        """Format a single feature for BACKLOG.md."""
        user_story = feature.get("user_story", {})
        acceptance_criteria = feature.get("acceptance_criteria", [])
        dependencies = feature.get("dependencies", [])

        ac_formatted = "\n".join(f"  - [ ] {c}" for c in acceptance_criteria) if acceptance_criteria else "  - [ ] To be defined"
        deps_formatted = ", ".join(f"#{d}" for d in dependencies) if dependencies else "None"

        issue_link = f"#{feature.get('issue_number')}" if feature.get("issue_number") else "(not created)"

        return FEATURE_TEMPLATE.format(
            name=feature.get("name", "Unnamed"),
            feature_id=feature.get("id", "unknown"),
            status=feature.get("status", "Ready"),
            issue_link=issue_link,
            description=feature.get("description", "No description"),
            user_type=user_story.get("user_type", "user"),
            capability=user_story.get("capability", "..."),
            benefit=user_story.get("benefit", "..."),
            acceptance_criteria=ac_formatted,
            dependencies=deps_formatted,
            effort=feature.get("effort", "M"),
            notes=feature.get("notes", "None"),
        )

    def _format_features_for_prompt(self, features: list[dict[str, Any]]) -> str:
        """Format features list for LLM prompt."""
        if not features:
            return "No features defined"

        lines = []
        for f in features:
            lines.append(
                f"- [{f.get('priority', 'P1')}] {f.get('name', 'Unnamed')} "
                f"({f.get('status', 'Ready')}, {f.get('effort', 'M')})"
            )
        return "\n".join(lines)

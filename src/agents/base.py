"""Base agent class - common functionality for all agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import anthropic
import structlog

from src.orchestrator.config import Settings
from src.orchestrator.state_machine import Task

logger = structlog.get_logger()


@dataclass
class AgentResult:
    """Result of agent execution."""
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    tokens_used: dict[str, int] = field(default_factory=dict)  # model -> tokens


class BaseAgent(ABC):
    """Base class for all agents."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.tokens_used: dict[str, int] = {}
    
    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Agent type identifier."""
        ...
    
    @abstractmethod
    async def execute(self, task: Task, context: dict[str, Any]) -> AgentResult:
        """Execute agent task."""
        ...
    
    def _select_model(self, task_type: str, complexity: str = "standard") -> str:
        """Select appropriate model based on task and complexity."""
        if complexity == "trivial":
            return self.settings.model_haiku
        elif complexity == "complex":
            return self.settings.model_opus
        else:
            # Standard complexity
            if task_type in ("file_analysis", "planning"):
                return self.settings.model_haiku
            else:
                return self.settings.model_sonnet
    
    async def _complete(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Make completion request to Claude."""
        if model is None:
            model = self.settings.model_sonnet
        
        messages = [{"role": "user", "content": prompt}]
        
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        
        if system:
            kwargs["system"] = system
        
        response = self.client.messages.create(**kwargs)
        
        # Track token usage
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        total = input_tokens + output_tokens
        
        self.tokens_used[model] = self.tokens_used.get(model, 0) + total
        
        logger.debug(
            "Completion",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        
        # Extract text from response
        text_blocks = [
            block.text for block in response.content
            if hasattr(block, "text")
        ]
        return "\n".join(text_blocks)
    
    async def analyze_files(self, issue_body: str) -> set[str]:
        """Predict which files an issue will touch."""
        prompt = f"""Analyze this GitHub issue and predict which files will need to be modified.

Issue:
{issue_body}

List only the file paths, one per line. Include both files that will be modified and new files that will be created.
If you cannot determine specific files, list the directories or patterns that are likely involved.

Files:"""
        
        response = await self._complete(
            prompt,
            model=self.settings.model_haiku,
            max_tokens=1024,
        )
        
        # Parse response into file set
        files = set()
        for line in response.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                # Remove common prefixes like "- " or "* "
                if line.startswith(("- ", "* ", "• ")):
                    line = line[2:]
                files.add(line)
        
        return files
    
    async def estimate_complexity(self, issue_body: str) -> str:
        """Estimate task complexity."""
        prompt = f"""Classify this GitHub issue's implementation complexity.

Issue:
{issue_body}

Respond with exactly one word: trivial, standard, or complex

trivial: single file, <20 lines, obvious fix (typos, config changes, simple bugs)
standard: 2-5 files, clear approach, moderate changes
complex: architectural changes, multiple components, ambiguous requirements, >5 files"""
        
        response = await self._complete(
            prompt,
            model=self.settings.model_haiku,
            max_tokens=10,
        )
        
        result = response.strip().lower()
        if result not in ("trivial", "standard", "complex"):
            result = "standard"
        
        return result

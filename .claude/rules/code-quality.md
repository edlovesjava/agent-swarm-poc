# Code Quality Rules

## Python Standards

### Type Hints Required
```python
# Required
def process_task(task_id: str, timeout: int = 30) -> TaskResult:
    ...

# Not allowed
def process_task(task_id, timeout=30):
    ...
```

### Async for All I/O
```python
# Required
async def fetch_issue(issue_id: int) -> Issue:
    async with session.get(url) as response:
        return await response.json()

# Not allowed (blocks event loop)
def fetch_issue(issue_id: int) -> Issue:
    return requests.get(url).json()
```

### Pydantic for External Data
```python
# Required
class WebhookPayload(BaseModel):
    action: str
    issue: IssuePayload

@router.post("/webhook")
async def handle(payload: WebhookPayload):
    ...

# Not allowed (unvalidated dicts)
@router.post("/webhook")
async def handle(payload: dict):
    ...
```

## Testing Requirements

- All new functions require tests
- Use pytest-asyncio for async tests
- Mock external services (GitHub API, Redis)
- Test both success and error paths

```python
@pytest.mark.asyncio
async def test_state_transition():
    machine = StateMachine(redis)
    await machine.transition("task-1", TaskState.PLANNING)
    assert await machine.get_state("task-1") == TaskState.PLANNING
```

## Error Handling

### Use Custom Exceptions
```python
class AgentError(Exception):
    """Base exception for agent errors."""
    pass

class TaskNotFoundError(AgentError):
    """Task does not exist."""
    pass

class StateTransitionError(AgentError):
    """Invalid state transition."""
    pass
```

### Log Errors with Context
```python
import structlog
logger = structlog.get_logger()

try:
    await process_task(task)
except TaskError as e:
    logger.error(
        "task_failed",
        task_id=task.id,
        error=str(e),
        state=task.state,
    )
    raise
```

## Formatting

Run before committing:
```bash
black src/ tests/
isort src/ tests/
ruff check src/ tests/ --fix
mypy src/
```

## Documentation

- Docstrings for public functions
- Type hints serve as documentation
- README for module-level docs
- Architecture docs in `/docs`

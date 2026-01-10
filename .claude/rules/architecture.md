# Architecture Rules

## Layers

```
┌─────────────────────────────────────────┐
│            API Layer (FastAPI)           │
│  - Webhook handlers                      │
│  - REST endpoints                        │
│  - Request validation                    │
├─────────────────────────────────────────┤
│           Service Layer                  │
│  - State machine                         │
│  - Task router                           │
│  - Coordination (locks)                  │
├─────────────────────────────────────────┤
│            Agent Layer                   │
│  - Worker agent                          │
│  - Planner agent                         │
│  - Fixer agent                           │
├─────────────────────────────────────────┤
│         Integration Layer                │
│  - GitHub App client                     │
│  - Redis client                          │
│  - Anthropic client                      │
└─────────────────────────────────────────┘
```

## Principles

### 1. Dependency Injection
```python
# Good - injectable dependency
async def get_redis() -> Redis:
    return await aioredis.from_url(settings.redis_url)

@router.post("/tasks")
async def create_task(redis: Redis = Depends(get_redis)):
    ...

# Bad - hardcoded dependency
@router.post("/tasks")
async def create_task():
    redis = await aioredis.from_url("redis://localhost:6379")
    ...
```

### 2. Single Responsibility
Each module has one purpose:
- `state_machine.py` - Only state transitions
- `task_router.py` - Only task assignment
- `file_locks.py` - Only lock management

### 3. Interface Segregation
```python
# Good - focused interfaces
class TaskReader(Protocol):
    async def get_task(self, task_id: str) -> Task: ...

class TaskWriter(Protocol):
    async def save_task(self, task: Task) -> None: ...

# Bad - fat interface
class TaskManager:
    async def get_task(self, task_id: str) -> Task: ...
    async def save_task(self, task: Task) -> None: ...
    async def send_notification(self, task: Task) -> None: ...
    async def generate_report(self) -> Report: ...
```

### 4. Config from Environment
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    github_app_id: str
    github_private_key_path: str
    redis_url: str = "redis://localhost:6379"
    anthropic_api_key: str

    model_config = ConfigDict(env_file=".env")
```

## State Machine Rules

### Valid Transitions Only
```python
VALID_TRANSITIONS = {
    TaskState.QUEUED: {TaskState.PLANNING},
    TaskState.PLANNING: {TaskState.PLAN_REVIEW, TaskState.FAILED},
    TaskState.PLAN_REVIEW: {TaskState.APPROVED, TaskState.PLANNING},
    TaskState.APPROVED: {TaskState.EXECUTING},
    TaskState.EXECUTING: {TaskState.PR_OPEN, TaskState.FAILED},
    TaskState.FAILED: {TaskState.FIXER_REVIEW},
}
```

### All Transitions Logged
```python
async def transition(self, task_id: str, new_state: TaskState) -> None:
    old_state = await self.get_state(task_id)
    if new_state not in VALID_TRANSITIONS.get(old_state, set()):
        raise StateTransitionError(f"{old_state} -> {new_state}")

    logger.info(
        "state_transition",
        task_id=task_id,
        from_state=old_state,
        to_state=new_state,
    )
    await self._set_state(task_id, new_state)
```

## Coordination Rules

### File Locks
- Always use TTL (default 30 minutes)
- Check locks before task assignment
- Release locks on completion or failure

### Branch Strategy
- Branch name: `agent/{issue_number}-{slug}`
- One branch per task
- Use git worktrees for isolation

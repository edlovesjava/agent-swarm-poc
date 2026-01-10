# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Autonomous Agent Swarm PoC - A self-hosted system of collaborating Claude agents that resolve GitHub issues and produce PRs with human approval gates.

## Build & Run Commands

### Orchestrator (Python/FastAPI)
```bash
# Setup
pip install -e ".[dev]"        # Install with dev dependencies

# Run
uvicorn src.orchestrator.main:app --reload  # Dev server on http://localhost:8000

# Tests
pytest                         # Run all tests
pytest tests/ -v               # Verbose test output
pytest --cov=src              # With coverage
```

### Docker
```bash
docker-compose up              # Start all services (Redis, orchestrator)
docker-compose up -d           # Detached mode
docker-compose logs -f         # Follow logs
```

### Redis (for development)
```bash
docker run -d -p 6379:6379 redis:alpine  # Local Redis
redis-cli                      # Connect to Redis CLI
```

## Architecture

```
GitHub Webhooks → Orchestrator (FastAPI) → Task Queue (Redis) → Agent Pool
                        │                         │
                        ▼                         ▼
                  GitHub App API            OpenHands Runtime
                  (Checks, Comments,        (Sandboxed execution)
                   Labels, PRs)
```

**Core Components:**
- `src/orchestrator/` - FastAPI app, webhook handling, state machine
- `src/agents/` - Worker, Planner, Fixer agent implementations
- `src/coordination/` - File locks, branch management
- `src/github_app/` - GitHub App client, Checks API integration

**Task Flow:**
```
QUEUED → PLANNING → PLAN_REVIEW → APPROVED → EXECUTING → PR_OPEN
              ↓           ↓                        ↓
           (revision)  (feedback)             FIXER_REVIEW → HUMAN_ESCALATION
```

## Key Files

### Orchestrator
- `src/orchestrator/main.py` - FastAPI entry point, webhook routes
- `src/orchestrator/state_machine.py` - Task state transitions
- `src/orchestrator/task_router.py` - Issue → agent assignment
- `src/orchestrator/config.py` - Configuration management

### Agents
- `src/agents/base.py` - Base agent class
- `src/agents/worker.py` - Issue → PR worker agent
- `src/agents/planner.py` - Architecture planning agent

### Coordination
- `src/coordination/file_locks.py` - Redis-based file locking

### GitHub Integration
- `src/github_app/client.py` - GitHub App API wrapper

## Configuration

### Environment Variables
```bash
# GitHub App
GITHUB_APP_ID=
GITHUB_PRIVATE_KEY_PATH=
GITHUB_WEBHOOK_SECRET=

# Anthropic
ANTHROPIC_API_KEY=

# Redis
REDIS_URL=redis://localhost:6379

# OpenHands (optional)
OPENHANDS_API_URL=
```

### Repository Config
Repositories can configure agent behavior via `.github/agents/config.yaml`:
- Issue filters (labels, upvotes)
- Model preferences per task type
- Approval requirements
- Failure handling settings

## Testing

```bash
pytest                                    # All tests
pytest tests/test_state_machine.py       # Specific test file
pytest -k "test_transition"              # Tests matching pattern
pytest --cov=src --cov-report=html       # Coverage report
```

## Code Style

- Python 3.11+
- Type hints required for all functions
- Async/await for I/O operations
- Pydantic for data validation
- Black + isort for formatting
- ruff for linting

```bash
black src/ tests/                        # Format code
isort src/ tests/                        # Sort imports
ruff check src/ tests/                   # Lint
mypy src/                                # Type checking
```

## Design Documents

- `docs/agent-swarm-architecture.md` - Full architecture specification
- `docs/architecture.md` - Technical overview

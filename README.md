# Agent Swarm PoC

Autonomous Claude agent swarm for GitHub issue-to-PR automation.

## Overview

A self-hosted system of collaborating AI agents that:
- Pick up GitHub issues labeled for agent work
- Generate implementation plans (human-approved)
- Execute changes in isolated sandboxes
- Create PRs with full audit trail
- Review and fix PRs on human request

## Architecture

See [docs/architecture.md](docs/architecture.md) for full design.

```
GitHub Issues → Orchestrator → Agent Pool → PRs
                    ↓
              Coordination Layer
              (file locks, state)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- GitHub App credentials (see setup)
- Anthropic API key

### Setup

1. **Create GitHub App**
   ```bash
   # Follow GitHub's guide to create an app with:
   # - Webhook URL: https://your-domain/webhook
   # - Permissions: Issues (R/W), PRs (R/W), Checks (R/W), Contents (R/W)
   # - Events: Issues, Issue comments, Pull requests, Check runs
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run locally**
   ```bash
   docker-compose up
   ```

4. **Install GitHub App** on your target repository

## Project Structure

```
agent-swarm-poc/
├── src/
│   ├── orchestrator/      # Main service, webhook handler, state machine
│   ├── agents/            # Agent implementations (worker, fixer, reviewer, planner)
│   ├── github_app/        # GitHub API client, Checks API, comments
│   └── coordination/      # File locks, branch management
├── config/                # Configuration schemas and defaults
├── scripts/               # CLI tools, setup helpers
├── tests/                 # Unit and integration tests
└── docs/                  # Architecture docs
```

## Configuration

Repository-level config in `.github/agents/config.yaml`:

```yaml
issue_filter:
  labels:
    include: ["agent-ok"]
coordination:
  max_concurrent_agents: 3
```

Agent instructions in `.github/agents/AGENTS.md`.

## Commands

Humans interact via issue/PR comments:

| Command | Effect |
|---------|--------|
| `/approve` | Approve agent's plan |
| `/agent-review` | Request agent code review |
| `/agent-fix` | Agent addresses review comments |
| `/agent-plan` | Request dependency analysis |
| `/agent-stop` | Halt agent work |

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/

# Type check
mypy src/
```

## License

MIT

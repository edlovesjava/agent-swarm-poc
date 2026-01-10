# Agent Swarm PoC Roadmap

## Current Focus: Phase 1 (PoC)

### Week 1: Foundation
- [ ] GitHub App scaffolding (webhook receiver, Checks API client)
- [ ] Redis-based task queue and state machine
- [ ] Single worker agent with OpenHands SDK
- [ ] Basic file lock coordination

### Week 2: Core Flow
- [ ] Plan generation and comment posting
- [ ] `/approve` command parsing
- [ ] PR creation with proper metadata
- [ ] Basic fixer agent

### Week 3: Polish
- [ ] Label management automation
- [ ] Check Run annotations for key decisions
- [ ] Config file parsing (`.github/agents/config.yaml`)
- [ ] Cost tracking and logging

## Phase 2: Production Hardening

- [ ] Persistent state (PostgreSQL instead of Redis-only)
- [ ] Agent health monitoring and auto-restart
- [ ] Rate limiting (GitHub API, LLM calls)
- [ ] Audit logging for all agent actions
- [ ] Prometheus metrics export

## Phase 3: Multi-Repo Support

- [ ] Per-repo configuration inheritance
- [ ] Cross-repo file lock awareness
- [ ] Shared agent pool across repos
- [ ] Repo-level permission scoping

## Phase 4: Cloud Deployment

- [ ] Container orchestration (k8s or ECS)
- [ ] E2B or Modal integration for sandboxes
- [ ] Auto-scaling based on queue depth
- [ ] Multi-tenant isolation (for SaaS)

## Design Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-01-10 | Python/FastAPI for orchestrator | Async-first, good LLM SDK support |
| 2025-01-10 | Redis for PoC state | Simple, fast, can upgrade to Postgres |
| 2025-01-10 | OpenHands for sandbox | MIT licensed, Docker-based |

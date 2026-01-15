# PoC Plan: Minimal Vertical Slice

## Objective

Prove the core loop works: **Issue -> Agent Plan -> Human Approval -> Agent Execution -> PR**

This is NOT about building everything. It is about demonstrating one issue flowing end-to-end through the system.

---

## Current State Assessment

### Already Implemented (Solid)

| Component | Status | Notes |
|-----------|--------|-------|
| `state_machine.py` | Complete | All states, transitions, Redis persistence |
| `config.py` | Complete | Settings from environment |
| `file_locks.py` | Complete | Redis-based lock coordination |
| `github_app/client.py` | Complete | Checks, comments, labels, PRs, files |
| `base.py` (agents) | Complete | Model selection, completion, token tracking |
| `worker.py` (_generate_plan) | Complete | Plan generation with prompts |
| `main.py` (webhook handler) | Complete | Signature verification, routing |
| `docker-compose.yml` | Complete | Redis + orchestrator setup |

### Partially Implemented (Needs Wiring)

| Component | Gap | Effort |
|-----------|-----|--------|
| `task_router.py` | Calls handlers but `TODO: Trigger agent` comments | Small - wire up agents |
| `worker.py` (_implement) | Placeholder - needs OpenHands or fallback | Medium - integration |

### Missing for PoC

| Component | Priority | Description |
|-----------|----------|-------------|
| Agent execution loop | P0 | Actually run agent on approved task |
| Plan posting | P0 | Post plan to GitHub issue as comment |
| Plan approval flow | P0 | Parse /approve, transition, execute |
| PR creation | P0 | Create PR from agent work |
| Label updates | P1 | Update labels on state change |
| Check Run updates | P1 | Update Checks API on transitions |

---

## Minimal PoC Scope

### What We Will Build

1. **Trigger**: Issue labeled `agent-ok` creates task, starts planning
2. **Plan**: Worker agent generates plan, posts as GitHub comment
3. **Approve**: Human comments `/approve`, task transitions to APPROVED
4. **Execute**: Agent implements (mock for PoC - just create files)
5. **PR**: Agent creates PR with changes

### What We Will NOT Build (Yet)

- OpenHands integration (use mock implementation)
- Fixer agent retry loops
- PR review agent
- Config file parsing (.github/agents/config.yaml)
- Check Run annotations
- Cost tracking display
- Multiple concurrent agents

---

## Implementation Tasks

### Phase 1: Wire the Core Loop (Day 1-2)

#### 1.1 Trigger Planning on Issue Event
**File**: `src/orchestrator/task_router.py`

Gap: `handle_issue_event` creates task but does not trigger planning.

```python
# After: task = await self.state_machine.create_task(...)
# Add:
await self._trigger_planning(task, issue)
```

Need to implement:
```python
async def _trigger_planning(self, task: Task, issue: dict) -> None:
    """Transition to PLANNING and invoke worker agent."""
    await self.state_machine.transition(task.id, TaskState.PLANNING)

    # Get worker agent
    worker = WorkerAgent(self.settings)
    result = await worker.execute(task, {
        "action": "plan",
        "issue_body": issue.get("body", ""),
        "issue_title": issue.get("title", ""),
    })

    if result.success:
        # Post plan as comment
        await self._post_plan(task, result.output["plan"])
        await self.state_machine.transition(
            task.id,
            TaskState.PLAN_REVIEW,
            metadata={"plan": result.output}
        )
```

Acceptance: Issue with `agent-ok` label triggers plan comment.

---

#### 1.2 Post Plan as GitHub Comment
**File**: `src/orchestrator/task_router.py`

Need to implement:
```python
async def _post_plan(self, task: Task, plan: str) -> None:
    """Post plan to GitHub issue."""
    github = GitHubClient(self.settings)

    body = f"""## Agent Plan for #{task.issue_number}

{plan}

---
Reply `/approve` to proceed, or provide feedback for revision.
"""

    await github.create_issue_comment(
        repo=task.repo,
        issue_number=task.issue_number,
        body=body,
    )

    # Update label
    await github.set_agent_label(task.repo, task.issue_number, "agent:awaiting-plan")
```

Acceptance: Plan appears as comment on issue.

---

#### 1.3 Handle /approve Command
**File**: `src/orchestrator/task_router.py`

Gap: `_handle_approve` records decision but does not trigger execution.

Add after transition to APPROVED:
```python
# Trigger execution
await self._trigger_execution(task)
```

Need to implement:
```python
async def _trigger_execution(self, task: Task) -> None:
    """Execute approved plan."""
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
        await self._create_pr(task, result)
```

Acceptance: `/approve` comment triggers execution flow.

---

### Phase 2: Mock Implementation (Day 2-3)

#### 2.1 Mock Implementation in Worker Agent
**File**: `src/agents/worker.py`

For PoC, skip OpenHands. Instead, create a simple mock that:
1. Parses files from plan
2. Creates placeholder changes
3. Returns success with file list

```python
async def _implement(self, task: Task, context: dict) -> AgentResult:
    """Implement the approved plan (mock for PoC)."""
    plan = context.get("plan", "")

    # Parse file list from plan
    files_changed = self._parse_files_from_plan(plan)

    # For PoC: just log what would be changed
    logger.info(
        "Mock implementation",
        task_id=task.id,
        files=files_changed,
    )

    return AgentResult(
        success=True,
        output={
            "status": "mock_implementation",
            "files_changed": files_changed,
            "branch": f"agent/{task.issue_number}-mock",
        },
        tokens_used=self.tokens_used.copy(),
    )
```

Acceptance: Execution returns success with mock file list.

---

#### 2.2 Create PR
**File**: `src/orchestrator/task_router.py`

```python
async def _create_pr(self, task: Task, result: AgentResult) -> None:
    """Create PR from agent work."""
    github = GitHubClient(self.settings)

    branch = result.output.get("branch", f"agent/{task.issue_number}")
    files = result.output.get("files_changed", [])

    # Get latest plan for PR body
    plan = task.plan_versions[-1] if task.plan_versions else {}

    body = f"""## Resolves #{task.issue_number}

### Summary
{plan.get('plan', 'Implementation complete.')}

### Files Changed
{chr(10).join(f'- `{f}`' for f in files)}

---
*Generated by Agent Swarm*
"""

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
```

Acceptance: PR is created linking to issue.

---

### Phase 3: Test End-to-End (Day 3-4)

#### 3.1 Integration Test Script

Create `scripts/test_e2e.py`:
```python
"""End-to-end test for the agent swarm PoC."""

import asyncio
import httpx

async def simulate_issue_webhook():
    """Simulate GitHub issue.opened webhook."""
    payload = {
        "action": "labeled",
        "repository": {"full_name": "test/repo"},
        "sender": {"login": "testuser"},
        "issue": {
            "number": 1,
            "title": "Add hello world endpoint",
            "body": "Add a /hello endpoint that returns 'Hello, World!'",
            "labels": [{"name": "agent-ok"}],
        },
    }

    # Note: In real test, need to generate valid signature
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/webhook",
            json=payload,
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": "sha256=...",  # Need valid sig
            },
        )
        print(f"Issue webhook: {resp.status_code}")

async def simulate_approve_comment():
    """Simulate /approve comment."""
    payload = {
        "action": "created",
        "repository": {"full_name": "test/repo"},
        "issue": {"number": 1},
        "comment": {
            "body": "/approve",
            "user": {"login": "testuser"},
        },
    }
    # ... similar to above

if __name__ == "__main__":
    asyncio.run(simulate_issue_webhook())
```

#### 3.2 Manual Test Checklist

1. [ ] Start services: `docker-compose up`
2. [ ] Create issue with `agent-ok` label in test repo
3. [ ] Verify: Plan comment appears
4. [ ] Verify: Label changes to `agent:awaiting-plan`
5. [ ] Comment `/approve` on issue
6. [ ] Verify: PR is created
7. [ ] Verify: Label changes to `agent:pr-open`
8. [ ] Verify: Task visible at `/tasks` endpoint

---

## Acceptance Criteria for "PoC Complete"

### Must Have (P0)

- [ ] Issue with `agent-ok` label triggers task creation
- [ ] Agent generates plan and posts as comment
- [ ] `/approve` comment transitions task and triggers execution
- [ ] PR is created (even if branch is mock/placeholder)
- [ ] Task state visible via API (`GET /tasks/{id}`)
- [ ] Labels update to reflect state

### Nice to Have (P1) - Not Required for PoC

- [ ] Check Run created and updated
- [ ] Plan revision on feedback (non-/approve comment)
- [ ] Actual code changes (OpenHands integration)
- [ ] Fixer agent on failure

---

## Risk Mitigation

### Risk: GitHub API Rate Limits
**Mitigation**: Use installation token caching (already implemented in client.py)

### Risk: OpenHands Integration Complexity
**Mitigation**: Use mock implementation for PoC, defer real integration

### Risk: Redis Unavailable
**Mitigation**: Docker compose ensures Redis starts first

### Risk: Webhook Signature Verification Fails
**Mitigation**: Already implemented, just need correct secret in env

---

## File Summary

Files to modify:
- `src/orchestrator/task_router.py` - Add agent invocation
- `src/agents/worker.py` - Add mock implementation

Files to create:
- `scripts/test_e2e.py` - E2E test script

No new dependencies required.

---

## Estimated Effort

| Task | Effort | Notes |
|------|--------|-------|
| Wire planning trigger | 2h | Straightforward |
| Post plan comment | 1h | Use existing client |
| Wire /approve -> execution | 2h | Connect handlers |
| Mock implementation | 2h | Parse plan, return mock |
| Create PR | 1h | Use existing client |
| E2E test script | 2h | Simulate webhooks |
| Manual testing | 2h | Debug and fix |
| **Total** | **12h** | ~2 days |

---

## Next Steps After PoC

Once the vertical slice works:

1. **OpenHands Integration**: Replace mock with real agent execution
2. **Plan Revision**: Handle non-/approve comments as feedback
3. **Fixer Agent**: Add retry loop on failure
4. **Check Runs**: Add Checks API integration for visibility
5. **Config Parsing**: Read `.github/agents/config.yaml`

These are tracked in the full roadmap at `docs/architecture/vision.md`.

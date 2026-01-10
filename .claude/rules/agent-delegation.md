# Agent Delegation Protocol

## When to Delegate

Invoke the **project-manager** agent FIRST for any task that:
- Involves 3+ implementation steps
- Spans multiple concerns (code + tests, implementation + deployment)
- Requires coordination across different specialties
- Is non-trivial and would benefit from structured planning

## Delegation Workflow

1. **User requests work** → Invoke project-manager agent
2. **PM creates delegated todos** → Each todo specifies the responsible agent
3. **User reviews plan** → Approves, modifies, or rejects
4. **Execute via agents** → Invoke the assigned agent for each todo item
5. **PM tracks progress** → Update todos as agents complete work

## Agent Assignments

Use these agents for their specialties:

| Domain | Agent | Use For |
|--------|-------|---------|
| Python code | `python-specialist` | FastAPI, async, implementation |
| Architecture | `architect` | Design decisions, patterns |
| DevOps | `devops-specialist` | Docker, CI/CD, deployment |
| Code review | `code-reviewer` | PR review, quality checks |
| GitHub API | `github-specialist` | Webhooks, Checks API, Apps |
| Planning | `project-manager` | Task breakdown, prioritization |

## Todo Format with Delegation

When PM creates todos, use this format:
```
- [ ] <task description> → @<agent-type>
```

Example:
```
- [ ] Implement webhook signature verification → @python-specialist
- [ ] Design state machine transitions → @architect
- [ ] Configure Redis container → @devops-specialist
- [ ] Review PR for security issues → @code-reviewer
```

## Scope Management

When encountering ideas outside current scope, use `/park` to capture them:

```
/park <idea description>
```

This adds the idea to `PARKING_LOT.md` for future elaboration without derailing current work.

**When to park:**
- Feature requests that don't fit Phase 1
- Interesting tangents discovered during implementation
- "Nice to have" improvements
- Technical debt worth tracking
- Ideas for Phase 2/3/4

## Exceptions

Direct execution (without PM delegation) is acceptable for:
- Single-step trivial tasks (typo fix, simple query)
- Exploratory research (reading files, searching code)
- Direct user request to skip planning
- Urgent fixes where speed matters more than process

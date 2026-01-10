---
description: Run code quality checks - tests, linting, type checking
allowed-tools: Bash
---

# Code Quality Check

Run all code quality checks for the project.

## Commands to Run

```bash
# Format check (don't modify, just check)
echo "=== Checking formatting ==="
black --check src/ tests/ 2>/dev/null || echo "Run: black src/ tests/"

# Import sorting check
echo "=== Checking imports ==="
isort --check-only src/ tests/ 2>/dev/null || echo "Run: isort src/ tests/"

# Linting
echo "=== Running linter ==="
ruff check src/ tests/ 2>/dev/null || echo "Linting issues found"

# Type checking
echo "=== Type checking ==="
mypy src/ 2>/dev/null || echo "Type errors found"

# Tests
echo "=== Running tests ==="
pytest -v 2>/dev/null || echo "Tests failed or not configured"

# Coverage
echo "=== Coverage report ==="
pytest --cov=src --cov-report=term-missing 2>/dev/null || echo "Coverage not available"
```

## Output Format

```markdown
## Code Quality Report

### Formatting
- [ ] Black: [Pass/Fail]
- [ ] isort: [Pass/Fail]

### Linting
- [ ] ruff: [Pass/Fail]
  - [List of issues if any]

### Type Checking
- [ ] mypy: [Pass/Fail]
  - [List of errors if any]

### Tests
- [ ] pytest: [Pass/Fail]
  - Tests run: X
  - Passed: X
  - Failed: X

### Coverage
- Overall: X%
- [Module coverage breakdown]

### Summary
[Overall health assessment]
```

## Quick Fixes

If issues found, suggest fixes:
```bash
# Auto-fix formatting
black src/ tests/
isort src/ tests/

# Auto-fix some lint issues
ruff check src/ tests/ --fix
```

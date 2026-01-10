# Agent Instructions

This file provides instructions for AI agents working on this repository.
Place at `.github/agents/AGENTS.md` in your repository.

## Code Style

- Follow existing patterns in the codebase
- Use consistent naming conventions
- Add comments for complex logic
- Keep functions focused and small

## Before Committing

- Run `npm run lint` (or equivalent) to check style
- Run `npm test` to verify changes don't break existing tests
- Ensure all new code has appropriate test coverage

## Testing Requirements

- Unit tests required for all new functions
- Integration tests for API changes
- Update existing tests if behavior changes

## Documentation

- Update README if adding new features
- Add JSDoc/docstrings to new functions
- Update API documentation for endpoint changes

## Off Limits

These files/directories should NOT be modified by agents without explicit human approval:

- `src/config/production.ts` - Production configuration
- `migrations/` - Database migrations require human review
- `package.json` - Dependency changes need human approval
- `.env*` - Environment files
- `Dockerfile` - Container configuration

## Commit Messages

Use conventional commits format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

Example:
```
fix(auth): handle expired JWT tokens gracefully

Add 30-second grace period to token validation to handle
clock skew between services.

Closes #42
```

## Pull Request Description

Always include:

1. **Summary**: What does this PR do?
2. **Issue**: Link to the original issue (`Closes #XX`)
3. **Changes**: List of specific changes made
4. **Testing**: How was this tested?
5. **Screenshots**: If UI changes (optional)

## Architecture Notes

<!-- Add project-specific architecture notes here -->

- Services communicate via REST APIs
- Database: PostgreSQL with TypeORM
- Authentication: JWT tokens with refresh
- Caching: Redis for session storage

## Common Patterns

<!-- Add project-specific patterns here -->

### Error Handling

```typescript
try {
  await operation();
} catch (error) {
  logger.error('Operation failed', { error, context });
  throw new AppError('OPERATION_FAILED', error);
}
```

### API Responses

```typescript
return {
  success: true,
  data: result,
  meta: { timestamp: new Date() }
};
```

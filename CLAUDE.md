# Claude Code Instructions

This file contains instructions for AI assistants working on this codebase.

## Setup

Always install dev dependencies before making changes:

```bash
pip install -e ".[dev,test]"
```

## Quality Standards

### Tests

Run the full test suite before committing:

```bash
pytest --cov=airlock --cov-report=term-missing
```

**100% code coverage is required.** Use `# pragma: no cover` only for genuinely untestable code (like `if __name__ == "__main__"` blocks).

### Linting

Run both linters:

```bash
flake8 airlock tests
python -m airlock.flake8_plugin
```

The flake8 plugin checks for:
- **AIR001**: Direct `.delay()` or `.apply_async()` calls bypass airlock
- **AIR002**: Inline imports inside functions

### No Inline Imports

Do not use imports inside functions. Move all imports to the top of the file.

Exceptions (must use `# noqa: AIR002`):
- Django `AppConfig.ready()` where imports must be delayed until settings are configured
- Conditional imports for optional dependencies (e.g., greenlet)

### Code Style

- Max line length: 100 characters
- Follow existing patterns in the codebase
- Keep changes minimal and focused

## Architecture

Airlock favors layered architecture: higher-level abstractions built cleanly on lower-level primitives, with clear boundaries and one-way dependencies. This applies to both the codebase organization and the API design.

Before making significant changes, understand the core concepts:

- **Scope**: Context manager that collects intents and dispatches on exit
- **Intent**: A deferred task call (task + args + kwargs + options)
- **Policy**: Decides whether an intent should be dispatched
- **Executor**: Dispatches intents to a backend (Celery, django-q, sync, etc.)

### Layering

The codebase is organized in layers:

- **Core** (`airlock/__init__.py`): Framework-agnostic primitives (Scope, Intent, Policy, configure/enqueue)
- **Integrations** (`airlock/integrations/`): Framework-specific adapters (Django, Celery, etc.)
- **Executors** (`airlock/integrations/executors/`): Backend dispatchers (celery, django-q, huey, dramatiq, sync)

Keep core free of framework dependencies. Integration code imports from core, never the reverse. This discipline is what allows airlock to support many frameworks without becoming coupled to any of them.

### API Styles

Airlock exposes multiple API styles for different use cases:

- **Imperative**: `airlock.enqueue(task, *args, **kwargs)` - explicit task enqueueing
- **Context manager**: `with airlock.scope(): ...` - batch intents within a block
- **Decorator**: `@airlock.scoped` - wrap a function in a scope

All styles ultimately use the same underlying Scope and Intent machinery.

Read the docs in `docs/` before adding new integrations or modifying core behavior.

## Documentation

When making code changes, propose corresponding documentation updates:

- New features need docs in `docs/`
- API changes should update docstrings
- Non-obvious behavior warrants comments; obvious behavior does not
- Update `CONTRIBUTING.md` if development workflow changes

## Commit Hygiene

- Write clear, descriptive commit messages
- Each commit should pass all tests and linting
- Don't bundle unrelated changes

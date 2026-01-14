# Contributing to Airlock

Thanks for your interest in contributing! Here's how to get started.

## Quick Start

```bash
git clone https://github.com/your-org/airlock.git
cd airlock
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Requires Python 3.10+.

## Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=airlock

# Run a specific test file
pytest tests/test_scope.py
```

To run integration tests against real backends (Django, Celery, etc.):

```bash
pip install -e ".[test]"
pytest
```

## Code Style

We use flake8 for linting:

```bash
flake8 airlock tests
```

This runs in CI on every pull request.

## Submitting Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add or update tests as needed
4. Run `pytest` and `flake8` to make sure everything passes
5. Open a pull request

For bug fixes, please include a test that fails without your fix.

## What We're Looking For

- Bug fixes
- Documentation improvements
- New integrations (executors, scopes for other frameworks)
- Interesting new applications of airlock
- Test coverage improvements
- Performance improvements

## Extending Airlock

Want to add support for a new framework or backend? See the extension docs:

- [Custom Executors](docs/extending/custom-executors.md) - dispatch intents to different backends
- [Custom Scopes](docs/extending/custom-scopes.md) - integrate with framework lifecycles
- [Custom Policies](docs/extending/custom-policies.md) - control which intents get dispatched

## Questions?

Open an issue if you're stuck or unsure about something. We're happy to help.

# Dev workflow commands

# Run tests
test *args:
    pytest {{args}}

# Run tests with coverage
cov *args:
    pytest --cov=airlock --cov-report=term-missing {{args}}

# Run tests with coverage and generate HTML report
cov-html *args:
    pytest --cov=airlock --cov-report=html {{args}}
    @echo "Coverage report: htmlcov/index.html"

# Run a specific test file
test-file file:
    pytest {{file}} -v

# Run Django integration tests
test-django:
    pytest tests/test_django_integration.py -v

# Serve docs locally
docs:
    mkdocs serve

# Build docs
docs-build:
    mkdocs build

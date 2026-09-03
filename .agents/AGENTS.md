# Python Workspace Rules for Antigravity IDE

## Python Code Standards & Auto-Correction Rules
- **Linter & Formatter**: Always use `ruff` (located at `./.venv/bin/ruff` or active environment).
- **Auto-Fix on Edit**: After creating or modifying any Python file (`.py`), automatically run:
  1. `./.venv/bin/ruff check --fix <filepath>`
  2. `./.venv/bin/ruff format <filepath>`
- **Imports**: Ensure imports are sorted according to Ruff standard (`I` rule set).
- **Type Annotations**: Follow Python 3.12+ modern typing conventions (e.g. `list[str]`, `dict[str, Any]`, `X | Y` union types via `UP007` / `UP006`).
- **Tests**: Ensure pytest tests pass cleanly using `./.venv/bin/pytest`.

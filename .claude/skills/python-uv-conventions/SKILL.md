---
name: python-uv-conventions
description: Coding conventions for cdforge - uv, ruff, single quotes, one import per line.
---

This is a Python CLI tool managed with `uv`. Follow these conventions for every change:

- Manage dependencies with `uv add` / `uv add --dev`; never edit `pyproject.toml`'s
  dependency lists by hand and never call `pip` directly.
- Run everything through `uv run` (`uv run pytest`, `uv run ruff check .`, `uv run
  cdforge`) so the project's own locked environment is used.
- String literals use single quotes (`'like this'`), enforced by
  `uv run ruff format --check .`.
- Imports are one per line and sorted, enforced by `uv run ruff check .`
  (`ruff` `isort` rules with `force-single-line = true`). Never write
  `from x import a, b` - write two `from x import a` / `from x import b` lines instead.
- New behavior in `src/cdforge/` needs a matching test in `tests/`.

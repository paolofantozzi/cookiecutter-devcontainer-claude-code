---
name: dependency-updater
description: Check for outdated dependencies and propose safe, incremental upgrades.
disable-model-invocation: true
---

Run `/dependency-updater` to check this project's dependencies:

1. Run `uv lock --upgrade --dry-run` (or `uv tree --outdated` if available) to see what has
   newer versions available.
2. Prefer small, incremental upgrades (patch/minor) over jumping straight to the latest
   major version. Call out any major-version bumps separately so a human can decide.
3. After upgrading, run the full test suite and the linter before proposing the change as
   a commit; do not upgrade and commit blindly.
4. Note any upgrade that changes a public API this project depends on in the commit
   message and in CHANGELOG.md.

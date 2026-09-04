---
name: commit-craftsman
description: Write higher-quality Conventional Commit messages and split mixed changes into focused commits.
---

When preparing a commit:

- Use the Conventional Commits format: `<type>(<scope>): <summary>`, with `type` one of
  `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`. Keep the summary
  under 72 characters, imperative mood, no trailing period.
- If the staged changes mix unrelated concerns (e.g. a bug fix and an unrelated
  refactor), split them into separate commits with `git add -p` rather than one mixed
  commit.
- Put the *why* in the commit body when it isn't obvious from the diff - the motivation,
  the alternative considered and rejected, or the bug being fixed - not a restatement of
  what the diff already shows.
- Never amend or rebase commits that could already be relied on elsewhere; prefer a new
  commit.

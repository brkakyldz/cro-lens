# Contributing to cro-lens

Thanks for your interest. cro-lens is young, so a short conversation in an
issue before a large change saves everyone time.

## Set up

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/). You do not need
Claude Code: the fake provider stands in for it in every test.

```bash
uv sync
uv run playwright install chromium
CRO_LENS_PROVIDER=fake uv run cro-lens ui
```

In PowerShell, set the variable first: `$env:CRO_LENS_PROVIDER = "fake"`, then
`uv run cro-lens ui`. The fake provider and the fixture pages are described in
[`docs/contracts/fake.md`](docs/contracts/fake.md).

## Make a change

1. Read [`AGENTS.md`](AGENTS.md). It holds the rules every change follows,
   including the invariants that break silently. It is written for people and
   coding agents alike.
2. Branch from `main`. One issue per pull request.
3. Tests never call a model or the internet: use the fake provider and the
   fixture pages in `tests/fixtures/pages/`.
4. If your change touches an interface, update its contract in
   `docs/contracts/`. A choice that is expensive to reverse gets an ADR in
   `docs/decisions/`.
5. A prompt change comes with a before/after live run of the same page, named
   in the pull request (there is no shared benchmark; ADR 0008).

### Acceptance scenarios

The scenarios in `tests/acceptance/holdout/` were written by an independent
author who saw the spec and the contracts but not the code. Do not edit them
in a pull request. If a scenario looks wrong, say so in the pull request or an
issue.

### Grades

A user's grades live in their own `$CRO_LENS_HOME/grades.json`, never in the
repo. Tests use a temporary `CRO_LENS_HOME`.

## Before you open a pull request

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run pyright
uv run pytest -q
CRO_LENS_REPO=. uv run pytest tests/acceptance/holdout   # a few minutes; CI runs it too
```

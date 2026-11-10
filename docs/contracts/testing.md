# testing@1 — the acceptance harness

- **Harness:** pytest ≥ 8 with `pytest-playwright` (Python, sync API, Chromium) for UI checks; the CLI is driven with `subprocess`. Python 3.12.
- **Locating the product:** env `CRO_LENS_REPO` = absolute path of the repo checkout. The CLI is invoked as `uv run --project $CRO_LENS_REPO cro-lens …` (or `$CRO_LENS_REPO/.venv/Scripts/cro-lens(.exe)` / `.venv/bin/cro-lens` when present). Fixture pages are at `$CRO_LENS_REPO/tests/fixtures/pages/` (contract `fake.md`).
- **Isolation:** every test uses its own temp `CRO_LENS_HOME` (which also holds that test's grades); `CRO_LENS_PROVIDER=fake` always. Never the internet.
- **Fixture server:** a test serves the fixture directory with `python -m http.server <free port> --bind 127.0.0.1 --directory <fixtures>` (or an equivalent in-process server) and waits until it answers.
- **UI server:** `cro-lens ui --port <free port>` as a subprocess with the env above; ready when `GET /healthz` is 200. Kill it at teardown.
- **Timeouts:** a fake-provider `analyze` on a fixture page completes in < 60 s on a normal machine; use generous auto-retrying waits, never sleeps.
- **Encoding:** set `PYTHONIOENCODING=utf-8` for subprocesses and decode output as UTF-8 (stdout contains `✓`).
- **Report:** run with `pytest --junitxml=<report path>`; scenario ids appear in test names (`test_H03_…`).

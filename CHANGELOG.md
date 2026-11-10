# Changelog

## [Unreleased]

- **A report you can read without knowing CRO.** Each finding and its test share one card: the proof from the page, what to change, suggested wording and how to measure it. Larger type, a *How to read this report* guide, a glossary, and a plain note under every section. *Check first* is a quiet amber mark instead of red, and the pipeline steps fold into one line once the report is there.
- **Your eval explains itself** and links straight to the audits that still need grading.
- **Fixed:** *Delete* now confirms with a second click on the button instead of a browser dialog, which embedded browsers can block silently.
- **Removed:** the wise example; `examples/` keeps calendly and allbirds. The README is rewritten for newcomers, with drawings of how an audit runs and how findings are checked.
- **Your own eval.** Mark each finding of a finished report **Right** or **Wrong**, with an optional note. *Your eval* (`cro-lens ui` → *Your eval*, or `cro-lens eval`) shows your precision overall and per category, and evidence validity over your audits (ADR 0008).
- **Audits learn from your grades.** A new audit shows the model up to 12 of your graded findings, the same site first, in the analysis and the self-check, and its report says how many it learned from. Turn it off per audit with `--no-feedback` or the start-page checkbox.
- **Removed:** the shipped eval set: `eval/manifest.yaml`, frozen snapshots, seeded cases, the single-prompt baseline, `RESULTS.md`, `cro-lens eval snapshot|run|report`, `cro-lens ui --eval-dir` and the labeling screen.

## [0.2.0] - 2026-11-10

- **Resume a stopped run.** Every step saves its result in the run folder. `cro-lens resume <run_id>` and the web app's **Continue** button pick up from the step that did not finish, reuse the capture already taken, and never visit the page a second time (ADR 0006).
- **Interrupted runs end.** A run whose process stopped (Ctrl-C, a closed terminal, the web app shut down) is shown as interrupted after 30 s instead of running forever, and can be resumed or deleted.
- **Delete audits in the web app**, from the list or from the audit's own page, after a confirmation. The start page lists every audit, not only the last 12.
- **Sign-in check before a run.** cro-lens checks that Claude Code is signed in before it creates a run folder or visits the page. It also catches a stale `CLAUDE_CODE_OAUTH_TOKEN` that `claude auth status` still reports as signed in. A sign-in error is no longer retried.
- The 12 held-out acceptance scenarios are in the repo and run in CI.
- Example audits of three public landing pages in `examples/`.

## [0.1.0] - 2026-11-10

First version: `cro-lens analyze`, the local web app (`cro-lens ui`), and the eval harness (`cro-lens eval snapshot|run|report`) with 15 real pages, 4 seeded-defect cases and a single-prompt baseline.

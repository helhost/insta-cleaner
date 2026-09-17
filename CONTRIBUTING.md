# Development

The Chrome extension is the main application. The Python package and tools support read-only collection, diagnostics, and protocol experiments. Keep account-specific captures and credentials out of commits.

## Setup

Use Node.js 20+ and Python 3.11+.

```sh
npm ci
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

## Check a change

```sh
npm test
python -m unittest discover -s tests -q
npm run format:check
python -m black --check instagram.py insta_cleaner tools tests
```

Apply consistent formatting with:

```sh
npm run format
python -m black instagram.py insta_cleaner tools tests
```

For the browser integration test, install Playwright’s Chromium once:

```sh
python -m playwright install chromium
python tests/extension/smoke.py
```

The smoke test uses an isolated profile and synthetic Instagram responses. It exercises scanning, date ranges, confirmation, removal responses, and the panel without changing a real account. Live checks are separate: use a small, explicit selection and inspect the result before expanding scope.

## Repository map

| Location         | Responsibility                                                  |
| ---------------- | --------------------------------------------------------------- |
| `extension/`     | Installable Chrome extension; no build step                     |
| `insta_cleaner/` | Reusable Python collection and parsing services                 |
| `instagram.py`   | Python login, Following collection, and Likes preview CLI       |
| `tools/`         | Development observers, capture readers, and bounded experiments |
| `tests/`         | Offline Python tests and extension tests                        |

See [extension architecture](extension/README.md) for the browser execution model and [tools](tools/README.md) for diagnostic commands.

## Implementation conventions

- Keep parsing and selection rules separate from browser operations and UI rendering.
- Bind scan results and confirmations to the current account and scan. Never reuse a confirmation after filters or account identity change.
- Require a complete Following traversal before treating an absent author as not followed.
- Treat malformed responses, repeated cursors, and interrupted scans as incomplete results.
- Require explicit confirmation for removal. Do not automatically retry a request whose outcome is uncertain.
- Keep user-facing messages concise. Technical identifiers and diagnostics belong in tests or development output.
- Cover behavior changes with focused tests. Prefer synthetic fixtures over raw network captures.

## Private files

`captures/`, `*.har`, `.browser-profile/`, `.local-data/`, `.auth/`, and environment files are ignored. HAR files may contain credentials and private account data. Do not turn real captures into committed fixtures; construct minimal synthetic examples instead.

`docs/` is intentionally ignored for local research notes. Publish reusable documentation in the tracked README files or this guide.

Before committing, inspect `git diff --check`, `git diff --stat`, and the staged diff. Keep functional changes separate from unrelated formatting when practical.

# Development tools

These utilities support investigation and testing. They are not required to install or run the Chrome extension.

Set up the Python environment using [the development guide](../CONTRIBUTING.md). Run commands from the repository root. Browser tools use a separate saved profile in `.browser-profile/`; output goes to `.local-data/`. Both are ignored by Git.

## Main Python CLI

```sh
python instagram.py login
python instagram.py following
python instagram.py preview --pages 1 --content reels --relationship not-followed
```

The CLI supports login and read-only collection/preview. It does not expose the extension’s bulk removal flow.

## Investigation utilities

| Tool                                    | Purpose                                                                            |
| --------------------------------------- | ---------------------------------------------------------------------------------- |
| `inspect_har.py`                        | Read a local HAR and summarize captured Likes responses without network access     |
| `observe_likes.py`                      | Observe browser activity; optionally collect Following automatically               |
| `probe_likes.py`                        | Collect a bounded number of Likes pages and optionally check a small author sample |
| `probe_months.py` / `probe_months.js`   | Compare sequential and concurrent date-range collection                            |
| `collect_following.py`                  | Collection helpers used by the observer                                            |
| `author_check.py`, `following_check.py` | Compatibility imports for parsers now in `insta_cleaner/`                          |
| `unlike_one.py`                         | Earlier single-item removal experiment; read-only unless `--execute` is supplied   |

Examples:

```sh
python tools/inspect_har.py captures/www.instagram.com.har --summary-only
python tools/probe_likes.py --pages 3 --authors 3 --headless
python tools/probe_months.py --start 2014-08-01 --headless
```

Use `--help` on executable tools for available options. These probes return observed inventories, which may be partial. The Python author-check experiments deliberately perform additional verification; they are separate from the extension’s faster inferred-author filtering.

Keep HAR files under `captures/`. Never commit captures, saved sessions, or account-specific output.

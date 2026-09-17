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

## Extension icon

The editable source is `extension/icons/icon.svg`. After changing it, regenerate the committed Chrome PNG sizes with:

```sh
python -m playwright install chromium
python tools/render_icons.py
```

The renderer uses only the local SVG and blocks network requests.

The icon gradient uses the stops and radial transforms from the [Instagram 2022 SVG reference](https://commons.wikimedia.org/wiki/File:Instagram_logo_2022.svg), applied to our own rounded square and sparkle. Its layers include `#FF005F`, `#FC01D8`, `#FFCC00`, `#FE4A05`, `#FF0F3F`, `#FE0657`, `#780CFF`, and `#820BFF`, with white foreground artwork.

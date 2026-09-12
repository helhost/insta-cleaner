# insta-cleaner

An early experiment in reviewing and eventually cleaning up your own Instagram
likes. For now, this repository only includes an offline HAR inspection tool.
It does not log in, send requests, or change your Instagram account.

## Inspect a capture

Requires Python 3.9 or newer, with no third-party dependencies.

```sh
python3 tools/inspect_har.py www.instagram.com.har
```

The reader summarizes Instagram's captured Likes requests and lists unique media
records found in their responses. It reports media IDs, post codes, and product
types, without printing request headers, cookies, tokens, or raw response bodies.
The output still describes your private activity; review it before sharing.

```sh
# Only show request and item counts
python3 tools/inspect_har.py captures/example.har --summary-only
```

HAR files are ignored wherever they are placed in this repository. You can keep
local captures in `captures/`, or leave them in the root folder. Browser session
folders are also ignored. Do not force-add these files to Git. Use synthetic data
for any future committed test fixtures.

## What the reader supports

- The Likes screen, pagination, refresh, and bulk-unlike actions captured through
  Instagram's `/async/wbloks/fetch/` endpoint.
- Media records in the observed Bloks UI-expression format, including `clips`,
  `feed`, and `carousel_container` product types.
- Plain-text and base64-encoded HAR response bodies.
- Deduplication by media ID across captured responses.

This is a parser for an observed internal format, not an official Instagram API
client. It never evaluates Bloks expressions. Format changes may cause records
to be missed. A successful HTTP response is not proof that an unlike succeeded.
Items listed across a capture may include items subsequently unliked; this is
an inventory of captured records, not your current Likes list or complete history.
Following status and reliable author identification are not implemented.

## Next steps

See [the implementation research](docs/implementation-research.md) for the project
comparison, technical options, and recommended build order.

1. Inspect the existing capture offline.
2. Capture applying the Likes author filter for one account to understand author
   identification. No additional unlikes are needed for that investigation.
3. Build a visible-browser, read-only preview before adding cleanup actions.

## First commit

If Git has not been initialized yet:

```sh
git init
```

Then review and commit only the project files:

```sh
git add .gitignore README.md tools/inspect_har.py
git diff --cached
git commit -m "Add offline Instagram HAR reader"
```

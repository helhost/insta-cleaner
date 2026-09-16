# insta-cleaner

An early experiment in reviewing and eventually cleaning up your own Instagram
likes. Includes an offline HAR reader and a browser observer for manual discovery.
Neither tool automates unliking or deletion.

## Application entry point

With dependencies installed, collect Following using your existing saved login:

```sh
python3 instagram.py following
```

This runs headlessly, requests 100 accounts per page, saves a private snapshot in
`.local-data/`, and exits. Close other collectors first because they share the
browser profile. Use `--page-size 50` to request smaller pages, or
`--channel chromium` for bundled Chromium instead of installed Chrome.
If login is needed:

```sh
python3 instagram.py login
```

The reusable application code lives in `insta_cleaner/`. `collect_following()`
returns a snapshot directly, without file handling or terminal output.
`filter_by_following()` accepts preview rows and classifies explicit authors as
followed, not-followed, or unknown. Missing/conflicting/inferred authors and
account mismatches remain unknown; incomplete lists cannot establish absence.
Identity is scoped using the session cookie, not independent server verification.
Snapshots use schema version 2; the older development exports remain unchanged.

## Read-only Likes preview

```sh
python3 instagram.py preview --pages 1 --content reels --relationship not-followed
```

This runs headlessly with your saved session: it collects a bounded Likes inventory,
checks explicit authors for every item matching the content filter, and collects
Following when a relationship filter is requested. It prints selected post links
and saves a private `.local-data/likes-preview-*.json` report. Nothing is removed.
Start with one page; author checks navigate to each matching post and can take time.

- `--pages`: maximum Likes pages, 1–20; default 3. Every preview remains labelled
  partial because full-history termination is not yet verified.
- `--content`: `all`, `reels`, or `posts` (including carousels); default `all`.
- `--relationship`: `all`, `followed`, `not-followed`, or `unknown`; default `all`.
  `all` skips Following collection.

Unknown or inferred authors are never counted as not-followed. An incomplete
Following list also makes absent authors unknown. Reports include separate
`selected` and `unknown` lists; these overlap when explicitly previewing unknown
items or selecting all relationships. Content outside the chosen filter is omitted.
The report records the session account ID, filter settings, and collection status.
Author usernames are included when available from Following, so an unfollowed
post may show only its author's numeric ID.

```sh
python3 instagram.py preview --pages 1 --content posts --relationship followed
python3 instagram.py preview --pages 1 --content reels --relationship unknown
```

The reusable implementation is in `insta_cleaner/likes.py`, `media.py`, and
`preview.py`. Development commands remain available below. Full-history
collection and all removal actions remain unimplemented.

## Development: limited Likes pagination probe

```sh
python3 tools/probe_likes.py --pages 3
```

Close other collectors first. The probe opens **Your activity → Likes** automatically
using the saved session, loads the remaining pages, and saves a partial
inventory in `.local-data/likes-probe-*.json`, and closes the browser. Keep filters
unchanged and avoid removals during the run. The page limit is 1–5, default 3.

To check explicit authors for a small sample after pagination:

```sh
python3 tools/probe_likes.py --pages 3 --authors 3 --headless
```

This runs without a window and opens three collected posts automatically. Author
checks stop waiting as soon as explicit metadata for the exact item arrives; otherwise
they wait up to eight seconds after navigation and document inspection. Navigation
has its own 30-second timeout. Unresolved authors retain their existing evidence.
Run `python3 instagram.py login` if the saved session needs renewing. For visible
troubleshooting, omit `--headless`; add `--manual` to navigate to Likes yourself.
`--manual` and `--headless` cannot be combined. It does not remove anything.

The probe uses live request credentials held in memory, never credentials from
HAR files. It parses only the observed `liked_next` instruction and never executes
server UI expressions. Saved rows contain media IDs, post codes, product types,
and author evidence. Suffix-only authors remain inferred. Missing continuation
instructions are not treated as proof that the full history is complete. Explicit
author lookup is available through `--authors`; full-history collection remains a later experiment.

## Observe Likes in a browser

Use Python 3.9 or newer. From the repository directory, install the browser
dependency in a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 tools/observe_likes.py
```

On Windows, activate with `.venv\Scripts\activate` instead. If Google Chrome is
already installed, you can skip the Chromium installation and run:

```sh
python3 tools/observe_likes.py --channel chrome
```

1. Log into Instagram yourself in the new browser window, including any 2FA.
2. Open **Your activity → Likes**.
3. Wait for a Likes batch in the terminal, then open one of those posts normally
   (leave Select mode off). Opening it in another tab in the same observer browser works too.
4. Watch for **Author check ... MATCH**, **MISMATCH**, or **CONFLICT**.
5. Try a few posts from different authors. If no check appears, refresh the opened
   post once. Close the browser or press **Ctrl+C** to finish.

The observer matches post metadata to a captured like by both media ID and post
code. It compares an explicit `owner`/`user` ID with the liked-item ID suffix.
A match validates that observed item only. Conflicting metadata remains unverified.
It does not verify following status, the signed-in account identity, or all history.
No Authors filter is required: the desktop layout tested only offers sorting and dates.

The script opens Instagram and passively observes recognized Likes reads and supported post-detail
responses while a post is open.
It does not click buttons, submit credentials, replay requests, or save HARs.
Your manual browser actions still work normally; avoid deleting anything during
this experiment. If login is challenged, complete Instagram's normal flow or stop.

The dedicated session lives in the ignored `.browser-profile/` directory, so you
usually do not need to log in again. Browser storage can contain private data;
never commit that directory. The terminal summary contains counts rather than
raw responses, cookies, usernames, or media IDs. No summary file is written.

If no batches appear, reopen Likes or refresh that page. If no author check appears,
Instagram may have reused cached metadata, the page URL may not identify the post,
or the response may use an unsupported format. Refresh the opened post once; do
not interpret silence as a match. Metadata is kept in memory until you stop.
The observer also checks embedded JSON in post documents and API responses that
arrive before the address bar changes. If a post response remains unsupported,
`Post diagnostic` lines report structural counts only (no raw payload or IDs).
Share those lines to help diagnose the missing format.
It also handles Instagram navigation responses: each route's concrete shortcode
is joined to that route's explicit media and owner IDs. This format was validated
against one locally captured liked post; broader account coverage is untested.

## Collect the Following list

```sh
python3 tools/observe_likes.py --channel chrome --collect-following
```

For automatic navigation with an existing saved login:

```sh
python3 tools/observe_likes.py --channel chrome --auto-open-following
```

To run without showing a browser window and exit automatically after saving:

```sh
python3 tools/observe_likes.py --channel chrome --auto-open-following --page-size 100 --headless
```

Close any earlier collector before starting, since they share the saved browser
profile. Headless mode requires a saved login. If it expires or Instagram asks
for verification, rerun without `--headless` to complete login.

This reads the account ID from the saved Instagram session and requests that
account's Following list directly. It does not depend on Profile buttons, language,
or scrolling. If no session is available, it waits up to two minutes for you to
log in, then starts automatically. Login challenges are not automated. Cookies
are used locally and are not included in the export. The browser stays open afterward.
All pages, including the first, use the requested page size in this mode.
Remaining pages request 50 accounts by default; use `--page-size 100` to try larger
pages. Instagram may return fewer. Pages load sequentially because each response
provides the next cursor. Larger pages have not yet been verified against a live
session. A profile-count mismatch remains incomplete even at the final page.

Log in manually, open your own profile, and click **Following** once. Leave the
browser open; no scrolling is needed. The collector requests remaining pages
using the same browser session, with a pause between requests. It stops at the
end, a failed/restricted page, repeated pagination, or three pages with no new
accounts. It does not follow, unfollow, or remove anything.

The result is saved automatically in `.local-data/following-<timestamp>.json`
(ignored by Git). This reusable snapshot contains account IDs, usernames, list
owner ID, collection time, and completeness diagnostics. Interrupted collections
also save partial results. Keep incomplete snapshots out of “not following”
filters. Without `--collect-following`, collection remains passive and in memory.

An uninterrupted cursor chain must end with explicit `has_more: false`, no next
cursor, no indicated restrictions/hidden accounts, and no parsing failures. If a
profile count is available it must also match. Otherwise the list remains incomplete.
The final-page format has been checked against the full Following capture.
A terminal page alone does not resolve a mismatch with the observed profile count.

Lists from different profiles are kept separate. List ownership is not yet verified
against the authenticated session, and this step does not enable not-following
filters. Restart the observer for a fresh snapshot if a page fails or changes.

## Preview collected likes

```sh
python3 tools/observe_likes.py --channel chrome --preview
```

Load Likes and open a few posts to collect author evidence. Close the observer
browser (or press Ctrl+C) to print a deduplicated preview with content type, author
ID, evidence status, and a post link. Nothing is saved or removed. The preview
contains private activity, so review it before sharing terminal output.

`matched` means explicit owner metadata agrees with the suffix for that item;
`inferred` means only the suffix is available. `mismatched` displays the explicit
owner rather than the suffix. `conflicting` leaves the author unknown. This does
not verify usernames, following status, or complete/current history.

To filter a subsequent preview, use an author ID from the first preview:

```sh
python3 tools/observe_likes.py --channel chrome --author-id 123456
```

Replace `123456` with the desired ID. This filters the terminal preview, not
Instagram's page. Inferred matches are included and labeled; conflicting identities
are excluded. Each run collects fresh observations in memory.

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
The application preview can classify explicitly resolved authors using Following. Unresolved authors remain unknown; removal actions are not implemented.

## Next steps

1. Inspect the existing capture offline.
2. Open captured liked posts and validate their candidate author-ID mapping.
3. Add verified author metadata and a read-only preview before cleanup actions.

## Tests

These use synthetic responses and do not require Playwright or an account:

```sh
python3 -m unittest discover -s tests -v
```

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

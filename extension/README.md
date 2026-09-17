# Extension architecture

Load this directory directly in Chrome. There is no bundler, server, or runtime dependency. The manifest declares the scripts and their execution contexts.

## Data flow

1. The side panel sends filters to the background worker.
2. The worker binds a scan to the active Instagram account and loads Following only when the selected relationship needs it.
3. The page hook observes the initial Likes request and uses its request context to collect subsequent pages. Date-bounded scans distribute independent ranges across a bounded worker queue.
4. The bridge forwards parsed results to the background worker, which deduplicates them and updates session storage. The panel renders counts and progress.
5. The panel requests a confirmation for a fixed set of matches. After confirmation, the worker sends a privileged unlike request using the captured Instagram request context.

## Modules

| Module                                | Responsibility                                                                          |
| ------------------------------------- | --------------------------------------------------------------------------------------- |
| `background.js`                       | Account identity, scan lifecycle, session state, confirmation and removal orchestration |
| `page-hook.js`                        | Observe Likes requests and collect pages in the Instagram page context                  |
| `bridge.js`                           | Relay scan events between the page and extension; acknowledge delivery                  |
| `parser.js`                           | Parse supported response shapes and pagination instructions                             |
| `dates.js`, `queue.js`                | Validate date ranges, build filtered requests, and schedule bounded concurrent work     |
| `following.js`, `workflow.js`         | Following traversal, content and relationship matching, selection validation            |
| `batch.js`                            | Validate and send the unlike request; interpret its acknowledgement                     |
| `panel.js`, `panel.html`, `panel.css` | User-facing filters, confirmation, progress and result states                           |
| `calendar.js`                         | Custom calendar selection and keyboard interaction                                      |

## Behavioral boundaries

Each pagination chain is sequential because the next cursor comes from the preceding response. Independent date ranges can run concurrently; overlapping results are deduplicated by media ID. Page limits or unsupported responses produce partial results.

Progress reflects completed date ranges, not elapsed time or a guaranteed time estimate. Open-ended scans use indeterminate progress.

Author IDs are taken from the captured media ID suffix. The extension does not open each post to verify its author. Negative relationship matching requires a complete Following snapshot for the same account.

Removal is bound to a fixed confirmation, account, and scan. The current implementation sends the confirmed eligible IDs in one unlike request. It checks Instagram’s success acknowledgement and reported count; HTTP success alone is insufficient. Uncertain results stop the run and are not automatically retried.

The page-message bridge accepts scan events only. Removal is initiated through the extension’s confirmation flow, not a page-message command.

## State and permissions

Scan data lives in extension session storage. Instagram cookies are used to identify the signed-in account, and requests use the existing browser session. Host access is restricted to `https://www.instagram.com/*`; there is no external project service.

After an extension reload, refresh the Instagram tab so its content scripts belong to the new extension instance.

See [the development guide](../CONTRIBUTING.md) for tests and formatting.

#!/usr/bin/env python3
"""Observe Likes responses while you navigate Instagram manually."""

import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlsplit

from inspect_har import PREFIX, response_records
from author_check import AuthorTracker, inspect_metadata, metadata_endpoint, post_code
from following_check import FollowingTracker, following_request
from collect_following import collect, collect_signed_in


READ_ACTIONS = {"liked_media_screen", "liked_next", "liked_refresh"}
PROFILE = Path(__file__).resolve().parents[1] / ".browser-profile"


def activity_action(url):
    """Accept only known Likes reads on Instagram itself."""
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in {"instagram.com", "www.instagram.com"}:
            return None
        if parts.path != "/async/wbloks/fetch/":
            return None
        app = dict(parse_qsl(parts.query)).get("appid", "")
        action = app[len(PREFIX):] if app.startswith(PREFIX) else ""
        return action if action in READ_ACTIONS else None
    except ValueError:
        return None


def selected_authors(post_data):
    """Return filter state and IDs, without guessing IDs from arbitrary text.

    Supported shapes are numeric IDs, comma-separated IDs, and JSON lists of IDs.
    This is a request-filter comparison, not independent profile verification.
    """
    try:
        params = json.loads(dict(parse_qsl(post_data or "")).get("params", "{}"))
        if not isinstance(params, dict):
            return "unknown", set()
        nested = params.get("activity_center_params", params)
        if isinstance(nested, str):
            nested = json.loads(nested)
        if not isinstance(nested, dict) or "main_authors_state_value" not in nested:
            return "unknown", set()
        value = nested["main_authors_state_value"]
        if value == "" or value == []:
            return "unfiltered", set()
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                value = json.loads(value)
            else:
                value = value.split(",")
        if type(value) is int:
            value = [value]
        if not isinstance(value, list) or not value:
            return "unknown", set()
        ids = set()
        for item in value:
            if type(item) not in (str, int):
                return "unknown", set()
            candidate = str(item).strip()
            if not re.fullmatch(r"[1-9][0-9]*", candidate):
                return "unknown", set()
            ids.add(candidate)
        return "filtered", ids
    except (ValueError, TypeError):
        return "unknown", set()


def summarize(action, filter_state, author_ids, status, body):
    """Summarize one response using its own request's filter context."""
    result = {"action": action, "filter": filter_state, "items": 0, "comparison": "not_checked"}
    if status != 200:
        result["note"] = "Non-success response; no author comparison performed."
        return result
    try:
        records, warning = response_records({"response": {"content": {"text": body}}})
    except (ValueError, KeyError, TypeError, AttributeError):
        result["note"] = "Unsupported response format; no raw data printed."
        return result
    result["items"] = len(records)
    result["products"] = dict(Counter(record[1] for record in records.values()))
    if warning:
        result["note"] = "No supported media records found; this does not mean the history is empty."
        return result
    candidates = [media_id.split("_", 1)[1] for media_id in records]
    result["candidate_authors"] = len(set(candidates))
    if filter_state == "filtered":
        matches = sum(candidate in author_ids for candidate in candidates)
        result["matching_items"] = matches
        result["selected_authors"] = len(author_ids)
        result["comparison"] = "consistent" if matches == len(records) else "mismatch"
    elif filter_state == "unknown":
        result["note"] = "Open a liked post normally to observe its author metadata."
    return result


class Reporter:
    def __init__(self):
        self.batches = 0
        self.comparisons = Counter()

    def show(self, result):
        self.batches += 1
        self.comparisons[result["comparison"]] += 1
        print(f"\nBatch {self.batches}: {result['action']} — {result['items']} items", flush=True)
        if result.get("products"):
            print("  Types: " + ", ".join(f"{k}: {v}" for k, v in sorted(result["products"].items())))
        if result["comparison"] in {"consistent", "mismatch"}:
            print(f"  Author filter: {result['selected_authors']} selected ID(s).")
            print(f"  Candidate author IDs matching that filter: {result['matching_items']}/{result['items']}.")
            print("  " + ("Consistent with the ID-suffix hypothesis; not independently verified."
                           if result["comparison"] == "consistent" else
                           "MISMATCH: do not rely on ID suffixes for author filtering yet."))
        elif result["filter"] == "unfiltered":
            print("  Open a liked post normally to check its author; no author filter is needed.")
        if "note" in result:
            print("  " + result["note"])
        sys.stdout.flush()

    def finish(self):
        print(f"\nObserved {self.batches} Likes response batches (items may overlap).")
        print(f"Filter comparisons: {self.comparisons['consistent']} consistent, "
              f"{self.comparisons['mismatch']} mismatched.")
        if not self.comparisons['consistent'] and not self.comparisons['mismatch']:
            print("No request-filter comparison completed; see the post author checks below.")
        print("This does not verify following status, account identity, or complete history.")


def show_preview(tracker, author_id=None):
    rows = tracker.preview(author_id)
    print(f"\nREAD-ONLY PREVIEW: {len(rows)} of {len(tracker.likes)} unique captured items.")
    if author_id:
        print("Author-ID filter applied; inferred matches included, ambiguous identities excluded.")
    print("#    CONTENT               AUTHOR ID             EVIDENCE       POST")
    for row in rows:
        content = {"clips": "reel", "feed": "feed post", "carousel_container": "carousel"}.get(row['product'], 'unknown')
        print(f"{row['index']:<4} {content:<21} {row['author_id'] or 'unknown':<21} "
              f"{row['evidence']:<14} https://www.instagram.com/p/{row['code']}/")
    print("matched = explicit owner agrees; inferred = ID suffix only; "
          "mismatched = explicit owner differs; conflicting = ambiguous.")
    print("For mismatched items, AUTHOR ID shows the explicit owner, not the suffix.")
    print("Private activity: review before sharing. Nothing selected or removed; history may be incomplete or stale.")


async def close_context(context):
    """Closing a window can disconnect the driver before cleanup completes."""
    try:
        await context.close()
    except Exception as error:
        # Playwright can surface this shutdown race as a plain Exception.
        # Suppress only known closed-connection outcomes, not arbitrary failures.
        message = str(error)
        if not any(reason in message for reason in (
            "Connection closed while reading from the driver",
            "Target page, context or browser has been closed",
        )):
            raise


async def observe(channel=None, preview=False, author_id=None, auto_following=False, page_size=50, auto_open=False, headless=False):
    # Lazy import keeps --help and parser tests usable without browser dependencies.
    try:
        from playwright.async_api import async_playwright, Error as BrowserError
    except ImportError:
        print("Install the browser dependency: python3 -m pip install -r requirements.txt", file=sys.stderr)
        return 2

    reporter = Reporter()
    tracker = AuthorTracker()
    following = FollowingTracker()
    collection_started = False

    def show_checks(changes):
        for index, state in changes:
            messages = {
                "matched": "MATCH: explicit post author ID agrees with the captured ID suffix.",
                "mismatched": "MISMATCH: explicit author differs; do not use the suffix for filtering.",
                "conflicting": "CONFLICT: multiple author IDs observed; this item remains unverified.",
            }
            print(f"Author check for captured item #{index}: {messages[state]}", flush=True)
    tasks = set()
    context = None
    try:
        PROFILE.mkdir(mode=0o700, parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(PROFILE), headless=headless, channel=channel,
                chromium_sandbox=True,
                accept_downloads=False,
            )
            closed = asyncio.Event()
            context.on("close", lambda *_: closed.set())

            async def handle(response, action, state, authors, code):
                nonlocal collection_started
                try:
                    body = await response.text() if response.status == 200 else ""
                    follow_request = following_request(response.url)
                    if follow_request:
                        following.add(follow_request, response.status, body)
                        following.show(follow_request[0])
                        if auto_following and not auto_open and not collection_started and not follow_request[1] and follow_request[2]:
                            collection_started = True
                            job = asyncio.create_task(collect(context, response, following, page_size))
                            tasks.add(job)
                            job.add_done_callback(tasks.discard)
                        return
                    if response.status == 200:
                        for account in following.profile_counts(body):
                            following.show(account)
                    if action:
                        reporter.show(summarize(action, state, authors, response.status, body))
                        if response.status == 200:
                            try:
                                records, _ = response_records({"response": {"content": {"text": body}}})
                                show_checks(tracker.add_likes(records))
                            except (ValueError, KeyError, TypeError, AttributeError):
                                pass
                    else:
                        try:
                            rows, diagnostic = inspect_metadata(body) if response.status == 200 else ([], {})
                            # Match by the actual media identity, not the page URL at event time.
                            # Instagram may prefetch before updating the address bar.
                            rows = [row for row in rows if (row[0], row[1]) in tracker.likes or row[1] == code]
                            show_checks(tracker.add_details(rows))
                            if not rows and code:
                                counts = ", ".join(f"{key}={value}" for key, value in diagnostic.items())
                                print(f"Post diagnostic: HTTP {response.status}; {counts or 'body not inspected'}.", flush=True)
                            elif rows and not any((pk, item_code) in tracker.likes for pk, item_code, _ in rows):
                                print("Post metadata observed; first load this item in Likes to compare it.", flush=True)
                        except (ValueError, TypeError, AttributeError):
                            print("Post response format unsupported; no raw data printed.", flush=True)
                except BrowserError:
                    follow_request = following_request(response.url)
                    if follow_request:
                        following.add(follow_request, 0, '')
                        following.show(follow_request[0])
                    print("A response could not be read, possibly because the page closed.")

            def on_response(response):
                action = activity_action(response.url)
                is_document = response.request.resource_type == "document"
                code = post_code(response.url) if is_document else None
                is_metadata = metadata_endpoint(response.url)
                if action is None and is_metadata:
                    try:
                        code = post_code(response.request.frame.page.url)
                    except BrowserError:
                        return
                if action is None and not (is_metadata or (is_document and code) or following_request(response.url)):
                    return
                state, authors = selected_authors(response.request.post_data)
                task = asyncio.create_task(handle(response, action, state, authors, code))
                tasks.add(task)
                task.add_done_callback(tasks.discard)

            context.on("response", on_response)
            if auto_following:
                print('Following collector ready. Using the saved browser session.')
                print('Loading your Following list directly.' if auto_open else 'Open your own profile → Following once. No scrolling needed.')
                print('Saves account IDs and usernames locally. Removes nothing.')
            else:
                print('Browser observer ready. Log in manually, then open Your activity → Likes.')
                print('To collect Following manually: open your own profile → Following and scroll inside the list.')
                print('Wait for a Likes batch, then open ONE liked post normally (not in Select mode).')
                print('Wait for an Author check. Try another post or refresh the opened post if none appears.')
                print('The observer does not click, replay requests, or remove anything.')
            if preview:
                print("A preview with author IDs and post links will appear when you close the browser.")
            if headless:
                print('Running without a browser window; exits after saving the snapshot.', flush=True)
            else:
                print('Your own browser clicks still work normally. Avoid deletion during this experiment.')
                print('Close all observer browser windows or press Ctrl+C here to finish.', flush=True)
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            except BrowserError:
                print("Initial navigation did not finish. You can open Instagram manually in this window.")
            if auto_open:
                try:
                    await collect_signed_in(context, following, page_size, wait_for_login=not headless)
                except BrowserError:
                    print('Could not load Following directly. Check the browser for a login challenge, then rerun.')
            if headless:
                await close_context(context)
            try:
                await closed.wait()
            finally:
                context.remove_listener("response", on_response)
                for task in list(tasks):
                    task.cancel()
                await asyncio.gather(*list(tasks), return_exceptions=True)
                if not closed.is_set():
                    await close_context(context)
    except (BrowserError, OSError):
        print("Could not run the browser. Install Chromium with 'python3 -m playwright install chromium', "
              "or use '--channel chrome' for installed Chrome. Close other observer instances first.", file=sys.stderr)
        return 2
    finally:
        reporter.finish()
        counts = Counter(tracker.reported.values())
        print(f"Post author checks: {counts['matched']} matched, {counts['mismatched']} mismatched, "
              f"{counts['conflicting']} conflicting; {len(tracker.likes) - len(tracker.reported)} unchecked items.")
        print("Matches validate only the observed items, not following status or other posts.")
        for account in following.accounts:
            following.show(account)
        if preview:
            show_preview(tracker, author_id)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", choices=["chrome"], help="Use installed Google Chrome instead of bundled Chromium")
    parser.add_argument("--preview", action="store_true", help="Print captured items, author IDs, and post links when stopping")
    parser.add_argument('--collect-following', action='store_true', help='Automatically fetch remaining Following pages and export usernames locally after you open the list')
    parser.add_argument("--author-id", help="Filter the preview to a numeric author ID (includes inferred matches)")
    parser.add_argument('--page-size', type=int, default=50, help='Requested accounts per page (default 50; Instagram may return fewer)')
    parser.add_argument('--auto-open-following', action='store_true', help='Fetch the saved session account’s Following list directly; implies --collect-following')
    parser.add_argument('--headless', action='store_true', help='Hide the browser and exit after collection; requires --auto-open-following and a saved login')
    args = parser.parse_args()
    if args.headless and not args.auto_open_following:
        parser.error('--headless requires --auto-open-following')
    if not 1 <= args.page_size <= 200:
        parser.error('--page-size must be between 1 and 200')
    if args.author_id and not re.fullmatch(r"[1-9][0-9]*", args.author_id):
        parser.error("--author-id must be a positive numeric account ID")
    try:
        return asyncio.run(observe(args.channel, args.preview or args.author_id is not None, args.author_id, args.collect_following or args.auto_open_following, args.page_size, args.auto_open_following, args.headless))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())

"""Paginate the observed following endpoint in the same local browser session."""

import asyncio
from datetime import datetime, timezone
import json
import re
from types import SimpleNamespace
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Support both direct execution and package imports.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.following_check import following_request

OUTPUT = Path(__file__).resolve().parents[1] / ".local-data"


def export_snapshot(tracker, account):
    state = tracker.accounts[account]
    users = {}
    for records, *_ in state["pages"].values():
        users.update(records)
    now = datetime.now(timezone.utc)
    result = {
        "schema_version": 1,
        "observed_at": now.isoformat(),
        "list_owner_id": account,
        "session_identity_verified": False,
        **tracker.summary(account),
        "accounts": [
            {"id": pk, "username": name} for pk, name in sorted(users.items())
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = OUTPUT / ("following-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with path.open("x", encoding="utf-8") as file:
        path.chmod(0o600)
        json.dump(result, file, indent=2)
        file.write("\n")
    return path


async def collect(context, seed_response, tracker, page_size=50):
    request = following_request(seed_response.url)
    if not request or not request[2] or request[1]:
        print("Automatic collection needs the unfiltered first page. Reopen Following.")
        return
    account = request[0]
    url = urlsplit(seed_response.url)
    params = dict(parse_qsl(url.query))
    params["count"] = str(page_size)
    seen = set()
    print(
        "Automatically collecting Following pages. No follow/unfollow actions will be sent.",
        flush=True,
    )
    try:
        raw_headers = await seed_response.request.all_headers()
        headers = {
            k: v
            for k, v in raw_headers.items()
            if k.lower()
            in {"x-ig-app-id", "x-asbd-id", "x-csrftoken", "x-requested-with", "accept"}
        }
        stalled = 0
        for _ in range(1000):
            state = tracker.accounts[account]
            if state["failed"]:
                print(
                    "Automatic collection stopped: snapshot has a failed or changed page."
                )
                break
            cursor = ""
            traversed = set()
            while cursor in state["pages"] and cursor not in traversed:
                traversed.add(cursor)
                records, next_cursor, more, unrestricted = state["pages"][cursor]
                if not unrestricted or not more:
                    break
                cursor = next_cursor
            if cursor in state["pages"]:
                if not unrestricted:
                    print(
                        "Automatic collection stopped: Instagram marked this list restricted."
                    )
                elif not more:
                    print(
                        "Automatic collection finished: Instagram returned its final page."
                    )
                    summary = tracker.summary(account)
                    if (
                        summary["expected"] is not None
                        and summary["users"] != summary["expected"]
                    ):
                        print(
                            "The returned list differs from the profile count; keeping the snapshot incomplete."
                        )
                else:
                    print(
                        "Automatic collection stopped: Instagram repeated a pagination cursor."
                    )
                break
            if cursor in seen:
                break
            seen.add(cursor)
            params["max_id"] = cursor
            next_url = urlunsplit(
                (url.scheme, url.netloc, url.path, urlencode(params), "")
            )
            await asyncio.sleep(1.5)
            before = tracker.summary(account)["users"]
            response = await context.request.get(
                next_url, headers=headers, timeout=30000, max_redirects=0
            )
            try:
                body = await response.text() if response.status == 200 else ""
                tracker.add(following_request(next_url), response.status, body)
            finally:
                await response.dispose()
            tracker.show(account)
            stalled = stalled + 1 if tracker.summary(account)["users"] == before else 0
            if stalled >= 3:
                print(
                    "Automatic collection stopped after three pages with no new accounts."
                )
                break
        else:
            print(
                "Automatic collection stopped at the page limit; snapshot may be incomplete."
            )
    except asyncio.CancelledError:
        print("Automatic collection interrupted; exporting the partial snapshot.")
        raise
    except Exception:
        tracker.add((account, "__failed_request__", True), 0, "")
        print(
            "Automatic collection stopped after a request error. No response details printed."
        )
    finally:
        path = export_snapshot(tracker, account)
        print(f"Following snapshot saved: {path}", flush=True)
        tracker.show(account)


async def collect_signed_in(context, tracker, page_size=50, wait_for_login=True):
    """Start from the session's account ID, without depending on UI labels."""
    account = None
    csrf = None
    for _ in range(120 if wait_for_login else 1):
        cookies = await context.cookies("https://www.instagram.com/")
        ids = {
            c["value"]
            for c in cookies
            if c["name"] == "ds_user_id" and re.fullmatch(r"[1-9][0-9]*", c["value"])
        }
        session = any(c["name"] == "sessionid" and c["value"] for c in cookies)
        if len(ids) == 1 and session:
            account = ids.pop()
            csrf = next((c["value"] for c in cookies if c["name"] == "csrftoken"), None)
            break
        if not wait_for_login:
            print("No saved login available. Rerun without --headless to log in.")
            return
        if _ == 0:
            print(
                "Waiting for login. Once you log in, Following collection starts automatically.",
                flush=True,
            )
        await asyncio.sleep(1)
    if account is None:
        print(
            "No signed-in session found after two minutes. Log in and rerun this command."
        )
        return
    # Public web application ID observed in the local Following capture.
    headers = {"x-ig-app-id": "936619743392459", "accept": "application/json"}
    if csrf:
        headers["x-csrftoken"] = csrf
    url = f"https://www.instagram.com/api/v1/friendships/{account}/following/?count={page_size}"
    print(
        "Loading Following directly for the saved session account. No navigation or scrolling needed.",
        flush=True,
    )
    response = await context.request.get(
        url, headers=headers, timeout=30000, max_redirects=0
    )
    try:
        body = await response.text() if response.status == 200 else ""
        tracker.add(following_request(url), response.status, body)
    finally:
        await response.dispose()

    async def all_headers():
        return headers

    seed = SimpleNamespace(url=url, request=SimpleNamespace(all_headers=all_headers))
    await collect(context, seed, tracker, page_size)

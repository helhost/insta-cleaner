"""Read-only following collection, independent of the CLI and snapshot storage."""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from .following_parser import FollowingTracker

WEB_APP_ID = "936619743392459"  # Observed Instagram web client ID.


class LoginRequired(Exception):
    pass


@dataclass
class FollowingSnapshot:
    list_owner_id: str
    observed_at: str
    accounts: dict[str, str]
    complete: bool
    pages: int
    stop_reason: str
    identity_source: str = "session_cookie"
    schema_version: int = 2

    def membership(self, author_id, *, account_id):
        """Unknown covers missing authors, another account, and incomplete absence."""
        if account_id != self.list_owner_id or not author_id:
            return "unknown"
        if str(author_id) in self.accounts:
            return "followed"
        return "not-followed" if self.complete else "unknown"

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = directory / f"following-{stamp}.json"
        with path.open("x", encoding="utf-8") as file:
            path.chmod(0o600)
            json.dump(asdict(self), file, indent=2)
            file.write("\n")
        return path


async def session_identity(context):
    cookies = await context.cookies("https://www.instagram.com/")
    ids = {
        c["value"]
        for c in cookies
        if c["name"] == "ds_user_id" and re.fullmatch(r"[1-9][0-9]*", c["value"])
    }
    if len(ids) != 1 or not any(
        c["name"] == "sessionid" and c["value"] for c in cookies
    ):
        raise LoginRequired("No saved login. Run: python3 instagram.py login")
    csrf = next((c["value"] for c in cookies if c["name"] == "csrftoken"), None)
    return ids.pop(), csrf


async def collect_following(context, *, page_size=100, delay=1.5, progress=None):
    """Return session-scoped data for filtering; make no writes or UI clicks.

    Identity comes from the session cookie, not independent account verification.
    Cursors are sequential; failures return partial data without retrying.
    """
    if not 1 <= page_size <= 200 or delay < 0:
        raise ValueError("Invalid page size or delay")
    account, csrf = await session_identity(context)
    tracker = FollowingTracker()
    users = {}
    cursor = ""
    seen = set()
    stalled = 0
    complete = False
    reason = "page limit reached"
    headers = {"x-ig-app-id": WEB_APP_ID, "accept": "application/json"}
    if csrf:
        headers["x-csrftoken"] = csrf
    for page in range(1000):
        if page:
            await asyncio.sleep(delay)
        current_account, _ = await session_identity(context)
        if current_account != account:
            reason = "session account changed"
            break
        query = {"count": page_size}
        if cursor:
            query["max_id"] = cursor
        url = f"https://www.instagram.com/api/v1/friendships/{account}/following/?{urlencode(query)}"
        try:
            response = await context.request.get(
                url, headers=headers, timeout=30000, max_redirects=0
            )
            try:
                body = await response.text() if response.status == 200 else ""
                result = tracker.add((account, cursor, True), response.status, body)
            finally:
                await response.dispose()
        except asyncio.CancelledError:
            raise
        except Exception:
            reason = "request failed"
            break
        if result["failed"]:
            reason = "; ".join(result["reasons"])
            break
        records, next_cursor, more, unrestricted = tracker.accounts[account]["pages"][
            cursor
        ]
        before = len(users)
        users.update(records)
        if progress:
            progress(len(users), result["pages"])
        if not unrestricted:
            reason = "list restricted by Instagram"
            break
        if not more:
            complete = result["complete"]
            reason = "final page reached"
            break
        seen.add(cursor)
        if next_cursor in seen:
            reason = "repeated pagination cursor"
            break
        stalled = stalled + 1 if len(users) == before else 0
        if stalled >= 3:
            reason = "no new accounts in three pages"
            break
        cursor = next_cursor
    pages = len(tracker.accounts.get(account, {}).get("pages", {}))
    return FollowingSnapshot(
        account, datetime.now(timezone.utc).isoformat(), users, complete, pages, reason
    )


def filter_by_following(items, snapshot, *, account_id, relationship):
    """Filter preview rows using explicit author evidence; never mutate activity."""
    if relationship not in {"followed", "not-followed", "unknown"}:
        raise ValueError("Unsupported relationship")
    return [
        item
        for item in items
        if (
            snapshot.membership(item.get("author_id"), account_id=account_id)
            if item.get("evidence") in {"matched", "mismatched"}
            else "unknown"
        )
        == relationship
    ]

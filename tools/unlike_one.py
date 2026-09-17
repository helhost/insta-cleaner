"""Single-reel unlike experiment. Defaults to checking only; no automatic retries."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from insta_cleaner.authors import AuthorTracker, post_code
from insta_cleaner.following import collect_following, session_identity
from insta_cleaner.likes import check_authors

ROOT = Path(__file__).resolve().parents[1]


def selected_item(report, code):
    rows = [item for item in report.get("selected", []) if item.get("code") == code]
    if len(rows) != 1:
        raise ValueError("Choose exactly one item from the preview selection.")
    item = rows[0]
    if (
        item.get("product") != "clips"
        or item.get("relationship") != "not-followed"
        or item.get("evidence") not in {"matched", "mismatched"}
        or not re.fullmatch(r"[1-9][0-9]*", str(item.get("media_id", "")))
        or not re.fullmatch(r"[1-9][0-9]*", str(item.get("author_id", "")))
    ):
        raise ValueError(
            "This experiment requires a reel with an explicit, not-followed author."
        )
    return item


def require_same_account(expected, actual):
    if not expected or expected != actual:
        raise ValueError("The signed-in account differs from the preview account.")


async def post_actions(page):
    # The nearest section around the post's Comment action excludes comment hearts.
    comment = page.locator('svg[aria-label="Comment"]')
    await comment.first.wait_for(state="visible", timeout=20000)
    if await comment.count() != 1:
        raise ValueError("Post action controls are ambiguous; stopping.")
    return comment.locator("xpath=ancestor::section[1]")


async def click_and_verify(page, unlike, like, code):
    await unlike.click(timeout=10000)
    await like.wait_for(state="visible", timeout=15000)
    await page.reload(wait_until="domcontentloaded", timeout=30000)
    if post_code(page.url) != code:
        raise ValueError("Verification navigated away from the selected post.")
    actions = await post_actions(page)
    await actions.locator('svg[aria-label="Like"]').wait_for(
        state="visible", timeout=15000
    )
    if await actions.locator('svg[aria-label="Unlike"]').count() != 0:
        raise ValueError("Reloaded post has an ambiguous liked state.")


async def run(args):
    from playwright.async_api import async_playwright

    report = json.loads(args.preview.read_text())
    item = selected_item(report, args.code)
    expected = report.get("account_id")
    journal = {
        "code": args.code,
        "media_id": item["media_id"],
        "account_id": expected,
        "execute": args.execute,
        "status": "checking",
        "click_attempted": False,
    }
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                str(ROOT / ".browser-profile"),
                channel="chrome",
                headless=True,
                chromium_sandbox=True,
            )
            try:
                require_same_account(expected, (await session_identity(context))[0])
                print(
                    "Refreshing Following and author evidence for the single selected reel…",
                    flush=True,
                )
                following = await collect_following(context)
                require_same_account(expected, following.list_owner_id)
                if (
                    following.membership(item["author_id"], account_id=expected)
                    != "not-followed"
                ):
                    raise ValueError(
                        "Fresh Following data does not establish that this author is not followed."
                    )
                tracker = AuthorTracker()
                tracker.add_likes(
                    {
                        f"{item['media_id']}_{item['author_id']}": (
                            args.code,
                            "clips",
                            "2",
                        )
                    }
                )
                await check_authors(context, tracker, 1)
                fresh = tracker.preview()[0]
                if (
                    fresh["evidence"] != "matched"
                    or fresh["author_id"] != item["author_id"]
                ):
                    raise ValueError(
                        "Fresh author metadata does not confirm the selected author."
                    )
                page = await context.new_page()
                url = f"https://www.instagram.com/p/{args.code}/"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if post_code(page.url) != args.code:
                    raise ValueError("Navigation did not reach the selected post.")
                actions = await post_actions(page)
                unlike = actions.locator('svg[aria-label="Unlike"]')
                like = actions.locator('svg[aria-label="Like"]')
                if await unlike.count() != 1 or await like.count() != 0:
                    raise ValueError(
                        "The selected post is not unambiguously liked. No click sent."
                    )
                require_same_account(expected, (await session_identity(context))[0])
                print(
                    f"Checked {args.code}: correct account, explicit author, not followed, currently liked.",
                    flush=True,
                )
                if not args.execute:
                    journal["status"] = "checks_passed_no_action"
                    return 0
                # Record intent before the click. Never retry a possibly delivered click.
                journal["click_attempted"] = True
                journal["status"] = "click_attempted_unverified"
                save_journal(journal)
                await click_and_verify(page, unlike, like, args.code)
                require_same_account(expected, (await session_identity(context))[0])
                journal["status"] = "unliked_verified_after_reload"
                print(
                    f"Unliked {args.code}; verified after reloading. No other items touched.",
                    flush=True,
                )
                return 0
            finally:
                await context.close()
    except Exception as error:
        # Never expose browser exception logs that might contain session data.
        print(
            "Stopped: "
            + (str(error) if type(error) is ValueError else type(error).__name__),
            flush=True,
        )
        if not journal["click_attempted"]:
            journal["status"] = "stopped_before_click"
        if journal["click_attempted"]:
            print(
                "A click may have reached Instagram. Check this item manually; do not retry blindly."
            )
        return 1
    finally:
        path = save_journal(journal)
        print(f"Test record saved: {path}")


def save_journal(journal):
    directory = ROOT / ".local-data"
    directory.mkdir(exist_ok=True, mode=0o700)
    path = directory / (
        "unlike-test-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + ".json"
    )
    with path.open("x", encoding="utf-8") as file:
        path.chmod(0o600)
        json.dump(journal, file, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Unlike this one checked item and verify after reload",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.code):
        parser.error("Invalid post code")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

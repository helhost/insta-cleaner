"""Compare one date range with two sequential/parallel monthly scans. Removes nothing."""

import argparse
import asyncio
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
from urllib.parse import parse_qsl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from insta_cleaner.following import session_identity


def ranges(start):
    first = date.fromisoformat(start)
    if first.day != 1:
        raise ValueError("Start must be the first day of a month")

    def advance(d):
        return date(d.year + (d.month == 12), d.month % 12 + 1, 1)

    middle = advance(first)
    end = advance(middle)
    return [
        (first.isoformat(), middle.isoformat()),
        (middle.isoformat(), end.isoformat()),
    ]


def compare(baseline, sequential, parallel):
    ids = lambda scans: set().union(*(set(s["ids"]) for s in scans))
    base, seq, par = ids([baseline]), ids(sequential), ids(parallel)
    ended = all(
        s["reason"] in ("no next instruction", "recognized empty")
        for s in [baseline, *sequential, *parallel]
    )
    return {
        "all_reached_observed_end": ended,
        "same_ids": base == seq == par,
        "comparison_passed": ended and base == seq == par,
        "sequential_missing": sorted(base - seq),
        "sequential_extra": sorted(seq - base),
        "parallel_missing": sorted(base - par),
        "parallel_extra": sorted(par - base),
        "boundary_overlap": len(set(sequential[0]["ids"]) & set(sequential[1]["ids"])),
    }


async def run(args):
    from playwright.async_api import async_playwright

    windows = ranges(args.start)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(ROOT / ".browser-profile"),
            channel="chrome",
            headless=args.headless,
            chromium_sandbox=True,
            accept_downloads=False,
        )
        try:
            owner, _ = await session_identity(context)

            async def scan(bounds):
                page = await context.new_page()
                started = perf_counter()
                try:
                    if (await session_identity(context))[0] != owner:
                        raise ValueError("Account changed")
                    async with page.expect_response(
                        lambda r: "appid=com.instagram.privacy.activity_center.liked_media_screen"
                        in r.url,
                        timeout=45000,
                    ) as captured:
                        await page.goto(
                            "https://www.instagram.com/your_activity/interactions/likes/",
                            wait_until="domcontentloaded",
                        )
                    seed = await captured.value
                    if seed.status != 200:
                        raise ValueError("Initial request failed")
                    form = dict(
                        parse_qsl(seed.request.post_data or "", keep_blank_values=True)
                    )
                    if "params" not in form:
                        raise ValueError("Initial form unavailable")
                    headers = {
                        k: v
                        for k, v in (await seed.request.all_headers()).items()
                        if k.lower()
                        in ("x-fb-lsd", "x-ig-app-id", "x-csrftoken", "x-asbd-id")
                    }
                    for script in (
                        "extension/parser.js",
                        "extension/dates.js",
                        "tools/probe_months.js",
                    ):
                        await page.evaluate((ROOT / script).read_text())
                    result = await page.evaluate(
                        "args=>runMonthRange(args)",
                        {
                            "body": await seed.text(),
                            "url": seed.url,
                            "form": form,
                            "headers": headers,
                            "settings": {"startDate": bounds[0], "endDate": bounds[1]},
                            "maxPages": args.pages,
                        },
                    )
                    if (await session_identity(context))[0] != owner:
                        raise ValueError("Account changed")
                    result.update(
                        start=bounds[0],
                        end=bounds[1],
                        seconds=round(perf_counter() - started, 3),
                    )
                    print(
                        f"  {bounds[0]} to {bounds[1]}: {len(result['ids'])} items, {result['pages']} pages, {result['seconds']}s; {result['reason']}",
                        flush=True,
                    )
                    return result
                finally:
                    await page.close()

            print(
                "Read-only comparison using saved login. No likes will be changed.",
                flush=True,
            )
            print("Combined-range baseline:", flush=True)
            baseline = await scan((windows[0][0], windows[1][1]))
            print("Two months sequentially:", flush=True)
            started = perf_counter()
            sequential = [await scan(bounds) for bounds in windows]
            sequential_seconds = perf_counter() - started
            print("Two months concurrently:", flush=True)
            started = perf_counter()
            tasks = [asyncio.create_task(scan(bounds)) for bounds in windows]
            try:
                parallel = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            parallel_seconds = perf_counter() - started
            result = {
                "baseline": baseline,
                "sequential": sequential,
                "parallel": parallel,
                "sequential_seconds": round(sequential_seconds, 3),
                "parallel_seconds": round(parallel_seconds, 3),
                **compare(baseline, sequential, parallel),
            }
            folder = ROOT / ".local-data"
            folder.mkdir(mode=0o700, exist_ok=True)
            path = folder / (
                "month-comparison-"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                + ".json"
            )
            with path.open("x") as f:
                path.chmod(0o600)
                json.dump(result, f, indent=2)
            print(
                f"Comparison: {'MATCH' if result['comparison_passed'] else 'INCONCLUSIVE OR MISMATCH'}; sequential {sequential_seconds:.2f}s, parallel {parallel_seconds:.2f}s"
            )
            print(
                "This compares observed results; it does not prove complete history or all date boundaries."
            )
            print(f"Saved: {path}")
        finally:
            await context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start", default="2014-08-01", help="First day of the first of two months"
    )
    parser.add_argument(
        "--pages", type=int, default=20, help="Maximum pages per range (1–20)"
    )
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    try:
        ranges(args.start)
    except ValueError:
        parser.error("Use a valid first-of-month start date, such as 2014-08-01")
    if not 1 <= args.pages <= 20:
        parser.error("--pages must be 1–20")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(
            f"Comparison stopped ({type(error).__name__}). No raw request details printed. Check saved login and close other collector browsers."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

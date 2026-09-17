"""Synthetic-only extension workflow test, including a simulated unlike. No real account."""

import asyncio
import json
from pathlib import Path
import tempfile
from urllib.parse import parse_qs
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
INITIAL = "/async/wbloks/fetch/?appid=com.instagram.privacy.activity_center.liked_media_screen"

ACTIVITY = {
    "main_authors_state_value": "",
    "main_filter_to_visible_on_facebook_value": False,
    "main_includes_location_value": False,
    "main_liked_privately_value": False,
    "main_content_type_value": 0,
    "main_content_types_value": "Posts, Reels",
    "main_account_history_events_state_value": "",
    "main_filter_to_visible_from_facebook_value": False,
}
EMPTY = json.dumps(
    {
        "payload": {
            "layout": {
                "bloks_payload": {
                    "data": [
                        {
                            "data": {
                                "key": "dtl:ig_activity_center:ya_has_items_rendered",
                                "initial_lispy": "(bk.action.bool.Const, false)",
                            }
                        }
                    ],
                    "embedded_payloads": [
                        {
                            "ig.components.Icon": {"resource_name": "error_outline_96"},
                            "bk.components.AccessibilityExtension": {
                                "role": "Header",
                                "label": "Ingen treff",
                            },
                        }
                    ],
                }
            }
        }
    }
)
REFRESH = '"com.instagram.privacy.activity_center.liked_refresh", (bk.action.map.Make, (bk.action.array.Make, "content_container_id", "content_element_id", "content_spinner_id", "main_order_state_value"), (bk.action.array.Make, (bk.action.i32.Const, 101), (bk.action.i32.Const, 102), (bk.action.i32.Const, 103)'


def body(pk, next_page=False, activity=None):
    values = [
        REFRESH,
        f'(bk.action.array.Make, "{pk}_43", "CODE{pk}", "clips", (bk.action.i32.Const, 2))',
    ]
    if next_page:
        args = ", ".join(
            json.dumps(x)
            for x in [
                "9",
                json.dumps(ACTIVITY if activity is None else activity),
                "next",
                "1",
                "2",
            ]
        )
        values.append(
            '(bk.action.bloks.AsyncActionWithDataManifest, "com.instagram.privacy.activity_center.liked_next", (bk.action.map.Make, (bk.action.array.Make, "page_size", "activity_center_params", "cursor", "container_id", "element_id"), (bk.action.array.Make, '
            + args
            + ")))"
        )
    return json.dumps({"payload": {"layout": {"bloks_payload": values}}})


async def main():
    liked = {"100": True, "200": True}
    clicks = []
    pagination = []
    refreshes = []
    active_refreshes = 0
    peak_refreshes = 0
    metadata_reads = []
    post_visits = []
    with tempfile.TemporaryDirectory() as profile:
        async with async_playwright() as p:
            extension = ROOT / "extension"
            c = await p.chromium.launch_persistent_context(
                profile,
                channel="chromium",
                headless=True,
                args=[
                    f"--disable-extensions-except={extension}",
                    f"--load-extension={extension}",
                ],
            )
            try:

                async def route(r):
                    nonlocal active_refreshes, peak_refreshes
                    url = r.request.url
                    if "/test-unlike/" in url:
                        pk = url.split("/test-unlike/")[1].split("?")[0]
                        liked[pk] = False
                        clicks.append(pk)
                        await r.fulfill(status=200, body="ok")
                    elif "/api/v1/media/" in url:
                        metadata_reads.append(url)
                        pk = url.split("/api/v1/media/")[1].split("/")[0]
                        await r.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(
                                {
                                    "status": "ok",
                                    "items": [
                                        {
                                            "pk": pk,
                                            "code": "CODE" + pk,
                                            "user": {"pk": "43"},
                                            "media_type": 2,
                                            "product_type": "clips",
                                            "has_liked": liked[pk],
                                        }
                                    ],
                                }
                            ),
                        )
                    elif "/following/" in url:
                        await r.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(
                                {
                                    "status": "ok",
                                    "users": [{"pk": "42", "username": "example"}],
                                    "has_more": False,
                                    "next_max_id": "",
                                    "should_limit_list_of_followings": False,
                                    "hidden_following_account_count": 0,
                                }
                            ),
                        )
                    elif "/async/wbloks/fetch/" in url:
                        if "liked_unlike" in url:
                            params = json.loads(
                                parse_qs(r.request.post_data)["params"][0]
                            )
                            ids = params["items_for_action"].split(",")
                            assert params["number_of_items"] == len(ids)
                            for composite in ids:
                                pk, author = composite.split("_")
                                assert author == "43"
                                liked[pk] = False
                                clicks.append(pk)
                            handler = (
                                "(bk.action.core.TakeLast, (bk.action.io.Toast, "
                                + json.dumps(
                                    f"Du har sluttet å like {len(ids)} innlegg."
                                )
                                + "), null)"
                            )
                            await r.fulfill(
                                status=200,
                                content_type="application/json",
                                body=json.dumps(
                                    {
                                        "payload": {
                                            "layout": {
                                                "bloks_payload": {
                                                    "tree": {
                                                        "bk.components.internal.Action": {
                                                            "handler": handler
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                ),
                            )
                            return
                        if "liked_refresh" in url:
                            active_refreshes += 1
                            peak_refreshes = max(peak_refreshes, active_refreshes)
                            await asyncio.sleep(0.05)
                            active_refreshes -= 1
                            refreshes.append(
                                json.loads(parse_qs(r.request.post_data)["params"][0])
                            )
                            await r.fulfill(
                                status=200,
                                content_type="application/json",
                                body=(
                                    EMPTY
                                    if refreshes[-1]["main_date_start_state_value"]
                                    > 1500000000
                                    else body(
                                        "300", True, {**ACTIVITY, **refreshes[-1]}
                                    )
                                ),
                            )
                            return
                        if "liked_next" in url:
                            pagination.append(
                                json.loads(parse_qs(r.request.post_data)["params"][0])
                            )
                        await r.fulfill(
                            status=200,
                            content_type="application/json",
                            body=(
                                body("100", True)
                                if "liked_media_screen" in url
                                else body("200")
                            ),
                        )
                    elif "/p/CODE" in url:
                        post_visits.append(url)
                        pk = url.split("/p/CODE")[1].split("/")[0]
                        label = "Unlike" if liked[pk] else "Like"
                        await r.fulfill(
                            status=200,
                            content_type="text/html",
                            body=f'<section><svg aria-label="Comment" width="20" height="20"></svg><svg aria-label="{label}" width="20" height="20" onclick="fetch(\'/test-unlike/{pk}\')"></svg></section>',
                        )
                    else:
                        await r.fulfill(
                            status=200,
                            content_type="text/html",
                            body="<html><body>Offline fixture<script>setTimeout(()=>fetch("
                            + json.dumps(INITIAL)
                            + ',{method:"POST",body:new URLSearchParams({params:"{}"})}),300)</script></body></html>',
                        )

                await c.route("https://www.instagram.com/**", route)
                await c.add_cookies(
                    [
                        {
                            "name": "ds_user_id",
                            "value": "42",
                            "domain": ".instagram.com",
                            "path": "/",
                            "secure": True,
                        }
                    ]
                )
                worker = (
                    c.service_workers[0]
                    if c.service_workers
                    else await c.wait_for_event("serviceworker")
                )
                page = await c.new_page()
                await page.goto("https://www.instagram.com/")
                await page.bring_to_front()
                await worker.evaluate(
                    "handle({type:'SCAN',filters:{content:'reels',relationship:'not-followed'}},{url:chrome.runtime.getURL('panel.html')})"
                )

                async def state():
                    return next(
                        iter(
                            (
                                await worker.evaluate(
                                    "chrome.storage.session.get(null)"
                                )
                            ).values()
                        )
                    )

                for _ in range(150):
                    s = await state()
                    if s["status"] == "ready":
                        break
                    await asyncio.sleep(0.1)
                assert (
                    s["status"] == "ready" and len(s["items"]) == 2 and s["pages"] == 2
                ), s
                assert s["following"]["complete"]
                assert pagination == [
                    {
                        "page_size": "100",
                        "activity_center_params": json.dumps(ACTIVITY),
                        "cursor": "next",
                        "container_id": "1",
                        "element_id": "2",
                    }
                ], pagination
                # Starting again on Likes must load a fresh document with the new token.
                old_token = s["token"]
                pagination.clear()
                await worker.evaluate(
                    "handle({type:'SCAN',filters:{content:'reels',relationship:'all'}},{url:chrome.runtime.getURL('panel.html')})"
                )
                for _ in range(150):
                    s = await state()
                    if s["status"] == "ready":
                        break
                    await asyncio.sleep(0.1)
                assert (
                    s["token"] != old_token
                    and s["status"] == "ready"
                    and s["pages"] == 2
                    and len(s["items"]) == 2
                ), s
                assert (
                    len(pagination) == 1 and pagination[0]["page_size"] == "100"
                ), pagination
                panel = await c.new_page()
                await panel.goto(worker.url.replace("background.js", "panel.html"))
                await page.bring_to_front()
                for _ in range(30):
                    await panel.evaluate("refresh()")
                    if await panel.locator("#count").inner_text() == "2 matches":
                        break
                    await asyncio.sleep(0.1)
                assert await panel.locator("#count").inner_text() == "2 matches"
                assert (
                    await panel.locator("#order").count() == 0
                    and await panel.locator("details").count() == 0
                )
                await panel.locator("#open-dates").click()
                await panel.locator("#calendar-year").select_option("2024")
                await panel.locator("#calendar-month").select_option("1")
                await panel.locator('[data-date="2024-02-10"]').click()
                await panel.locator('[data-date="2024-02-20"]').click()
                await panel.locator("#apply-dates").click()
                assert await panel.locator("#startDate").input_value() == "2024-02-10"
                assert await panel.locator("#endDate").input_value() == "2024-02-20"
                await panel.locator("#open-dates").click()
                await panel.locator("#date-close").click()
                assert await panel.locator("#endDate").input_value() == "2024-02-20"
                await panel.locator("#clear-dates").click()
                assert await panel.locator("#startDate").input_value() == ""
                await panel.set_viewport_size({"width": 390, "height": 860})
                await panel.screenshot(
                    path=str(
                        Path(tempfile.gettempdir())
                        / "insta-cleaner-extension-panel.png"
                    ),
                    full_page=True,
                )
                prepared = await worker.evaluate(
                    "handle({type:'PREPARE',ids:['100']},{url:chrome.runtime.getURL('panel.html')})"
                )
                assert clicks == [], "No action allowed before confirmation"
                await worker.evaluate(
                    "token=>handle({type:'CONFIRM',approval:token},{url:chrome.runtime.getURL('panel.html')})",
                    prepared["approval"]["token"],
                )
                for _ in range(200):
                    s = await state()
                    if s["status"] in ["finished", "halted"]:
                        break
                    await asyncio.sleep(0.1)
                if s["status"] != "finished":
                    debug = await c.new_page()
                    await debug.goto("https://www.instagram.com/p/CODE100/")
                    print(
                        "Synthetic DOM:",
                        await debug.evaluate("document.body.innerHTML"),
                        await debug.evaluate(
                            '[...document.querySelectorAll("svg")].map(x=>[x.getAttribute("aria-label"),x.getBoundingClientRect().width])'
                        ),
                    )
                    print("Synthetic click log:", clicks)
                assert s["status"] == "finished", s
                assert clicks == ["100"] and liked["200"] is True
                assert (
                    metadata_reads == [] and post_visits == []
                ), "All-author batches must not open or check individual posts"
                assert s["results"][0]["status"] == "unliked-server-confirmed"
                await panel.evaluate("refresh()")
                assert await panel.locator("#review").is_hidden()
                assert await panel.evaluate("refreshTimer===null")
                assert await panel.locator("#count").inner_text() == "1 like removed"
                await page.bring_to_front()
                await worker.evaluate(
                    "handle({type:'SCAN',filters:{content:'all',relationship:'all',startDate:'2014-09-01',endDate:'2014-10-01',order:'newest_to_oldest'}},{url:chrome.runtime.getURL('panel.html')})"
                )
                for _ in range(150):
                    s = await state()
                    if s["status"] == "ready":
                        break
                    await asyncio.sleep(0.1)
                assert s["status"] == "ready" and {
                    x["mediaId"] for x in s["items"]
                } == {"300", "200"}, s
                assert peak_refreshes == 2
                assert (
                    s["queueProgress"]["completed"] == s["queueProgress"]["total"] == 5
                )
                assert (
                    len(refreshes) == 5
                    and refreshes[0]["main_date_start_state_value"] > 0
                )
                assert (
                    refreshes[0]["main_date_start_state_value"]
                    < refreshes[0]["main_date_end_state_value"]
                )
                await panel.evaluate("refresh()")
                assert await panel.locator("#startDate").input_value() == "2014-09-01"
                await panel.screenshot(
                    path=str(
                        Path(tempfile.gettempdir())
                        / "insta-cleaner-extension-panel.png"
                    ),
                    full_page=True,
                )
                await panel.locator("#open-dates").click()
                await panel.screenshot(
                    path=str(
                        Path(tempfile.gettempdir()) / "insta-cleaner-calendar.png"
                    ),
                    full_page=True,
                )
                await panel.locator("#date-close").click()
                await panel.evaluate(
                    "globalThis.savedPanelState=state; state={...state,status:'scanning',startedAt:Date.now()-35000,queueProgress:{completed:17,total:53,workers:12}};render()"
                )
                assert (
                    await panel.locator("#action-hint").inner_text() == "32% searched"
                )
                assert await panel.locator("#stop").is_visible()
                assert await panel.locator("#review").is_hidden()
                assert await panel.locator("#percent").inner_text() == "32%"
                assert (
                    await panel.locator("#progress").get_attribute("aria-valuenow")
                    == "32"
                )
                assert await panel.locator("#count").inner_text() == "2 matches"
                assert "workers" not in await panel.locator("body").inner_text()
                await panel.screenshot(
                    path=str(
                        Path(tempfile.gettempdir()) / "insta-cleaner-progress.png"
                    ),
                    full_page=True,
                )
                await panel.evaluate("state=savedPanelState;render()")
                await panel.set_viewport_size({"width": 320, "height": 740})
                assert await panel.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                )
                # The action remains reachable without scrolling, even in a short panel.
                await panel.set_viewport_size({"width": 320, "height": 540})
                await panel.evaluate("scrollTo(0, 0)")
                assert await panel.locator("#review").evaluate(
                    "el => {const r=el.getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight && r.right<=innerWidth}"
                )
                await panel.locator("#review").click()
                assert await panel.locator("#confirm").evaluate("el=>el.open")
                await panel.locator("#cancel").click()
                assert clicks == [
                    "100"
                ], "Opening the dock confirmation must not remove likes"
                await panel.evaluate("scrollTo(0, document.body.scrollHeight)")
                await panel.wait_for_timeout(100)
                assert await panel.evaluate(
                    "document.querySelector('footer').getBoundingClientRect().bottom <= document.querySelector('#action-bar').getBoundingClientRect().top"
                )
                await panel.screenshot(
                    path=str(
                        Path(tempfile.gettempdir()) / "insta-cleaner-action-bar.png"
                    )
                )
                await panel.locator('[data-content="reels"]').click()
                assert await panel.locator("#action-bar").is_hidden()
                await panel.locator('[data-content="all"]').click()
                assert await panel.locator("#action-bar").is_visible()
                await panel.set_viewport_size({"width": 320, "height": 740})
                await panel.locator("#open-dates").click()
                await panel.locator("#pick-start").click()
                await panel.locator('[data-date="2014-09-30"]').click()
                await panel.locator('[data-date="2014-09-02"]').click()
                await panel.locator("#apply-dates").click()
                assert await panel.locator("#date-picker").evaluate("el=>el.open")
                assert "end date" in await panel.locator("#date-error").inner_text()
                assert await panel.locator("#startDate").input_value() == "2014-09-01"
                assert await panel.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                )
                await panel.screenshot(
                    path=str(
                        Path(tempfile.gettempdir())
                        / "insta-cleaner-calendar-narrow.png"
                    ),
                    full_page=True,
                )
                await panel.locator("#date-close").click()
                await panel.set_viewport_size({"width": 390, "height": 860})
                await worker.evaluate(
                    "handle({type:'SCAN',filters:{content:'all',relationship:'all',startDate:'2020-01-01',endDate:'2021-01-01'}},{url:chrome.runtime.getURL('panel.html')})"
                )
                for _ in range(150):
                    s = await state()
                    if s["status"] == "ready":
                        break
                    await asyncio.sleep(0.1)
                assert (
                    s["status"] == "ready"
                    and s["items"] == []
                    and "no matches" in s["message"]
                ), s
                assert peak_refreshes == 12 and s["queueProgress"]["workers"] == 12, s
                assert (
                    s["queueProgress"]["completed"] == s["queueProgress"]["total"] == 53
                ), s
                for script in (
                    "extension/parser.js",
                    "extension/dates.js",
                    "tools/probe_months.js",
                ):
                    await page.evaluate((ROOT / script).read_text())
                result = await page.evaluate(
                    "args=>runMonthRange(args)",
                    {
                        "body": body("100", True),
                        "url": "https://www.instagram.com" + INITIAL,
                        "form": {"params": "{}"},
                        "headers": {},
                        "settings": {
                            "startDate": "2020-01-01",
                            "endDate": "2020-02-01",
                        },
                        "maxPages": 3,
                    },
                )
                assert result["reason"] == "recognized empty" and result["ids"] == []
                print(
                    "PASS: scan, date pagination, recognized empty range, month probe in browser, and confirmed synthetic unlike."
                )
            finally:
                await c.close()


asyncio.run(main())

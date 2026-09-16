"""Bounded read-only Likes collection and explicit author resolution."""
import asyncio
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from .media import PREFIX, response_records, strings
from .authors import AuthorTracker, inspect_metadata, metadata_endpoint
from .following import LoginRequired, session_identity

READ_ACTIONS = {'liked_media_screen', 'liked_next', 'liked_refresh'}

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


STRING = r'"(?:\\.|[^"\\])*"'
NEXT = re.compile(
    r'\(bk\.action\.bloks\.AsyncActionWithDataManifest,\s*'
    r'"com\.instagram\.privacy\.activity_center\.liked_next",\s*'
    r'\(bk\.action\.map\.Make,\s*\(bk\.action\.array\.Make,\s*'
    r'"page_size",\s*"activity_center_params",\s*"cursor",\s*"container_id",\s*"element_id"\),\s*'
    r'\(bk\.action\.array\.Make,\s*(' + STRING + r'),\s*(' + STRING + r'),\s*('
    + STRING + r'),\s*(' + STRING + r'),\s*(' + STRING + r')\)\)')


def next_params(body):
    document = json.loads(body.strip().removeprefix('for (;;);'))
    found = []
    for expression in strings(document['payload']['layout']['bloks_payload']):
        for match in NEXT.finditer(expression):
            values = [json.loads(value) for value in match.groups()]
            params = dict(zip(('page_size', 'activity_center_params', 'cursor', 'container_id', 'element_id'), values))
            if params not in found:
                found.append(params)
    if len(found) != 1 or not found[0]['cursor']:
        raise ValueError('No single supported next-page instruction; completion is unverified')
    return found[0]


def envelope_error(body):
    document = json.loads(body.strip().removeprefix('for (;;);'))
    if not isinstance(document, dict) or not isinstance(document.get('payload'), dict):
        code = document.get('error') if isinstance(document, dict) else None
        return f'unsupported page envelope; server error {code if type(code) is int else "unknown"}'
    return None


async def check_authors(context, tracker, limit, timeout=8, *, items=None):
    """Open a bounded sample normally; join only exact media-ID/code pairs."""
    page = await context.new_page()
    pending = set()
    accepted = set()
    active_key = None
    author_ready = asyncio.Event()

    def add_rows(rows):
        matched = [row for row in rows if (row[0], row[1]) in accepted]
        tracker.add_details(matched)
        if any((row[0], row[1]) == active_key for row in matched):
            author_ready.set()

    async def inspect(response):
        try:
            if response.status == 200:
                rows, _ = inspect_metadata(await response.text())
                add_rows(rows)
        except Exception:
            pass  # An unreadable ancillary response cannot establish author evidence.

    def observe(response):
        if metadata_endpoint(response.url) or response.request.resource_type == 'document':
            task = asyncio.create_task(inspect(response))
            pending.add(task)
            task.add_done_callback(pending.discard)

    page.on('response', observe)
    try:
        for item in (tracker.preview() if items is None else items)[:limit]:
            key = (item['media_id'], item['code'])
            accepted.add(key)
            active_key = key
            author_ready.clear()
            try:
                await page.goto(f"https://www.instagram.com/p/{item['code']}/", wait_until='domcontentloaded', timeout=30000)
                rows, _ = inspect_metadata(await page.content())
                add_rows([row for row in rows if (row[0], row[1]) == key])
                if not author_ready.is_set():
                    try:
                        await asyncio.wait_for(author_ready.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        pass  # Keep inferred/unknown evidence when metadata never arrives.
                state = next(row['evidence'] for row in tracker.preview()
                             if (row['media_id'], row['code']) == key)
                print(f"  Author sample #{item['index']}: {state}.", flush=True)
            except Exception:
                print(f"  Author sample #{item['index']}: unavailable; retaining existing evidence.", flush=True)
    finally:
        page.remove_listener('response', observe)
        for task in list(pending):
            task.cancel()
        await asyncio.gather(*list(pending), return_exceptions=True)
        await page.close()


async def open_likes(context, page, ready, *, manual=False, headless=False):
    if headless:
        await session_identity(context)
    if manual:
        print('Open Your activity → Likes. Collection starts automatically.', flush=True)
    else:
        print('Opening Likes automatically using the saved session.', flush=True)
    target = 'https://www.instagram.com/' if manual else 'https://www.instagram.com/your_activity/interactions/likes/'
    await page.goto(target, wait_until='domcontentloaded', timeout=30000)
    if '/accounts/login' in page.url or '/challenge/' in page.url:
        raise LoginRequired('Login or verification required. Run: python3 instagram.py login')
    return await asyncio.wait_for(ready, timeout=180 if manual else 45)


async def collect_likes(context, *, pages=3):
    if not 1 <= pages <= 20:
        raise ValueError('pages must be between 1 and 20')
    account, _ = await session_identity(context)
    tracker = AuthorTracker()
    batches = 0
    reason = 'page limit reached'
    page = await context.new_page()
    ready = asyncio.get_running_loop().create_future()

    def observed(response):
        if not ready.done() and activity_action(response.url) in {'liked_media_screen', 'liked_refresh'}:
            ready.set_result(response)

    page.on('response', observed)
    try:
        seed = await open_likes(context, page, ready, headless=True)
        if seed.status != 200:
            raise ValueError(f'Initial Likes request returned HTTP {seed.status}')
        body = await seed.text()
        form = dict(parse_qsl(seed.request.post_data or '', keep_blank_values=True))
        if 'params' not in form:
            raise ValueError('Unsupported initial request form')
        headers = {k: v for k, v in (await seed.request.all_headers()).items()
                   if k.lower() in {'x-fb-lsd', 'x-ig-app-id', 'x-csrftoken', 'x-asbd-id', 'x-requested-with', 'accept', 'origin', 'referer'}}
        parts = urlsplit(seed.url)
        query = dict(parse_qsl(parts.query))
        query['appid'] = 'com.instagram.privacy.activity_center.liked_next'
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ''))
        seen = set()
        for index in range(pages):
            stage = 'parse page'
            problem = envelope_error(body)
            if problem:
                reason = problem
                break
            records, warning = response_records({'response': {'content': {'text': body}}})
            if warning:
                reason = warning
                break
            before = len(tracker.likes)
            tracker.add_likes(records)
            rows, _ = inspect_metadata(body)
            tracker.add_details(rows)
            batches += 1
            print(f'  Page {batches}: {len(records)} items; {len(tracker.likes)} unique total.', flush=True)
            if len(tracker.likes) == before:
                reason = 'no new items'
                break
            if index + 1 == pages:
                break
            stage = 'parse continuation'
            params = next_params(body)
            if params['cursor'] in seen:
                reason = 'repeated cursor'
                break
            seen.add(params['cursor'])
            form['params'] = json.dumps(params)
            await asyncio.sleep(1.5)
            stage = 'send next page'
            response = await page.evaluate("""async ({url, form, headers}) => {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 30000);
                try {
                    const response = await fetch(url, {
                        method: 'POST', credentials: 'same-origin', redirect: 'error',
                        headers, body: new URLSearchParams(form), signal: controller.signal
                    });
                    return {status: response.status, body: await response.text()};
                } finally { clearTimeout(timer); }
            }""", {'url': url, 'form': form,
                    'headers': {k: v for k, v in headers.items() if k.lower() not in {'origin', 'referer'}}})
            if response['status'] != 200:
                reason = f"HTTP {response['status']}"
                break
            stage = 'read next page'
            body = response['body']

    except LoginRequired:
        raise
    except (ValueError, KeyError, TypeError):
        reason = 'unsupported Likes response or pagination format'
    except asyncio.TimeoutError:
        reason = 'timed out waiting for Likes'
    finally:
        page.remove_listener('response', observed)
        await page.close()
    if (await session_identity(context))[0] != account:
        raise LoginRequired('Session changed during collection; rerun with one account.')
    return tracker, {'account_id': account, 'pages': batches, 'complete': False, 'stop_reason': reason}

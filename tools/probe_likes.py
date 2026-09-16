"""Limited read-only Likes pagination experiment; start by opening Likes manually."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import traceback
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from inspect_har import response_records, strings
from observe_likes import activity_action, PROFILE, close_context
from author_check import AuthorTracker, inspect_metadata, metadata_endpoint

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


async def check_authors(context, tracker, limit):
    """Open a bounded sample normally; join only exact media-ID/code pairs."""
    page = await context.new_page()
    pending = set()
    accepted = set()

    async def inspect(response):
        try:
            if response.status == 200:
                rows, _ = inspect_metadata(await response.text())
                tracker.add_details([row for row in rows if (row[0], row[1]) in accepted])
        except Exception:
            pass  # An unreadable ancillary response cannot establish author evidence.

    def observe(response):
        if metadata_endpoint(response.url) or response.request.resource_type == 'document':
            task = asyncio.create_task(inspect(response))
            pending.add(task)
            task.add_done_callback(pending.discard)

    page.on('response', observe)
    try:
        for item in tracker.preview()[:limit]:
            key = (item['media_id'], item['code'])
            accepted.add(key)
            try:
                await page.goto(f"https://www.instagram.com/p/{item['code']}/", wait_until='domcontentloaded', timeout=30000)
                rows, _ = inspect_metadata(await page.content())
                tracker.add_details([row for row in rows if (row[0], row[1]) == key])
                # Allow asynchronously loaded route metadata to arrive, without
                # requiring network-idle on Instagram's continually active page.
                await asyncio.sleep(3)
                if pending:
                    await asyncio.wait(list(pending), timeout=5)
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


async def probe(args):
    from playwright.async_api import async_playwright
    tracker = AuthorTracker()
    batches = 0
    reason = 'page limit reached'
    stage = 'initialization'
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(str(PROFILE), channel=args.channel,
            headless=False, chromium_sandbox=True, accept_downloads=False)
        ready = asyncio.get_running_loop().create_future()

        def observed(response):
            if not ready.done() and activity_action(response.url) in {'liked_media_screen', 'liked_refresh'}:
                ready.set_result(response)

        context.on('response', observed)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            print('Open Your activity → Likes in this browser. The probe then loads up to '
                  f'{args.pages} pages automatically. Do not change filters or remove items during the run.', flush=True)
            await page.goto('https://www.instagram.com/', wait_until='domcontentloaded')
            seed = await asyncio.wait_for(ready, timeout=180)
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
            for index in range(args.pages):
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
                if index + 1 == args.pages:
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
            if getattr(args, 'authors', 0) and tracker.likes:
                stage = 'check authors'
                print('Checking a small author sample by opening collected posts…', flush=True)
                await check_authors(context, tracker, args.authors)
        except (ValueError, KeyError):
            # Errors here use fixed local descriptions; never print request data.
            reason = 'unsupported response or pagination format'
        except asyncio.TimeoutError:
            reason = 'timed out waiting for Likes'
        except Exception as error:
            category = type(error).__name__
            frames = traceback.extract_tb(error.__traceback__)
            local = [frame for frame in frames if Path(frame.filename).resolve().is_relative_to(Path(__file__).resolve().parents[1]) and '.venv' not in Path(frame.filename).parts]
            location = f' at {Path(local[-1].filename).name}:{local[-1].lineno}' if local else ''
            codes = [code for code in ('ECONNRESET', 'ETIMEDOUT', 'ENOTFOUND', 'ERR_HTTP2_PROTOCOL_ERROR') if code in str(error)]
            reason = f'{stage}: {category}{location}' + (f' ({codes[0]})' if codes else '')
        finally:
            context.remove_listener('response', observed)
            await close_context(context)
            output = Path(__file__).resolve().parents[1] / '.local-data'
            output.mkdir(exist_ok=True, mode=0o700)
            path = output / ('likes-probe-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
            with path.open('x') as file:
                path.chmod(0o600)
                json.dump({'schema_version': 1, 'complete': False, 'pages': batches,
                           'stop_reason': reason, 'items': tracker.preview()}, file, indent=2)
            print(f'Stopped: {reason}. This is a partial development inventory.\nSaved: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', choices=['chrome'], default='chrome')
    parser.add_argument('--pages', type=int, default=3)
    parser.add_argument('--authors', type=int, default=0, help='Automatically open up to five collected posts to check explicit authors')
    args = parser.parse_args()
    if not 0 <= args.authors <= 5:
        parser.error('--authors must be between 0 and 5')
    if not 1 <= args.pages <= 5:
        parser.error('--pages must be between 1 and 5 during this experiment')
    try:
        asyncio.run(probe(args))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

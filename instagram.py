"""Instagram cleaner entry point. Currently supports login and Following collection."""
import argparse
import asyncio
from pathlib import Path

from insta_cleaner.following import LoginRequired, collect_following, session_identity

ROOT = Path(__file__).resolve().parent


async def run(args):
    from playwright.async_api import async_playwright, Error as BrowserError
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(ROOT / '.browser-profile'), channel=args.channel,
                headless=args.command != 'login', chromium_sandbox=True,
                accept_downloads=False)
            try:
                if args.command == 'login':
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto('https://www.instagram.com/', wait_until='domcontentloaded')
                    print('Log in in the browser. Waiting up to five minutes for a saved session.', flush=True)
                    for _ in range(300):
                        try:
                            await session_identity(context)
                            print('Session saved. You can now run: python3 instagram.py following')
                            return 0
                        except LoginRequired:
                            await asyncio.sleep(1)
                    print('Login timed out. Run the login command again when ready.')
                    return 1
                print('Collecting Following using your saved login…', flush=True)
                snapshot = await collect_following(context, page_size=args.page_size,
                    progress=lambda count, pages: print(f'  {count} accounts · {pages} pages', flush=True))
                path = snapshot.save(ROOT / '.local-data')
                state = 'Complete traversal' if snapshot.complete else 'Partial collection'
                print(f'{state}: {len(snapshot.accounts)} accounts. {snapshot.stop_reason}.')
                print(f'Saved: {path}')
                return 0 if snapshot.complete else 1
            finally:
                await context.close()
    except LoginRequired as error:
        print(str(error))
        return 1
    except BrowserError:
        print('Browser or request failed. Close other collectors; run "python3 instagram.py login" if login needs renewing.')
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('login', 'following'):
        command = commands.add_parser(name)
        command.add_argument('--channel', choices=['chrome', 'chromium'], default='chrome')
        if name == 'following':
            command.add_argument('--page-size', type=int, default=100)
    args = parser.parse_args()
    if args.command == 'following' and not 1 <= args.page_size <= 200:
        parser.error('--page-size must be between 1 and 200')
    if args.channel == 'chromium':
        args.channel = None
    try:
        return asyncio.run(run(args))
    except ImportError:
        print('Install dependencies: python3 -m pip install -r requirements.txt')
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

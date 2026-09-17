"""Export Chrome icon PNGs from the canonical SVG using local Chromium."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "extension" / "icons"
SIZES = (16, 32, 48, 128)


async def main():
    svg = (ICON_DIR / "icon.svg").read_text()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(device_scale_factor=1)
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(
                "<style>html,body{margin:0;background:transparent;overflow:hidden}"
                "svg{display:block;width:100vw;height:100vh}</style>" + svg
            )
            for size in SIZES:
                await page.set_viewport_size({"width": size, "height": size})
                await page.screenshot(
                    path=str(ICON_DIR / f"icon-{size}.png"), omit_background=True
                )
                print(f"Exported {size} × {size}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

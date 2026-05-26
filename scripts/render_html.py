"""Render a local HTML file to PNG and/or PDF via headless Chromium.

Used to verify that pages with client-side-rendered content (mermaid diagrams,
KaTeX math, JS-driven layout) actually display correctly. Quarto's `quarto
render` only verifies that the source compiles; it does not execute the
browser-side JS that turns `<pre class="mermaid">` blocks into SVG.

Usage:
    pixi run python scripts/render_html.py <input.html> [--png out.png] [--pdf out.pdf]

If neither --png nor --pdf is given, writes <input>.png next to the input.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def render(
    html_path: Path,
    png_path: Path | None,
    pdf_path: Path | None,
    wait_ms: int,
    width: int,
) -> None:
    url = html_path.resolve().as_uri()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": width, "height": 900})
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(wait_ms)
        if png_path is not None:
            await page.screenshot(path=str(png_path), full_page=True)
            print(f"wrote {png_path}")
        if pdf_path is not None:
            await page.pdf(path=str(pdf_path), format="A4", print_background=True)
            print(f"wrote {pdf_path}")
        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--png", type=Path, default=None)
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=1500,
        help="Extra wait for client-side JS rendering (mermaid, KaTeX). Default 1500.",
    )
    parser.add_argument("--width", type=int, default=1400, help="Viewport width.")
    args = parser.parse_args()

    if args.png is None and args.pdf is None:
        args.png = args.html.with_suffix(".png")

    asyncio.run(render(args.html, args.png, args.pdf, args.wait_ms, args.width))


if __name__ == "__main__":
    main()

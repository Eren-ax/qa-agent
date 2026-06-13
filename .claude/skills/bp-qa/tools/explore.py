"""DOM exploration helper for Channel.io test channels.

Opens a test channel in a headed browser, clicks the "문의하기" (contact) button,
waits for the ALF chat widget to load, and dumps HTML + screenshots to
`storage/explore/<timestamp>/` for selector identification.

Usage:
    uv run python -m tools.explore <url>
    uv run python -m tools.explore https://vqnol.channel.io

The browser stays open after dumping so you can inspect the DOM via DevTools.
Press Enter in the terminal to close.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, async_playwright


REPO_ROOT = Path(__file__).resolve().parent.parent
EXPLORE_DIR = REPO_ROOT / "storage" / "explore"

CONTACT_BUTTON_CANDIDATES = [
    "text=문의하기",
    "button:has-text('문의하기')",
    "[aria-label*='문의']",
]


async def dump(page: Page, out_dir: Path, label: str) -> None:
    """Save HTML + screenshot + iframe inventory for a given state."""
    out_dir.mkdir(parents=True, exist_ok=True)

    html = await page.content()
    (out_dir / f"{label}.html").write_text(html, encoding="utf-8")

    await page.screenshot(path=str(out_dir / f"{label}.png"), full_page=True)

    # Inventory iframes — Channel.io widget often renders inside one.
    frames_info = []
    for i, frame in enumerate(page.frames):
        frames_info.append(f"[{i}] name={frame.name!r} url={frame.url}")
        try:
            frame_html = await frame.content()
            (out_dir / f"{label}.frame{i}.html").write_text(frame_html, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            frames_info.append(f"    (failed to dump frame {i}: {exc})")
    (out_dir / f"{label}.frames.txt").write_text("\n".join(frames_info), encoding="utf-8")

    print(f"  ↳ dumped {label}: html, screenshot, {len(page.frames)} frame(s)")


async def click_contact_button(page: Page) -> bool:
    """Try multiple selector strategies to find and click '문의하기'."""
    for selector in CONTACT_BUTTON_CANDIDATES:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=5000)
            await locator.click()
            print(f"  ↳ clicked: {selector}")
            return True
        except Exception:  # noqa: BLE001
            continue

    # Fallback: search in all frames.
    for frame in page.frames:
        for selector in CONTACT_BUTTON_CANDIDATES:
            try:
                locator = frame.locator(selector).first
                await locator.wait_for(state="visible", timeout=2000)
                await locator.click()
                print(f"  ↳ clicked (in frame {frame.url}): {selector}")
                return True
            except Exception:  # noqa: BLE001
                continue
    return False


async def explore(url: str) -> None:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = EXPLORE_DIR / ts
    print(f"[explore] target: {url}")
    print(f"[explore] output: {out_dir}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("[1/4] navigating…")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=15000)
        await dump(page, out_dir, "01-landing")

        print("[2/4] locating '문의하기' button…")
        clicked = await click_contact_button(page)
        if not clicked:
            print("  ⚠ could not find '문의하기' automatically.")
            print("  ⚠ please click it manually in the browser window.")
            input("  (press Enter once the chat widget is visible) ")

        print("[3/4] waiting for chat widget to render…")
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        await dump(page, out_dir, "02-widget-open")

        print("[4/4] done.")
        print(f"       inspect output: {out_dir}")
        print("       browser left open for manual DevTools inspection.")
        print("       press Enter to close.")
        await asyncio.get_event_loop().run_in_executor(None, input)

        await context.close()
        await browser.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: uv run python -m tools.explore <url>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(explore(sys.argv[1]))


if __name__ == "__main__":
    main()

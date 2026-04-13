"""Interactive CLI for manually driving an ALF chat session.

Usage:
    uv run python -m tools.cli <channel-url>
    uv run python -m tools.cli https://vqnol.channel.io

Optional flags:
    --headed            show the browser window (default: headless)
    --slowmo <ms>       Playwright slow-motion delay (default: 0)
    --timeout <s>       per-reply timeout (default: 60)

Sanity-check tool: type messages, see ALF replies, verify the Playwright
driver is stable before layering the scoring / scenario pipeline on top.
Empty input (just Enter) exits.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from tools.chat_driver import PlaywrightDriver


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tools.cli",
        description="Drive an ALF chat session interactively.",
    )
    p.add_argument("url", help="test channel URL (e.g. https://vqnol.channel.io)")
    p.add_argument(
        "--headed",
        action="store_true",
        help="show the browser window (default: headless)",
    )
    p.add_argument(
        "--slowmo",
        type=int,
        default=0,
        help="Playwright slow-motion delay in ms (default: 0)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="per-reply timeout in seconds (default: 60)",
    )
    return p.parse_args(argv)


async def _read_line(prompt: str) -> str:
    """asyncio-safe stdin readline."""
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)


async def run(url: str, *, headed: bool, slowmo: int, timeout: float) -> int:
    driver = PlaywrightDriver(headless=not headed, slow_mo_ms=slowmo)
    print(f"[cli] opening {url} …")
    try:
        welcome = await driver.open(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[cli] failed to open: {exc}", file=sys.stderr)
        await driver.close()
        return 1

    if welcome:
        print(f"[cli] {len(welcome)} welcome message(s) captured:")
        for m in welcome:
            print(f"  ALF: {m.text}")
    else:
        print("[cli] no welcome message detected.")

    print("[cli] ready. type a message and press Enter. empty line to quit.")
    try:
        while True:
            try:
                user_text = (await _read_line("> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                break
            await driver.send(user_text)
            try:
                replies = await driver.wait_reply(timeout=timeout)
            except TimeoutError as exc:
                print(f"[cli] timeout: {exc}", file=sys.stderr)
                continue
            for reply in replies:
                print(f"ALF: {reply.text}")
    finally:
        await driver.close()
        print("[cli] session closed.")
    return 0


def main() -> None:
    args = _parse_args(sys.argv[1:])
    sys.exit(asyncio.run(run(args.url, headed=args.headed, slowmo=args.slowmo, timeout=args.timeout)))


if __name__ == "__main__":
    main()

"""Chat driver abstraction + Playwright implementation for Channel.io / ALF.

Design:
- `ChatDriver` defines the minimal I/O surface the rest of the system depends on.
- `PlaywrightDriver` is the current implementation that opens a test channel in a
  headless (or headed) Chromium, clicks the contact button, and drives the ALF
  widget through its DOM.

Selectors derived from vqnol.channel.io exploration (storage/explore/20260413-154959).
All selectors prefer stable anchors: `data-ch-testid`, ARIA roles, and
a11y-hidden labels. Hash-suffixed CSS classes are matched by prefix via
`[class*="..."]` to stay resilient across widget rebuilds.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)


# ---- Selectors (stable anchors only) ---------------------------------------

SEL_WIDGET_ROOT = '[data-ch-testid="user-chat"]'
SEL_MESSAGE_INPUT = '[data-ch-testid="messenger-footer-text-area"]'
SEL_SEND_BUTTON = '[data-ch-testid="messenger-footer-send-button"]'
SEL_MESSAGE_LIST = 'section[role="log"]'

# ALF (agent) message bubble text nodes: each bubble's text lives in
# `div[id^="node-"]` nested inside a wrapper whose class starts with
# "DeskMessagestyled__Wrapper" (user messages use a different wrapper).
SEL_ALF_MESSAGE_TEXT = '[class*="DeskMessagestyled__Wrapper"] div[id^="node-"]'

# Typing indicator wrapper — empty when idle, populated while ALF is composing.
SEL_TYPING_WRAPPER = '[class*="MessageStreamstyled__Typing"]'

# Contact / "문의하기" entry button on the landing page.
CONTACT_BUTTON_CANDIDATES: tuple[str, ...] = (
    "text=문의하기",
    "button:has-text('문의하기')",
    "[aria-label*='문의']",
)


# ---- Data types ------------------------------------------------------------


@dataclass(frozen=True)
class AlfMessage:
    """A single ALF-authored message."""

    node_id: str  # DOM id, e.g. "node-c88e197f-..."
    text: str
    ts: float = field(default_factory=time.time)


# ---- Abstract interface ----------------------------------------------------


class ChatDriver(ABC):
    """Minimal async I/O surface the rest of qa-agent depends on."""

    @abstractmethod
    async def open(self, channel_url: str) -> list[AlfMessage]:
        """Open a fresh session. Returns any pre-existing ALF messages
        (welcome greeting, etc.) observed after the widget is ready."""

    @abstractmethod
    async def send(self, text: str) -> None:
        """Send a user message. Does not wait for a reply."""

    @abstractmethod
    async def wait_reply(self, timeout: float = 60.0, quiet_period: float = 2.0) -> list[AlfMessage]:
        """Block until ALF is done replying to the most recent send.

        ALF frequently emits a reply as multiple back-to-back messages
        (acknowledgment + follow-up). We wait for at least one new message
        to appear, then a `quiet_period` during which no new nodes and no
        typing indicator are observed, then return all new messages in order.

        Raises TimeoutError if no reply within `timeout` seconds."""

    @abstractmethod
    async def close(self) -> None:
        """Release browser resources."""


# ---- Playwright implementation --------------------------------------------


class PlaywrightDriver(ChatDriver):
    """Drives the ALF chat widget rendered directly in the channel.io page.

    Note: vqnol.channel.io renders the widget in the main frame (no iframe
    hop required). If deployed to an embedded-widget page, this driver would
    need an iframe-entering step.
    """

    def __init__(self, headless: bool = True, slow_mo_ms: int = 0):
        self._headless = headless
        self._slow_mo_ms = slow_mo_ms
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._seen_node_ids: set[str] = set()

    # -- lifecycle -----------------------------------------------------------

    async def open(self, channel_url: str) -> list[AlfMessage]:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless, slow_mo=self._slow_mo_ms)
        self._ctx = await self._browser.new_context()
        self._page = await self._ctx.new_page()

        await self._page.goto(channel_url, wait_until="domcontentloaded")

        # Landing page: click "문의하기" to enter the chat room.
        await self._click_contact_button()

        # Wait for the chat widget root + input field.
        await self._page.wait_for_selector(SEL_WIDGET_ROOT, timeout=15_000)
        await self._page.wait_for_selector(SEL_MESSAGE_INPUT, timeout=15_000)

        # Capture any pre-existing ALF messages (welcome greeting, etc.)
        # so they are not mistaken for replies to future sends. The welcome
        # bubble typically renders 1-3s after the input field appears, so we
        # poll briefly — channels without a welcome message will fall through.
        welcome = await self._wait_for_welcome(timeout=5.0)
        self._seen_node_ids.update(m.node_id for m in welcome)
        return welcome

    async def _wait_for_welcome(self, timeout: float) -> list[AlfMessage]:
        """Poll up to `timeout` seconds for any initial ALF messages.

        Once a message appears, continue polling briefly (300ms quiet period)
        to catch multi-part welcomes that arrive back-to-back.
        """
        deadline = time.monotonic() + timeout
        quiet_after_first = 0.6
        last_seen_count = 0
        last_change = time.monotonic()
        while time.monotonic() < deadline:
            msgs = await self._collect_all_alf_messages()
            if len(msgs) != last_seen_count:
                last_seen_count = len(msgs)
                last_change = time.monotonic()
            # If we have at least one message and it's been quiet, return.
            if msgs and (time.monotonic() - last_change) >= quiet_after_first:
                return msgs
            await asyncio.sleep(0.25)
        # Timed out — return whatever we have (possibly empty).
        return await self._collect_all_alf_messages()

    async def close(self) -> None:
        if self._ctx:
            await self._ctx.close()
            self._ctx = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        self._page = None

    # -- messaging -----------------------------------------------------------

    async def send(self, text: str) -> None:
        page = self._require_page()
        textarea = page.locator(SEL_MESSAGE_INPUT)
        await textarea.click()
        await textarea.fill(text)
        # Enable-state flip of the send button is the canonical signal that
        # the input is non-empty; press Enter afterwards for deterministic send.
        await page.locator(SEL_SEND_BUTTON).wait_for(state="visible", timeout=5_000)
        await page.keyboard.press("Enter")

    async def wait_reply(self, timeout: float = 60.0, quiet_period: float = 2.0) -> list[AlfMessage]:
        """Poll for new ALF messages, then wait out a quiet period.

        Completion criterion:
          1. At least one new ALF bubble node has appeared.
          2. For `quiet_period` seconds: no additional new nodes AND typing
             indicator remains idle.
        All new messages accumulated during that window are returned in DOM
        order. Raises TimeoutError if no reply at all within `timeout`.
        """
        self._require_page()
        deadline = time.monotonic() + timeout
        poll_interval = 0.4

        first_seen_at: float | None = None
        last_activity_at: float = time.monotonic()
        accumulated: list[AlfMessage] = []
        accumulated_ids: set[str] = set()

        while time.monotonic() < deadline:
            new_msgs = await self._collect_new_alf_messages()
            typing_idle = await self._typing_idle()

            added_this_tick = False
            for m in new_msgs:
                if m.node_id not in accumulated_ids:
                    accumulated.append(m)
                    accumulated_ids.add(m.node_id)
                    added_this_tick = True

            if added_this_tick or not typing_idle:
                last_activity_at = time.monotonic()
                if first_seen_at is None and accumulated:
                    first_seen_at = last_activity_at

            # Completion: have at least one message, and quiet period elapsed.
            if accumulated and typing_idle and (time.monotonic() - last_activity_at) >= quiet_period:
                self._seen_node_ids.update(accumulated_ids)
                return accumulated

            await asyncio.sleep(poll_interval)

        if accumulated:
            # Timed out while still seeing activity — return what we have.
            self._seen_node_ids.update(accumulated_ids)
            return accumulated

        raise TimeoutError(f"no new ALF reply within {timeout}s " f"(known bubbles: {len(self._seen_node_ids)})")

    # -- internals -----------------------------------------------------------

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("driver not opened; call .open(url) first")
        return self._page

    async def _click_contact_button(self) -> None:
        page = self._require_page()
        for selector in CONTACT_BUTTON_CANDIDATES:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=5_000)
                await locator.click()
                return
            except PlaywrightTimeoutError:
                continue
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError("could not find '문의하기' contact button; " "landing page structure may have changed")

    async def _collect_all_alf_messages(self) -> list[AlfMessage]:
        """Collect all ALF message text bubbles currently rendered.

        Empty-text nodes are skipped — ALF renders markdown blank lines as
        empty `div[id^="node-"]` bubbles (pure DOM spacers, no signal).
        Including them would bloat transcripts and add noise to scoring.
        """
        page = self._require_page()
        handles = await page.locator(SEL_ALF_MESSAGE_TEXT).all()
        messages: list[AlfMessage] = []
        for h in handles:
            node_id = await h.get_attribute("id")
            if not node_id:
                continue
            text = (await h.inner_text()).strip()
            if not text:
                continue
            messages.append(AlfMessage(node_id=node_id, text=text))
        return messages

    async def _collect_new_alf_messages(self) -> list[AlfMessage]:
        all_msgs = await self._collect_all_alf_messages()
        return [m for m in all_msgs if m.node_id not in self._seen_node_ids]

    async def _typing_idle(self) -> bool:
        """Return True iff the typing indicator wrapper has no child content."""
        page = self._require_page()
        try:
            # inner_text on an empty wrapper returns "" — use that as the
            # idle signal. If the wrapper is missing entirely, treat as idle.
            locator = page.locator(SEL_TYPING_WRAPPER).first
            count = await locator.count()
            if count == 0:
                return True
            inner = (await locator.inner_text(timeout=1_000)).strip()
            return inner == ""
        except PlaywrightTimeoutError:
            return True
        except Exception:  # noqa: BLE001
            return True

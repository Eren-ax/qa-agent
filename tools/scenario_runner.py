"""Phase 3 automation: drive a scenarios.json through ALF.

Wraps PlaywrightDriver with per-turn persona inference via Claude (Anthropic
SDK) and persists transcripts.jsonl under storage/runs/<run_id>/.

Usage:
    uv run python -m tools.scenario_runner --run-id <id> --channel-url <url>
    uv run python -m tools.scenario_runner --run-id <id> --channel-url <url> \
        --scenario-id <id>          # run only one
    uv run python -m tools.scenario_runner --run-id <id> --channel-url <url> \
        --headed --timeout 90

Requires ANTHROPIC_API_KEY in env (loaded from `.env` at repo root if present).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from tools.chat_driver import PlaywrightDriver
from tools.result_store import (
    SCHEMA_VERSION,
    AlfMessageRecord,
    Scenario,
    Transcript,
    Turn,
    append_transcript,
    read_scenarios,
    utcnow_iso,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

PERSONA_FILE = REPO_ROOT / "prompts" / "persona_archetypes.md"

# LLM access goes through Prism (Channel.io's Anthropic-compatible gateway) by
# default. Override via env if pointing at direct Anthropic or another gateway.
# Model IDs require a provider prefix on Prism (e.g. "anthropic/<model>").
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://prism.ch.dev")
PERSONA_MODEL = os.environ.get("PERSONA_MODEL", "anthropic/claude-sonnet-4-6")
PERSONA_MAX_TOKENS = 200  # persona messages are short; cap protects against runaway

# Per-archetype char caps (mirrors prompts/persona_archetypes.md Hard rule 4).
CHAR_CAPS = {
    "polite_clear": 80,
    "vague": 80,
    "impatient": 80,
    "confused": 100,
    "adversarial": 120,
}
DEFAULT_CHAR_CAP = 80

# Handoff phrase heuristics (mirrors skills/qa-agent/SKILL.md "Termination decision").
HANDOFF_PATTERNS = [
    re.compile(r"상담사.{0,30}(연결|전환|바꿔)"),
    re.compile(r"(연결|전환|바꿔).{0,30}상담사"),
    re.compile(r"담당자.{0,30}(전달|연결|확인 후)"),
]

# Persona-side closer detection. Short replies containing any of these tokens
# are treated as conversation-end signals.
CLOSER_TOKENS = (
    "감사합니다",
    "알겠습니다",
    "알겠어요",
    "됐어요",
    "괜찮아요",
    "그렇게 하죠",
)
CLOSER_MAX_LEN = 30


# ---- helpers ---------------------------------------------------------------


@dataclass
class HistoryEntry:
    role: str  # "user" or "alf"
    text: str


def load_persona_prompt() -> str:
    return PERSONA_FILE.read_text(encoding="utf-8")


def detect_handoff(alf_text: str) -> bool:
    if not alf_text:
        return False
    return any(p.search(alf_text) for p in HANDOFF_PATTERNS)


def detect_closer(persona_msg: str) -> bool:
    msg = persona_msg.strip()
    if len(msg) > CLOSER_MAX_LEN:
        return False
    return any(token in msg for token in CLOSER_TOKENS)


def truncate_to_cap(text: str, cap: int) -> str:
    text = text.strip()
    if len(text) <= cap:
        return text
    return text[:cap].rstrip() + "…"


def strip_meta_and_markdown(text: str) -> str:
    """Pick first non-blank line and strip markdown markers."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    line = lines[0]
    line = re.sub(r"^[-*#>]+\s*", "", line)
    line = re.sub(r"^`+|`+$", "", line)
    # Strip surrounding quotes the model sometimes adds.
    if (line.startswith('"') and line.endswith('"')) or (line.startswith("'") and line.endswith("'")):
        line = line[1:-1]
    return line.strip()


def looks_like_meta(text: str) -> bool:
    lower = text.lower()
    return lower.startswith(("as a", "i would", "as the", "as an", "the customer"))


def build_persona_user_prompt(
    *,
    scenario: Scenario,
    turns_remaining: int,
    history: list[HistoryEntry],
    client_tone: dict | None,
) -> str:
    criteria_summary = "\n".join(f"  - {c.description}" for c in scenario.success_criteria) or "  (none provided)"
    history_text = "\n".join(f"{h.role.upper()}: {h.text}" for h in history) or "(no history yet)"
    tone_text = ""
    if client_tone:
        tone_text = f"\nclient.tone (side info, do not mirror):\n{client_tone}\n"

    return f"""You are playing the **{scenario.persona_ref}** persona for QA scenario `{scenario.id}`.

scenario.intent: {scenario.intent}
scenario.success_criteria_summary:
{criteria_summary}
scenario.max_turns: {scenario.max_turns}
turns_remaining: {turns_remaining}
{tone_text}
Conversation history (turn 0 = your initial_message + ALF's reply):
{history_text}

Produce ONLY your next single customer message in Korean. No prefix, no role
label, no markdown, no quotes around it, no explanation. Just the raw message
text. Stay strictly in character per the {scenario.persona_ref} archetype's
rules in your system prompt."""


async def generate_persona_message(client: AsyncAnthropic, *, system_prompt: str, user_prompt: str) -> str:
    response = await client.messages.create(
        model=PERSONA_MODEL,
        max_tokens=PERSONA_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts = [b.text for b in response.content if hasattr(b, "text")]
    return "".join(parts)


def _finalize(
    scenario: Scenario,
    run_id: str,
    started_at: str,
    terminated_reason: str,
    turns: list[Turn],
    welcome_count: int,
    notes_extras: list[str],
) -> Transcript:
    notes = f"welcome_messages={welcome_count}"
    if notes_extras:
        notes += " | " + " | ".join(notes_extras)
    return Transcript(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        scenario_id=scenario.id,
        started_at=started_at,
        ended_at=utcnow_iso(),
        terminated_reason=terminated_reason,
        turns=turns,
        notes=notes,
    )


# ---- per-scenario driver loop ----------------------------------------------


async def run_one_scenario(
    scenario: Scenario,
    *,
    channel_url: str,
    run_id: str,
    anthropic_client: AsyncAnthropic,
    persona_system_prompt: str,
    client_tone: dict | None,
    headed: bool,
    timeout: float,
) -> Transcript:
    cap = CHAR_CAPS.get(scenario.persona_ref, DEFAULT_CHAR_CAP)
    started_at = utcnow_iso()
    driver = PlaywrightDriver(headless=not headed)
    turns: list[Turn] = []
    history: list[HistoryEntry] = []
    terminated_reason = "max_turns"
    notes_extras: list[str] = []
    welcome_count = 0

    try:
        welcome = await driver.open(channel_url)
        welcome_count = len(welcome)
        for w in welcome:
            history.append(HistoryEntry(role="alf", text=w.text))

        # Turn 0: send initial_message verbatim, no persona inference.
        user_ts = time.time()
        await driver.send(scenario.initial_message)
        try:
            replies = await driver.wait_reply(timeout=timeout)
        except TimeoutError:
            terminated_reason = "timeout"
            turns.append(
                Turn(
                    turn_index=0,
                    user_message=scenario.initial_message,
                    user_ts=user_ts,
                    alf_messages=[],
                    reply_latency_s=None,
                )
            )
            return _finalize(
                scenario,
                run_id,
                started_at,
                terminated_reason,
                turns,
                welcome_count,
                notes_extras,
            )

        history.append(HistoryEntry(role="user", text=scenario.initial_message))
        for r in replies:
            history.append(HistoryEntry(role="alf", text=r.text))

        turns.append(
            Turn(
                turn_index=0,
                user_message=scenario.initial_message,
                user_ts=user_ts,
                alf_messages=[AlfMessageRecord(node_id=r.node_id, text=r.text, ts=r.ts) for r in replies],
                reply_latency_s=replies[-1].ts - user_ts if replies else None,
            )
        )

        if replies and detect_handoff(replies[-1].text):
            terminated_reason = "escalated"
            return _finalize(
                scenario,
                run_id,
                started_at,
                terminated_reason,
                turns,
                welcome_count,
                notes_extras,
            )

        # Turn 1..max_turns: persona-driven loop.
        for turn_idx in range(1, scenario.max_turns + 1):
            turns_remaining = scenario.max_turns - turn_idx + 1

            # Pre-persona handoff check on the most recent ALF message.
            last_alf = next((h.text for h in reversed(history) if h.role == "alf"), "")
            if detect_handoff(last_alf):
                terminated_reason = "escalated"
                break

            # Persona inference (one retry on empty/meta).
            user_prompt = build_persona_user_prompt(
                scenario=scenario,
                turns_remaining=turns_remaining,
                history=history,
                client_tone=client_tone,
            )
            raw = await generate_persona_message(
                anthropic_client,
                system_prompt=persona_system_prompt,
                user_prompt=user_prompt,
            )
            cleaned = truncate_to_cap(strip_meta_and_markdown(raw), cap)

            if not cleaned or looks_like_meta(cleaned):
                notes_extras.append(f"turn {turn_idx}: persona retry triggered (empty or meta output)")
                retry_prompt = (
                    user_prompt + "\n\nREMINDER: Output ONLY the raw customer message in "
                    "Korean. No meta commentary, no English explanations, no "
                    "quotes. Stay in character."
                )
                raw = await generate_persona_message(
                    anthropic_client,
                    system_prompt=persona_system_prompt,
                    user_prompt=retry_prompt,
                )
                cleaned = truncate_to_cap(strip_meta_and_markdown(raw), cap)
                if not cleaned or looks_like_meta(cleaned):
                    terminated_reason = "error"
                    notes_extras.append(f"turn {turn_idx}: persona produced empty/meta twice; aborting")
                    break

            # Closer detection — record and stop.
            if detect_closer(cleaned):
                if turns_remaining <= 1:
                    terminated_reason = "max_turns"
                else:
                    terminated_reason = "completed"
                user_ts = time.time()
                turns.append(
                    Turn(
                        turn_index=turn_idx,
                        user_message=cleaned,
                        user_ts=user_ts,
                        alf_messages=[],
                        reply_latency_s=None,
                    )
                )
                break

            # Send + wait_reply.
            user_ts = time.time()
            await driver.send(cleaned)
            try:
                replies = await driver.wait_reply(timeout=timeout)
            except TimeoutError:
                terminated_reason = "timeout"
                turns.append(
                    Turn(
                        turn_index=turn_idx,
                        user_message=cleaned,
                        user_ts=user_ts,
                        alf_messages=[],
                        reply_latency_s=None,
                    )
                )
                break

            history.append(HistoryEntry(role="user", text=cleaned))
            for r in replies:
                history.append(HistoryEntry(role="alf", text=r.text))

            turns.append(
                Turn(
                    turn_index=turn_idx,
                    user_message=cleaned,
                    user_ts=user_ts,
                    alf_messages=[AlfMessageRecord(node_id=r.node_id, text=r.text, ts=r.ts) for r in replies],
                    reply_latency_s=replies[-1].ts - user_ts if replies else None,
                )
            )

            if replies and detect_handoff(replies[-1].text):
                terminated_reason = "escalated"
                break

    except Exception as exc:  # noqa: BLE001
        terminated_reason = "error"
        notes_extras.append(f"driver/runner exception: {type(exc).__name__}: {exc}")
    finally:
        try:
            await driver.close()
        except Exception:  # noqa: BLE001
            pass

    return _finalize(
        scenario,
        run_id,
        started_at,
        terminated_reason,
        turns,
        welcome_count,
        notes_extras,
    )


# ---- CLI -------------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[runner] ANTHROPIC_API_KEY not set in env (.env or shell)",
            file=sys.stderr,
        )
        return 2

    scenario_set = read_scenarios(args.run_id)
    scenarios = scenario_set.scenarios
    if args.scenario_id:
        scenarios = [s for s in scenarios if s.id == args.scenario_id]
        if not scenarios:
            print(
                f"[runner] scenario_id '{args.scenario_id}' not found in run " f"{args.run_id}",
                file=sys.stderr,
            )
            return 2

    persona_system_prompt = load_persona_prompt()
    client_tone = None  # v0: future enhancement — load from canonical_input.yaml

    anthropic_client = AsyncAnthropic(base_url=LLM_BASE_URL)

    print(
        f"[runner] run_id={args.run_id} channel={args.channel_url} "
        f"scenarios={len(scenarios)} model={PERSONA_MODEL} base_url={LLM_BASE_URL}"
    )
    for i, scenario in enumerate(scenarios, 1):
        print(f"[runner] [{i}/{len(scenarios)}] {scenario.id} " f"(persona={scenario.persona_ref})")
        try:
            transcript = await run_one_scenario(
                scenario,
                channel_url=args.channel_url,
                run_id=args.run_id,
                anthropic_client=anthropic_client,
                persona_system_prompt=persona_system_prompt,
                client_tone=client_tone,
                headed=args.headed,
                timeout=args.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[runner] [{i}/{len(scenarios)}] FATAL: {exc}", file=sys.stderr)
            continue
        append_transcript(args.run_id, transcript)
        print(f"[runner]   → {transcript.terminated_reason} " f"({len(transcript.turns)} turns)")

    print(f"[runner] done. transcripts at storage/runs/{args.run_id}/transcripts.jsonl")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="tools.scenario_runner",
        description="Drive scenarios.json through ALF with persona inference.",
    )
    p.add_argument("--run-id", required=True)
    p.add_argument("--channel-url", required=True)
    p.add_argument(
        "--scenario-id",
        default=None,
        help="run only this scenario (default: all in scenarios.json)",
    )
    p.add_argument("--headed", action="store_true")
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

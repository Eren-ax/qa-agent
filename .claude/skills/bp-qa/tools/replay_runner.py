"""Replay runner: replay actual user-chat conversations through ALF.

Unlike scenario_runner (which uses LLM personas), this replays the exact user
messages from a real conversation and records ALF's responses for comparison.

Usage:
    uv run python -m tools.replay_runner \
        --userchat-json /tmp/extracted_userchat.json \
        --channel-url https://test.channel.io \
        --output /tmp/replay_result.json \
        --headed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from tools.chat_driver import PlaywrightDriver
from tools.userchat_extractor import UserChatRecord, UserChatTurn
from tools.llm_client import create_llm_client, call_llm
from tools.user_style_analyzer import analyze_user_style
from tools.intent_tracker import extract_intent_from_first_message, should_end_conversation
from tools.message_formatter import post_process_llm_output

import os

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

ADAPTIVE_PROMPT_FILE = REPO_ROOT / "prompts" / "adaptive_user_replay.md"


@dataclass
class ReplayTurn:
    """One turn of replay execution."""

    turn: int
    user_message: str  # from original conversation
    alf_messages: list[str]  # ALF's response in replay
    reply_latency_s: float | None  # time from send to first ALF message
    timestamp: str  # replay execution time


@dataclass
class ReplayResult:
    """Complete replay execution result."""

    original_user_chat_id: str
    original_alf_session_id: str
    channel_url: str
    replay_turns: list[ReplayTurn]
    started_at: str
    ended_at: str
    adaptive_mode: bool = False
    notes: str = ""

    def to_json(self) -> dict:
        """Export to JSON."""
        return {
            'originalUserChatId': self.original_user_chat_id,
            'originalAlfSessionId': self.original_alf_session_id,
            'channelUrl': self.channel_url,
            'adaptiveMode': self.adaptive_mode,
            'replayTurns': [
                {
                    'turn': t.turn,
                    'userMessage': t.user_message,
                    'alfMessages': t.alf_messages,
                    'replyLatencyS': t.reply_latency_s,
                    'timestamp': t.timestamp
                }
                for t in self.replay_turns
            ],
            'startedAt': self.started_at,
            'endedAt': self.ended_at,
            'notes': self.notes
        }


async def adapt_user_message(
    *,
    original_turn: UserChatTurn,
    current_alf_response: str,
    user_style_section: str,
    primary_goal: str,
    achievement_indicators: list[str],
    client,
    provider: str,
    model: str
) -> str:
    """Adapt original user message to current ALF response context.

    Uses LLM to preserve intent while adapting to current conversation flow.
    Mimics the specific user's speech style.
    """
    # Load prompt template
    system_prompt_template = ADAPTIVE_PROMPT_FILE.read_text(encoding="utf-8")

    # Fill in user-specific information
    system_prompt = system_prompt_template.format(
        user_style_section=user_style_section,
        primary_goal=primary_goal,
        achievement_indicators=", ".join(f'"{ind}"' for ind in achievement_indicators)
    )

    user_prompt = f"""{{
  "original_turn": {{
    "user": "{original_turn.user_message}",
    "alf": "{original_turn.alf_message}"
  }},
  "current_alf_response": "{current_alf_response}"
}}"""

    # Override model to use Opus 4.7 for best quality
    adaptive_model = os.environ.get("ADAPTIVE_MODEL", "anthropic/claude-opus-4-7")

    adapted = await call_llm(
        client=client,
        provider=provider,
        model=adaptive_model,
        system=system_prompt,
        user=user_prompt,
        max_tokens=100,
        temperature=0.2  # Low temp for consistency
    )

    # Post-process to ensure natural ending
    adapted = post_process_llm_output(adapted, max_length=80)

    return adapted


async def replay_conversation(
    *,
    original: UserChatRecord,
    channel_url: str,
    headed: bool = False,
    timeout: int = 90,
    adaptive: bool = False,
    max_turns: int = None,
) -> ReplayResult:
    """Replay a user-chat conversation through ALF.

    Args:
        original: Original conversation from Langfuse
        channel_url: Test channel URL
        headed: Show browser window
        timeout: Per-message timeout in seconds
        adaptive: Use LLM to adapt user messages to current context
        max_turns: Stop after N turns (default: all)

    Returns:
        ReplayResult with ALF's responses
    """
    from datetime import datetime, timezone

    started_at = datetime.now(timezone.utc).isoformat()
    replay_turns: list[ReplayTurn] = []

    # Initialize LLM client for adaptive mode
    llm_client = None
    llm_provider = None
    llm_model = None
    user_style_section = None
    conversation_intent = None

    if adaptive:
        llm_client, llm_model, llm_provider = create_llm_client()
        adaptive_model = os.environ.get("ADAPTIVE_MODEL", "anthropic/claude-opus-4-7")
        print(f"[Adaptive mode] Using {llm_provider}/{adaptive_model} (temp=0.2)")

        # Analyze user's speech style
        user_messages = [t.user_message for t in original.turns if t.user_message.strip()]
        user_style = analyze_user_style(user_messages)
        user_style_section = user_style.to_prompt_section()
        print(f"[User style] {user_style.formality_level}, avg length {user_style.avg_length:.0f} chars")
        print(f"[User style] Common endings: {user_style.common_endings[:3]}")

        # Extract conversation intent
        first_message = original.turns[0].user_message
        conversation_intent = extract_intent_from_first_message(first_message)
        print(f"[Intent] {conversation_intent.primary_goal}")
        print(f"[Intent] Achievement indicators: {conversation_intent.achievement_indicators}")

    print(f"\n=== Replay: {original.user_chat_id} ===")
    print(f"Original session: {original.alf_session_id}")
    print(f"Channel: {channel_url}")
    print(f"Turns: {len(original.turns)}")
    print(f"Adaptive: {adaptive}")
    print(f"Max turns: {max_turns or 'all'}\n")

    driver = PlaywrightDriver(headless=not headed)

    try:
        # Open channel (first turn - may have welcome message)
        welcome_messages = await driver.open(channel_url)
        if welcome_messages:
            print(f"[Welcome] ALF sent {len(welcome_messages)} initial messages")

        for i, original_turn in enumerate(original.turns):
            turn_num = original_turn.turn

            # Check max_turns limit
            if max_turns and i >= max_turns:
                print(f"\n⏹️  Reached max_turns limit ({max_turns})")
                break

            # Determine user message (original or adapted)
            if i == 0 or not adaptive:
                # First turn or non-adaptive: use original message
                user_msg = original_turn.user_message
            else:
                # Adaptive mode: check if conversation should end
                prev_alf_response = ' '.join(replay_turns[-1].alf_messages)

                should_end, closing_message = should_end_conversation(
                    conversation_intent,
                    prev_alf_response,
                    i
                )

                if should_end:
                    print(f"[Turn {turn_num}] 🎯 Goal achieved or escalated - ending conversation")
                    print(f"  Closing: {closing_message}")
                    user_msg = closing_message
                else:
                    # Continue adapting
                    print(f"[Turn {turn_num}] Adapting user message...")
                    print(f"  Original: {original_turn.user_message}")

                    user_msg = await adapt_user_message(
                        original_turn=original_turn,
                        current_alf_response=prev_alf_response,
                        user_style_section=user_style_section,
                        primary_goal=conversation_intent.primary_goal,
                        achievement_indicators=conversation_intent.achievement_indicators,
                        client=llm_client,
                        provider=llm_provider,
                        model=llm_model
                    )

                    print(f"  Adapted:  {user_msg}")

            # Skip if user message is empty (some traces have empty first turn)
            if not user_msg.strip():
                print(f"[Turn {turn_num}] Skipping empty user message")
                continue

            print(f"[Turn {turn_num}] USER: {user_msg}")

            # Send user message
            send_start = time.time()
            await driver.send(user_msg)

            # Wait for ALF reply
            alf_messages = []
            reply_latency = None

            try:
                messages = await driver.wait_reply(timeout=timeout, quiet_period=2.0)
                reply_latency = time.time() - send_start

                for msg in messages:
                    alf_messages.append(msg.text)
                    print(f"[Turn {turn_num}] ALF:  {msg.text[:100]}...")

            except TimeoutError:
                print(f"[Turn {turn_num}] ⏱️  Timeout (no ALF reply within {timeout}s)")
                # Continue to next turn even if timeout

            replay_turns.append(ReplayTurn(
                turn=turn_num,
                user_message=user_msg,
                alf_messages=alf_messages,
                reply_latency_s=reply_latency,
                timestamp=datetime.now(timezone.utc).isoformat()
            ))

            # Check if this was a closing message - if so, stop
            if adaptive and user_msg in ["네 알겠습니다", "감사합니다", "알겠어요", "네 감사해요", "네 알겠어요"]:
                print(f"\n✅ Conversation ended naturally after turn {turn_num}")
                break

            # Small delay between turns
            await asyncio.sleep(1)

    finally:
        await driver.close()

    ended_at = datetime.now(timezone.utc).isoformat()

    notes = f"Replayed {len(replay_turns)} turns"
    if adaptive:
        notes += " (adaptive mode)"
    if max_turns:
        notes += f" (max {max_turns})"

    return ReplayResult(
        original_user_chat_id=original.user_chat_id,
        original_alf_session_id=original.alf_session_id,
        channel_url=channel_url,
        replay_turns=replay_turns,
        adaptive_mode=adaptive,
        started_at=started_at,
        ended_at=ended_at,
        notes=notes
    )


async def main():
    parser = argparse.ArgumentParser(
        description='Replay user-chat conversation through ALF'
    )
    parser.add_argument(
        '--userchat-json',
        required=True,
        help='Path to extracted user-chat JSON'
    )
    parser.add_argument(
        '--channel-url',
        required=True,
        help='Channel URL to test (e.g., https://test.channel.io)'
    )
    parser.add_argument(
        '--output',
        help='Output JSON path (default: print to stdout)'
    )
    parser.add_argument(
        '--headed',
        action='store_true',
        help='Show browser window'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=90,
        help='Per-message timeout in seconds (default: 90)'
    )
    parser.add_argument(
        '--adaptive',
        action='store_true',
        help='Use LLM to adapt user messages to current ALF responses (preserves intent)'
    )
    parser.add_argument(
        '--max-turns',
        type=int,
        default=None,
        help='Stop after N turns (default: all)'
    )

    args = parser.parse_args()

    # Load original conversation
    with open(args.userchat_json) as f:
        data = json.load(f)

    original = UserChatRecord(
        user_chat_id=data['userChatId'],
        alf_session_id=data['alfSessionId'],
        channel_id=data['channelId'],
        turns=[
            UserChatTurn(
                turn=t['turn'],
                user_message=t['user'],
                alf_message=t['alf'],
                timestamp=t['timestamp']
            )
            for t in data['turns']
        ]
    )

    # Replay
    result = await replay_conversation(
        original=original,
        channel_url=args.channel_url,
        headed=args.headed,
        timeout=args.timeout,
        adaptive=args.adaptive,
        max_turns=args.max_turns
    )

    # Output
    output_json = json.dumps(result.to_json(), ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output_json, encoding='utf-8')
        print(f"\n✅ Saved to {args.output}")
    else:
        print("\n=== Replay Result ===")
        print(output_json)


if __name__ == '__main__':
    asyncio.run(main())

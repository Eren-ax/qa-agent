"""User-chat extractor: Langfuse trace → structured conversation data.

Extracts ALF conversations from Langfuse traces for replay testing.

Usage:
    from tools.userchat_extractor import extract_from_langfuse

    conversation = extract_from_langfuse(
        user_chat_id="69f209716b807bddf86a",
        alf_session_id="17d5f164-5258-4caf-8cf9-45dfda5a5562"
    )
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


@dataclass
class UserChatTurn:
    """One turn of user-ALF conversation."""

    turn: int
    user_message: str
    alf_message: str
    timestamp: str


@dataclass
class UserChatRecord:
    """Complete user-chat conversation record from Langfuse."""

    user_chat_id: str
    alf_session_id: str
    channel_id: str
    turns: list[UserChatTurn]

    @classmethod
    def from_langfuse_json(cls, json_path: Path) -> UserChatRecord:
        """Load from Langfuse MCP dump JSON.

        Expects structure:
        {
          "data": [
            {
              "id": "trace_id",
              "sessionId": "alf_session_id",
              "timestamp": "2026-04-29T...",
              "observations": [
                {
                  "input": {"messages": [...]},
                  "output": {"content": "..."}
                }
              ]
            }
          ]
        }
        """
        with open(json_path) as f:
            raw = json.load(f)

        # Handle both MCP response {"data": [...]} and plain list [...]
        if isinstance(raw, dict) and 'data' in raw:
            data = raw['data']
        elif isinstance(raw, list):
            data = raw
        else:
            raise ValueError(f"Unknown JSON structure: {list(raw.keys()) if isinstance(raw, dict) else type(raw)}")

        if not data:
            raise ValueError("No traces found in JSON")

        # Extract metadata from first trace
        first_trace = data[0]
        alf_session_id = first_trace['sessionId']

        # Extract channel_id from tags (e.g., "channelId:236373")
        channel_id = None
        for tag in first_trace.get('tags', []):
            if tag.startswith('channelId:'):
                channel_id = tag.split(':', 1)[1]
                break

        # Extract user_chat_id from tags or metadata
        user_chat_id = first_trace.get('userId', 'unknown')

        # Sort traces by timestamp
        traces = sorted(data, key=lambda x: x['timestamp'])

        # Extract turns
        turns = []
        for i, trace in enumerate(traces, 1):
            observations = trace.get('observations', [])
            if not observations:
                continue

            gen = observations[0]
            messages = gen.get('input', {}).get('messages', [])
            output = gen.get('output', {})

            # Find user message (role=user)
            user_msg = None
            for msg in messages:
                if msg.get('role') == 'user' and msg.get('content'):
                    user_msg = msg['content']
                    break

            # ALF response (output content)
            alf_msg = output.get('content', '')

            if user_msg:
                turns.append(UserChatTurn(
                    turn=i,
                    user_message=user_msg,
                    alf_message=alf_msg,
                    timestamp=trace['timestamp']
                ))

        return cls(
            user_chat_id=user_chat_id,
            alf_session_id=alf_session_id,
            channel_id=channel_id or 'unknown',
            turns=turns
        )

    def to_json(self) -> dict:
        """Export to JSON-serializable dict."""
        return {
            'userChatId': self.user_chat_id,
            'alfSessionId': self.alf_session_id,
            'channelId': self.channel_id,
            'turns': [
                {
                    'turn': t.turn,
                    'user': t.user_message,
                    'alf': t.alf_message,
                    'timestamp': t.timestamp
                }
                for t in self.turns
            ]
        }


def extract_from_langfuse(
    langfuse_json_path: str | Path,
) -> UserChatRecord:
    """Extract conversation from Langfuse MCP dump.

    Args:
        langfuse_json_path: Path to Langfuse traces JSON file

    Returns:
        UserChatRecord with parsed conversation
    """
    return UserChatRecord.from_langfuse_json(Path(langfuse_json_path))


# CLI for testing
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Extract user-chat from Langfuse trace')
    parser.add_argument('--langfuse-json', required=True, help='Path to Langfuse traces JSON')
    parser.add_argument('--output', help='Output JSON path (default: print to stdout)')

    args = parser.parse_args()

    record = extract_from_langfuse(args.langfuse_json)

    output = json.dumps(record.to_json(), ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"Saved to {args.output}")
    else:
        print(output)

"""Extract initial user message from Channel.io UserChat URL.

Uses trace-alf-userchat skill to fetch conversation and extract first user message.

Usage:
    python3 -m tools.extract_userchat_initial_message \
        --url "https://desk.channel.io/charan/user-chats/69e6e6d69f3e263c3ac0"
"""

import argparse
import json
import re
import sys
from pathlib import Path


def extract_user_chat_id(url: str) -> str | None:
    """Extract UserChat ID from URL."""
    match = re.search(r'/user-chats/([a-f0-9]+)', url)
    return match.group(1) if match else None


def get_initial_message_from_trace(user_chat_id: str) -> str | None:
    """Get initial user message using trace-alf-userchat skill.

    TODO: This requires calling the skill programmatically.
    For now, we'll need to use Langfuse MCP directly.
    """
    # Placeholder - need to implement Langfuse query
    return None


def extract_from_url(url: str) -> dict:
    """Extract initial message and metadata from UserChat URL.

    Returns:
        {
            "user_chat_id": str,
            "url": str,
            "initial_message": str,
            "error": str | None
        }
    """
    user_chat_id = extract_user_chat_id(url)
    if not user_chat_id:
        return {
            "user_chat_id": None,
            "url": url,
            "initial_message": None,
            "error": "Invalid URL format"
        }

    # TODO: Implement actual extraction using Langfuse MCP
    # For now, return placeholder
    return {
        "user_chat_id": user_chat_id,
        "url": url,
        "initial_message": f"[TODO: Extract from Langfuse for {user_chat_id}]",
        "error": "Not implemented - requires Langfuse MCP integration"
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract initial user message from UserChat URL"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="UserChat URL (e.g., https://desk.channel.io/charan/user-chats/xxx)"
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path (optional)"
    )

    args = parser.parse_args()

    result = extract_from_url(args.url)

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved to: {output_path}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    sys.exit(main())

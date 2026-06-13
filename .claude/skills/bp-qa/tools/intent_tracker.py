"""Intent tracker for conversation goal detection.

Tracks whether the user's original intent has been satisfied by ALF's responses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConversationIntent:
    """User's goal in this conversation."""

    primary_goal: str  # e.g., "가격 확인", "예약", "환불"
    goal_achieved: bool = False
    achievement_indicators: list[str] = None  # Keywords that signal goal achieved

    def __post_init__(self):
        if self.achievement_indicators is None:
            self.achievement_indicators = []


def extract_intent_from_first_message(first_message: str) -> ConversationIntent:
    """Extract user's primary goal from their first message.

    Args:
        first_message: User's first message in conversation

    Returns:
        ConversationIntent with detected goal and indicators
    """
    # Intent patterns
    intent_patterns = {
        "가격 확인": {
            "keywords": ["가격", "얼마", "비용", "금액"],
            "indicators": ["원", "만원", "가격은", "비용은"]
        },
        "예약": {
            "keywords": ["예약", "방문", "일정"],
            "indicators": ["예약", "확정", "날짜", "시간"]
        },
        "환불": {
            "keywords": ["환불", "취소", "반품"],
            "indicators": ["환불", "처리", "계좌"]
        },
        "효과 확인": {
            "keywords": ["효과", "괜찮", "추천"],
            "indicators": ["효과", "추천", "적합"]
        },
        "재입고": {
            "keywords": ["재입고", "품절", "입고"],
            "indicators": ["입고", "예정", "알림"]
        },
        "문의": {
            "keywords": ["문의", "알려", "궁금"],
            "indicators": []  # Generic, hard to detect achievement
        }
    }

    # Detect intent
    detected_intent = "문의"  # default
    indicators = []

    for intent, patterns in intent_patterns.items():
        if any(kw in first_message for kw in patterns["keywords"]):
            detected_intent = intent
            indicators = patterns["indicators"]
            break

    return ConversationIntent(
        primary_goal=detected_intent,
        goal_achieved=False,
        achievement_indicators=indicators
    )


def check_goal_achieved(
    intent: ConversationIntent,
    alf_response: str
) -> bool:
    """Check if ALF's response satisfies the user's goal.

    Args:
        intent: User's conversation intent
        alf_response: ALF's latest response

    Returns:
        True if goal appears to be achieved
    """
    if not intent.achievement_indicators:
        return False

    # Check if response contains achievement indicators
    matches = sum(1 for ind in intent.achievement_indicators if ind in alf_response)

    # Need at least 1 indicator to consider achieved
    return matches >= 1


def should_end_conversation(
    intent: ConversationIntent,
    alf_response: str,
    turn_count: int
) -> tuple[bool, str]:
    """Decide if conversation should end based on goal achievement.

    Args:
        intent: User's conversation intent
        alf_response: ALF's latest response
        turn_count: Current turn number

    Returns:
        (should_end, closing_message)
    """
    # Check goal achievement
    if check_goal_achieved(intent, alf_response):
        # Goal achieved - end with appropriate closer
        closers = [
            "네 알겠습니다",
            "감사합니다",
            "알겠어요",
            "네 감사해요"
        ]
        return True, closers[0]

    # Check if ALF escalated to human
    if any(phrase in alf_response for phrase in ["상담사", "담당자", "연락", "문의"]):
        # ALF handed off - acknowledge
        return True, "네 알겠습니다"

    # Check if too many turns without resolution
    if turn_count >= 5:
        # Give up
        return True, "네 알겠어요"

    return False, ""


# CLI for testing
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tools.intent_tracker <first_message>")
        sys.exit(1)

    first_message = sys.argv[1]
    intent = extract_intent_from_first_message(first_message)

    print(f"Detected intent: {intent.primary_goal}")
    print(f"Achievement indicators: {intent.achievement_indicators}")

    # Test with sample ALF response
    test_responses = [
        "가격은 399,000원입니다",
        "예약 가능합니다. 날짜 알려주세요",
        "상담사에게 연결해드리겠습니다"
    ]

    for i, resp in enumerate(test_responses, 1):
        should_end, closer = should_end_conversation(intent, resp, i)
        print(f"\nALF Response {i}: {resp}")
        print(f"  Goal achieved: {check_goal_achieved(intent, resp)}")
        print(f"  Should end: {should_end}")
        if should_end:
            print(f"  Closing: {closer}")

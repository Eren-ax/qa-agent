"""Message formatter for natural speech output.

Prevents awkward truncation and ensures messages end naturally.
"""

from __future__ import annotations

import re


def is_natural_ending(text: str) -> bool:
    """Check if text ends naturally (not truncated).

    Args:
        text: Text to check

    Returns:
        True if ending looks natural
    """
    text = text.strip()

    # Natural endings
    natural_patterns = [
        r'[요예네까]$',  # 요체/해요체 endings
        r'[다]$',  # 합니다체
        r'[?!.]$',  # Punctuation
        r'[0-9]$',  # Numbers (e.g., "010-1234-5678")
        r'[요예네까]\?$',  # Question forms
    ]

    for pattern in natural_patterns:
        if re.search(pattern, text):
            return True

    # Unnatural endings (truncated)
    unnatural_patterns = [
        r'\.\.\.$',  # Ellipsis
        r'[가-힣]{2}$',  # Likely mid-word (2 chars at end, not ending particle)
    ]

    for pattern in unnatural_patterns:
        if re.search(pattern, text):
            return False

    # Default: assume unnatural if not explicitly natural
    return False


def truncate_to_natural_ending(text: str, max_length: int = 80) -> str:
    """Truncate text to max_length but at a natural break point.

    Args:
        text: Text to truncate
        max_length: Maximum length in characters

    Returns:
        Truncated text ending naturally
    """
    if len(text) <= max_length:
        return text

    # Find natural break points (sentence endings, particles)
    break_points = []

    # Find all sentence endings within max_length
    for pattern in [r'[요예네까]', r'다', r'[?!.]', r'[0-9]{4}']:
        for match in re.finditer(pattern, text[:max_length + 10]):
            break_points.append(match.end())

    if not break_points:
        # No natural break found - just cut at max_length
        return text[:max_length].rstrip()

    # Use the latest break point that fits
    best_break = max(bp for bp in break_points if bp <= max_length)
    return text[:best_break].strip()


def ensure_natural_ending(text: str, max_length: int = 80) -> str:
    """Ensure text ends naturally, truncating if necessary.

    Args:
        text: Generated text
        max_length: Maximum allowed length

    Returns:
        Text with natural ending
    """
    text = text.strip()

    # If within limit and natural, return as-is
    if len(text) <= max_length and is_natural_ending(text):
        return text

    # If over limit, truncate naturally
    if len(text) > max_length:
        return truncate_to_natural_ending(text, max_length)

    # If within limit but unnatural ending, try to fix
    # Remove trailing ellipsis
    text = re.sub(r'\.\.\.$', '', text).strip()

    # If still unnatural, truncate to last natural point
    if not is_natural_ending(text):
        return truncate_to_natural_ending(text, len(text))

    return text


def post_process_llm_output(text: str, max_length: int = 80) -> str:
    """Clean up LLM-generated message.

    Removes common issues:
    - Leading politeness ("네,") when not a closer
    - Formal endings
    - Ellipsis
    - Truncation artifacts

    Args:
        text: Raw LLM output
        max_length: Maximum length

    Returns:
        Cleaned, natural message
    """
    text = text.strip()

    # Don't clean closers - they should stay as-is
    closers = ["네 알겠습니다", "감사합니다", "알겠어요", "네 감사해요", "네 알겠어요", "됐어요"]
    if text in closers:
        return text

    # Remove leading "네," or "아," (but not standalone "네")
    text = re.sub(r'^(네|아),\s*', '', text)

    # Remove formal endings (습니다 → 요)
    text = re.sub(r'습니다\.?$', '요', text)
    text = re.sub(r'ㅂ니다\.?$', '요', text)

    # Remove trailing periods (unless it's ellipsis)
    if not text.endswith('...'):
        text = re.sub(r'\.$', '', text)

    # Ensure natural ending
    text = ensure_natural_ending(text, max_length)

    return text


# CLI for testing
if __name__ == '__main__':
    test_cases = [
        ("300샷의 효과가 어떤지 궁금합니...", 80),
        ("네, 주문번호는 12345입니다.", 80),
        ("환불 가능한가요? 제가 구매한 상품이 불량이라서 환불을 원합니다.", 30),
        ("010-1234-5678", 80),
        ("감사합니다.", 80),
    ]

    print("=== Message Formatter Test ===\n")

    for text, max_len in test_cases:
        natural = is_natural_ending(text)
        processed = post_process_llm_output(text, max_len)

        print(f"Original:  {text}")
        print(f"  Natural ending: {natural}")
        print(f"  Length: {len(text)} chars")
        print(f"Processed: {processed}")
        print(f"  Length: {len(processed)} chars")
        print()

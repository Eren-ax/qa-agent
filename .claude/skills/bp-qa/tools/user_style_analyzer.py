"""User speech style analyzer.

Extracts and analyzes the speaking patterns from a user's actual messages
to enable LLM to mimic their exact style.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class UserStyle:
    """Analyzed speech patterns of a specific user."""

    user_messages: list[str]  # Actual messages from this user
    avg_length: float
    common_endings: list[str]  # Most frequent 2-3 char endings
    common_particles: list[str]  # 근데, 그럼, 혹시, etc.
    sentence_patterns: list[str]  # Question/statement patterns
    formality_level: str  # "formal", "casual", "very-casual"

    def to_prompt_section(self) -> str:
        """Generate prompt section describing this user's style."""

        examples_text = "\n".join(f'  - "{msg}"' for msg in self.user_messages[:5])

        endings_text = ", ".join(f'"{e}"' for e in self.common_endings[:5])
        particles_text = ", ".join(f'"{p}"' for p in self.common_particles[:5])

        return f"""## THIS USER'S ACTUAL SPEECH STYLE (MANDATORY TO MIMIC)

**Real messages from this exact user:**
{examples_text}

**Observed patterns:**
- Average length: {self.avg_length:.0f} characters
- Common endings: {endings_text}
- Common particles: {particles_text}
- Formality: {self.formality_level}

**CRITICAL RULE:**
You MUST mimic THIS SPECIFIC USER's style, not generic customer style.
Copy their endings, length, and particles EXACTLY as shown above.
"""


def analyze_user_style(user_messages: list[str]) -> UserStyle:
    """Analyze speech patterns from user's actual messages.

    Args:
        user_messages: List of messages the user actually sent

    Returns:
        UserStyle with extracted patterns
    """
    if not user_messages:
        raise ValueError("No user messages to analyze")

    # Remove empty messages
    user_messages = [m.strip() for m in user_messages if m.strip()]

    # Average length
    avg_length = sum(len(m) for m in user_messages) / len(user_messages)

    # Extract endings (last 2-3 characters)
    endings = []
    for msg in user_messages:
        if len(msg) >= 2:
            # Try 3-char ending first (e.g., "나요?")
            if len(msg) >= 3:
                endings.append(msg[-3:])
            else:
                endings.append(msg[-2:])

    # Count most common endings
    ending_counter = Counter(endings)
    common_endings = [e for e, _ in ending_counter.most_common(5)]

    # Extract particles (근데, 그럼, 혹시, etc.)
    particles = []
    particle_patterns = [
        r'\b근데\b', r'\b그럼\b', r'\b혹시\b', r'\b아\b',
        r'\b그래서\b', r'\b그리고\b', r'\b그치만\b'
    ]
    for msg in user_messages:
        for pattern in particle_patterns:
            if re.search(pattern, msg):
                particles.append(re.search(pattern, msg).group())

    common_particles = list(set(particles))

    # Detect formality level
    formality = detect_formality(user_messages)

    # Extract sentence patterns (question vs statement)
    sentence_patterns = []
    for msg in user_messages:
        if '?' in msg or msg.endswith('요') or msg.endswith('나요'):
            sentence_patterns.append('question')
        else:
            sentence_patterns.append('statement')

    return UserStyle(
        user_messages=user_messages,
        avg_length=avg_length,
        common_endings=common_endings,
        common_particles=common_particles,
        sentence_patterns=sentence_patterns,
        formality_level=formality
    )


def detect_formality(messages: list[str]) -> str:
    """Detect formality level from messages.

    Returns:
        "formal" (합니다체), "casual" (해요체), or "very-casual" (해체)
    """
    formal_count = 0
    casual_count = 0
    very_casual_count = 0

    for msg in messages:
        if re.search(r'습니다|ㅂ니다', msg):
            formal_count += 1
        elif re.search(r'해요|어요|아요|네요', msg):
            casual_count += 1
        elif re.search(r'해\s*$|어\s*$|아\s*$', msg):
            very_casual_count += 1

    if formal_count > casual_count and formal_count > very_casual_count:
        return "formal"
    elif very_casual_count > casual_count:
        return "very-casual"
    else:
        return "casual"


# CLI for testing
if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m tools.user_style_analyzer <userchat_json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)

    user_messages = [t['user'] for t in data['turns'] if t['user'].strip()]

    style = analyze_user_style(user_messages)

    print(style.to_prompt_section())

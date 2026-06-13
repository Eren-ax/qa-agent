"""Calculate outcome score (Layer 1: Customer Satisfaction).

Measures whether the customer got what they wanted.
Score range: 0~7.0

Signals:
- Resolution (closed): 2.0
- CSAT (≥4): 1.5
- Last message positive: 1.0
- No repeat inquiry: 1.0
- Pingpong penalty (>10 turns): -0.3
- Response time penalty (>1h): -0.5
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from tools.llm_client import create_llm_client, call_llm


def calculate_outcome_score(
    row: pd.Series,
    all_data: Optional[pd.DataFrame] = None,
    analyze_last_message: bool = False,
    check_repeat_inquiry: bool = False,
) -> dict:
    """Calculate Layer 1: Customer Satisfaction score.

    Args:
        row: Single case from clustering Excel
        all_data: Full dataset (needed for repeat inquiry check)
        analyze_last_message: Use LLM to analyze sentiment (costs $0.003/case)
        check_repeat_inquiry: Check for repeat inquiries (computationally expensive)

    Returns:
        {
            'scores': {
                'resolved': float,
                'csat': float,
                'last_message_positive': float,
                'no_repeat_inquiry': float,
                'pingpong_penalty': float,
                'response_time_penalty': float,
            },
            'total': float  # Sum of all scores (0~7.0)
        }
    """
    scores = {}

    # 1. Resolution (2.0 points)
    scores['resolved'] = 2.0 if row.get('state') == 'closed' else 0.0

    # 2. CSAT (1.5 points)
    csat = row.get('profile.csat', 0)
    scores['csat'] = 1.5 if pd.notna(csat) and csat >= 4 else 0.0

    # 3. Last message positive (1.0 point) - Optional, requires LLM
    if analyze_last_message and 'enhanced_text' in row and pd.notna(row['enhanced_text']):
        scores['last_message_positive'] = _analyze_last_message_sentiment(row['enhanced_text'])
    else:
        scores['last_message_positive'] = 0.0

    # 4. No repeat inquiry (1.0 point) - Optional, requires full dataset
    if check_repeat_inquiry and all_data is not None:
        has_repeat = _check_repeat_inquiry(row, all_data)
        scores['no_repeat_inquiry'] = 0.0 if has_repeat else 1.0
    else:
        # Default: assume no repeat (conservative)
        scores['no_repeat_inquiry'] = 1.0

    # 5. Pingpong penalty (-0.3 for >10 turns)
    reply_count = row.get('replyCount', 0)
    scores['pingpong_penalty'] = -0.3 if reply_count > 10 else 0.0

    # 6. Response time penalty (-0.5 for >1h)
    time_to_answer = row.get('timeToFirstAnswer', 0)
    scores['response_time_penalty'] = -0.5 if time_to_answer > 3600 else 0.0

    return {
        'scores': scores,
        'total': sum(scores.values())
    }


def _analyze_last_message_sentiment(enhanced_text: str) -> float:
    """Analyze sentiment of last user message using LLM.

    Returns:
        1.0: Clear satisfaction ("감사합니다", "해결됐어요")
        0.5: Neutral closing ("알겠습니다", "확인했어요")
        0.0: Dissatisfaction ("이게 뭐죠", "안 되는데요")
    """
    # Extract last USER message
    last_user_msg = _extract_last_user_message(enhanced_text)

    if not last_user_msg:
        return 0.0

    # Quick heuristic check (no LLM needed for obvious cases)
    positive_keywords = ['감사', '고마', '해결', '됐어요', '확인했습니다', '알겠습니다']
    negative_keywords = ['안 됐', '안돼', '이게 뭐', '불만', '화나', '짜증']

    text_lower = last_user_msg.lower()
    if any(kw in text_lower for kw in positive_keywords):
        return 1.0
    if any(kw in text_lower for kw in negative_keywords):
        return 0.0

    # LLM analysis for ambiguous cases
    try:
        llm_client, model, provider = create_llm_client()
        prompt = f"""고객의 마지막 발화를 분석하여 만족도를 판단하세요.

발화: "{last_user_msg}"

점수 기준:
- 1.0: 명확한 감사/만족 표현
- 0.5: 중립적 종료
- 0.0: 불만족 표현

Output: 0.0, 0.5, or 1.0 only (no explanation)"""

        response = call_llm(
            llm_client=llm_client,
            provider=provider,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10
        )

        score = float(response.strip())
        return max(0.0, min(1.0, score))

    except Exception as e:
        # Fallback: neutral
        print(f"Warning: LLM sentiment analysis failed: {e}")
        return 0.5


def _extract_last_user_message(enhanced_text: str) -> str:
    """Extract last user message from conversation text.

    Expected format:
        USER: message1
        AGENT: response1
        USER: message2
        AGENT: response2
        ...
    """
    if not enhanced_text:
        return ""

    # Split by lines
    lines = enhanced_text.split('\n')

    # Find last USER: line
    last_user = None
    for line in reversed(lines):
        line = line.strip()
        if line.startswith('USER:') or line.startswith('고객:'):
            last_user = line.split(':', 1)[1].strip() if ':' in line else line
            break

    return last_user or ""


def _check_repeat_inquiry(row: pd.Series, all_data: pd.DataFrame) -> bool:
    """Check if user made similar inquiry within 7 days.

    Args:
        row: Current case
        all_data: Full dataset

    Returns:
        True if repeat inquiry found, False otherwise
    """
    user_id = row.get('userId')
    if pd.isna(user_id):
        return False

    case_date = pd.to_datetime(row.get('createdAt'))
    if pd.isna(case_date):
        return False

    # Find other cases by same user
    user_cases = all_data[all_data['userId'] == user_id].copy()

    for _, other in user_cases.iterrows():
        if other['id'] == row['id']:
            continue

        other_date = pd.to_datetime(other.get('createdAt'))
        if pd.isna(other_date):
            continue

        # Within 7 days after this case
        days_diff = (other_date - case_date).days
        if 0 < days_diff <= 7:
            # Check intent similarity (simple keyword overlap)
            if _similar_intent(row.get('label', ''), other.get('label', '')):
                return True

    return False


def _similar_intent(intent1: str, intent2: str) -> bool:
    """Check if two intents are similar (simple keyword overlap)."""
    if not intent1 or not intent2:
        return False

    # Extract keywords (remove common words)
    stopwords = ['문의', '요청', '확인', '관련', '에', '대한', '하고', '싶어요']

    def extract_keywords(text: str) -> set:
        words = re.findall(r'\w+', text.lower())
        return {w for w in words if w not in stopwords and len(w) > 1}

    keywords1 = extract_keywords(intent1)
    keywords2 = extract_keywords(intent2)

    if not keywords1 or not keywords2:
        return False

    # Jaccard similarity > 0.5
    intersection = keywords1 & keywords2
    union = keywords1 | keywords2

    return len(intersection) / len(union) > 0.5 if union else False


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) < 2:
        print("Usage: python outcome_scorer.py <clustered_excel>")
        sys.exit(1)

    df = pd.read_excel(sys.argv[1])
    df = df[df['cluster_id'].notna()].head(10)

    print("Testing outcome scorer on 10 cases...\n")

    for _, row in df.iterrows():
        result = calculate_outcome_score(row)
        print(f"Case {row['id'][:8]}... (Cluster {row['cluster_id']})")
        print(f"  State: {row.get('state')}, CSAT: {row.get('profile.csat')}")
        print(f"  Outcome score: {result['total']:.1f}/7.0")
        print(f"  Breakdown: {result['scores']}")
        print()

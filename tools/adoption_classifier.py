"""Classify task adoption tier (Layer 3: Implementation Difficulty).

Automatically classifies how ALF should handle each case:
- RAG: Knowledge base search (few days ~ weeks)
- Text Task: Conditional logic needed (few weeks)
- Function Task: External API/admin integration (few months)

Uses heuristic + LLM hybrid approach:
1. Heuristic classification (fast, free)
2. LLM validation for uncertain cases (accurate, costs $0.001/case with haiku)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from tools.llm_client import create_llm_client, call_llm


@dataclass
class TaskClassification:
    """Task type classification result."""

    task_type: str  # "RAG" | "Text Task" | "Function Task"
    confidence: float  # 0.0 ~ 1.0
    reason: str  # Why this classification


def classify_task_type(
    intent: str,
    enhanced_text: str,
    alf_triggered: bool = False,
    use_llm_fallback: bool = True,
) -> TaskClassification:
    """Classify task adoption tier.

    Args:
        intent: Customer intent/label
        enhanced_text: Full conversation text
        alf_triggered: Whether ALF was triggered
        use_llm_fallback: Use LLM for uncertain cases (default: True)

    Returns:
        TaskClassification with task_type, confidence, reason
    """
    # 1st pass: Heuristic classification
    heuristic_result = _heuristic_classify(intent, enhanced_text, alf_triggered)

    # 2nd pass: LLM validation for low confidence
    if use_llm_fallback and heuristic_result.confidence < 0.7:
        try:
            llm_result = _llm_classify(intent, enhanced_text)
            return llm_result
        except Exception as e:
            print(f"Warning: LLM classification failed, using heuristic: {e}")
            return heuristic_result

    return heuristic_result


def _heuristic_classify(
    intent: str,
    enhanced_text: str,
    alf_triggered: bool,
) -> TaskClassification:
    """Heuristic classification using keywords and patterns.

    Fast and free, ~70% accuracy expected.
    """
    text = f"{intent} {enhanced_text}".lower()

    # Function Task keywords (highest priority)
    function_keywords = {
        # Order/Payment operations
        '주문 취소': 0.9,
        '주문취소': 0.9,
        '반품': 0.8,
        '교환': 0.8,
        '환불': 0.9,
        '결제': 0.7,
        '취소': 0.7,

        # Inventory/Stock operations
        '재고 확인': 0.9,
        '재고': 0.7,
        '입고': 0.6,

        # Point/Coupon operations
        '포인트 적립': 0.9,
        '포인트': 0.7,
        '쿠폰 발급': 0.9,
        '쿠폰': 0.7,
        '적립금': 0.8,

        # Member operations
        '회원 등급': 0.8,
        '등급': 0.6,
        '멤버십': 0.7,

        # System operations
        'api': 0.9,
        '연동': 0.8,
        '어드민': 0.9,
        '시스템': 0.7,
        '데이터베이스': 0.9,
        'db': 0.9,
    }

    max_function_confidence = 0.0
    matched_function_keywords = []

    for keyword, confidence in function_keywords.items():
        if keyword in text:
            max_function_confidence = max(max_function_confidence, confidence)
            matched_function_keywords.append(keyword)

    if max_function_confidence >= 0.7:
        return TaskClassification(
            task_type="Function Task",
            confidence=max_function_confidence,
            reason=f"키워드 매칭: {matched_function_keywords[:3]}"
        )

    # Text Task keywords (conditional logic)
    text_task_patterns = [
        (r'경우', 0.6),
        (r'상황', 0.6),
        (r'조건', 0.7),
        (r'만약', 0.7),
        (r'~면', 0.6),
        (r'~하면', 0.6),
        (r'상태별', 0.8),
        (r'타입별', 0.8),
        (r'케이스별', 0.8),
        (r'등급별', 0.7),
        (r'단계', 0.6),
    ]

    max_text_confidence = 0.0
    matched_text_patterns = []

    for pattern, confidence in text_task_patterns:
        if re.search(pattern, text):
            max_text_confidence = max(max_text_confidence, confidence)
            matched_text_patterns.append(pattern)

    if max_text_confidence >= 0.6:
        return TaskClassification(
            task_type="Text Task",
            confidence=max_text_confidence,
            reason=f"조건 분기 패턴 감지: {matched_text_patterns[:3]}"
        )

    # RAG (default)
    rag_keywords = {
        'faq': 0.8,
        '문의': 0.6,
        '정보': 0.6,
        '어떻게': 0.6,
        '무엇': 0.6,
        '어디': 0.6,
        '언제': 0.6,
        '왜': 0.6,
        '가능': 0.6,
        '방법': 0.7,
    }

    max_rag_confidence = 0.5  # Base confidence
    matched_rag_keywords = []

    for keyword, confidence in rag_keywords.items():
        if keyword in text:
            max_rag_confidence = max(max_rag_confidence, confidence)
            matched_rag_keywords.append(keyword)

    # Boost confidence if ALF was triggered (likely RAG-solvable)
    if alf_triggered:
        max_rag_confidence = max(max_rag_confidence, 0.8)
        reason = f"ALF 작동 + 단순 정보 제공"
        if matched_rag_keywords:
            reason += f" (키워드: {matched_rag_keywords[:2]})"
    else:
        reason = f"지식베이스 검색 가능"
        if matched_rag_keywords:
            reason += f" (키워드: {matched_rag_keywords[:2]})"
        else:
            reason += " (기본 추정)"
            max_rag_confidence = 0.5  # Lower confidence without evidence

    return TaskClassification(
        task_type="RAG",
        confidence=max_rag_confidence,
        reason=reason
    )


def _llm_classify(intent: str, enhanced_text: str) -> TaskClassification:
    """LLM-based classification for uncertain cases.

    Uses Claude Haiku for cost efficiency (~$0.001/case).
    """
    # Truncate enhanced_text to save tokens
    text_preview = enhanced_text[:800] if len(enhanced_text) > 800 else enhanced_text

    prompt = f"""다음 상담 케이스를 ALF 처리 방식으로 분류하세요.

고객 의도: {intent}

대화 내용:
{text_preview}

분류 기준:
1. RAG: 지식베이스 검색으로 답변 가능
   예: FAQ, 상품 정보, 매장 위치, 운영 시간, 정책 안내

2. Text Task: 조건 분기 필요
   예: 주문 상태별 안내, 회원 등급별 혜택, 상황별 대응

3. Function Task: 외부 API/어드민 연동 필요
   예: 주문 취소, 재고 확인, 포인트 적립, 쿠폰 발급

Output JSON only:
{{"task_type": "RAG|Text Task|Function Task", "confidence": 0.0-1.0, "reason": "분류 근거 (한 문장)"}}"""

    try:
        llm_client, model, provider = create_llm_client()
        # Use Haiku for cost efficiency
        response = call_llm(
            llm_client=llm_client,
            provider=provider,
            model="anthropic/claude-haiku-4-5",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )

        import json
        result = json.loads(response.strip())

        return TaskClassification(
            task_type=result['task_type'],
            confidence=float(result['confidence']),
            reason=result['reason']
        )

    except Exception as e:
        # Fallback to RAG on error
        return TaskClassification(
            task_type="RAG",
            confidence=0.5,
            reason=f"LLM 분류 실패, 기본값 사용: {e}"
        )


if __name__ == "__main__":
    # Test cases
    test_cases = [
        {
            "intent": "주문 취소 요청",
            "text": "어제 주문한 상품을 취소하고 싶어요",
            "alf": False,
        },
        {
            "intent": "배송 정책 문의",
            "text": "배송비는 얼마인가요? 무료배송 조건이 궁금합니다",
            "alf": True,
        },
        {
            "intent": "회원 등급별 혜택",
            "text": "회원 등급에 따라 할인율이 다른가요?",
            "alf": False,
        },
    ]

    print("Testing adoption classifier...\n")

    for i, case in enumerate(test_cases, 1):
        print(f"Case {i}: {case['intent']}")
        result = classify_task_type(
            intent=case['intent'],
            enhanced_text=case['text'],
            alf_triggered=case['alf'],
            use_llm_fallback=False  # Test heuristic only
        )
        print(f"  → {result.task_type} (confidence: {result.confidence:.2f})")
        print(f"     Reason: {result.reason}")
        print()

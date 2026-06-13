"""Success Criteria Templates for QA Scenario Generation

L3 Sub-intent별 자동 생성 템플릿. 버티컬별(패션/의료/전자제품) 특화.
"""

from __future__ import annotations

# E-commerce (패션) 템플릿
ECOMMERCE_TEMPLATES = {
    "사이즈_핏_문의": {
        "must_include": ["사이즈표", "실측", "교환"],
        "must_not_include": ["확인 후", "담당자"],
        "eval_prompt": "ALF가 사이즈표 링크 또는 실측 정보를 제공하고 교환 정책을 안내했는가?",
    },
    "재고_품절_문의": {
        "must_include": ["재입고 알림", "인스타그램"],
        "must_not_include": ["확인 후 연락"],
        "eval_prompt": "ALF가 재입고 알림 신청 방법과 인스타그램 공지 채널을 안내했는가?",
    },
    "배송지_변경": {
        "must_include": ["배송지 변경", "주문번호", "출고 전"],
        "must_not_include": ["불가능"],
        "eval_prompt": "ALF가 배송지 변경 가능 시점(출고 전)과 절차를 명확히 안내했는가?",
    },
    "배송_조회": {
        "must_include": ["송장번호", "배송조회"],
        "escalation_keywords": ["분실", "반송"],
        "eval_prompt": "ALF가 송장번호를 제공하고 배송 조회 방법을 안내했는가?",
    },
    "제품_불량_AS": {
        "must_include": ["AS", "사진", "접수"],
        "escalation_keywords": ["환불", "피해보상"],
        "eval_prompt": "ALF가 AS 접수 절차(사진 첨부)를 안내하고 처리 기간을 명시했는가?",
    },
    "쿠폰_적립금": {
        "must_include": ["쿠폰", "등급"],
        "must_not_include": ["문의"],
        "eval_prompt": "ALF가 등급별 쿠폰 발급 기준과 사용 방법을 명확히 안내했는가?",
    },
}

# Healthcare (의료/뷰티) 템플릿
HEALTHCARE_TEMPLATES = {
    "예약_신청": {
        "must_include": ["예약", "날짜", "시간"],
        "must_not_include": ["대기"],
        "eval_prompt": "ALF가 예약 가능한 날짜와 시간을 제시하고 예약 절차를 안내했는가?",
    },
    "예약_변경": {
        "must_include": ["예약번호", "변경", "가능"],
        "must_not_include": ["불가능"],
        "eval_prompt": "ALF가 예약 변경 가능 시점과 절차를 명확히 안내했는가?",
    },
    "시술_상담": {
        "must_include": ["상담", "가능"],
        "escalation_keywords": ["의사", "전문가"],
        "eval_prompt": "ALF가 시술 상담 예약 방법을 안내했는가? (전문가 상담 필요 시 escalation)",
    },
    "가격_문의": {
        "must_include": ["가격", "비용"],
        "must_not_include": ["확인 후"],
        "eval_prompt": "ALF가 시술 가격 정보를 명확히 제공했는가?",
    },
    "부작용_문의": {
        "must_include": [],
        "escalation_keywords": ["부작용", "통증", "문제"],
        "eval_prompt": "ALF가 부작용 문의를 의료진에게 즉시 escalate했는가?",
    },
}

# Electronics (전자제품/리퍼비시) 템플릿
ELECTRONICS_TEMPLATES = {
    "사양_문의": {
        "must_include": ["사양", "스펙"],
        "must_not_include": ["확인 후"],
        "eval_prompt": "ALF가 제품 사양(CPU/RAM/SSD 등)을 명확히 제공했는가?",
    },
    "재고_확인": {
        "must_include": ["재고", "있습니다"],
        "must_not_include": ["확인 후"],
        "eval_prompt": "ALF가 재고 여부를 즉시 확인하고 안내했는가?",
    },
    "용도별_추천": {
        "must_include": ["추천"],
        "must_not_include": ["전문가"],
        "eval_prompt": "ALF가 고객 용도에 맞는 제품을 추천했는가?",
    },
    "매입_견적": {
        "must_include": ["견적", "매입"],
        "must_not_include": ["담당자"],
        "eval_prompt": "ALF가 매입 견적 신청 방법과 필요 정보를 안내했는가?",
    },
    "매입_절차": {
        "must_include": ["신청", "택배", "검수"],
        "must_not_include": [],
        "eval_prompt": "ALF가 매입 절차(신청→포장재→택배→검수→입금)를 단계별로 안내했는가?",
    },
    "불량_신고": {
        "must_include": ["불량", "AS", "사진"],
        "escalation_keywords": ["환불", "고장"],
        "eval_prompt": "ALF가 불량 신고 절차(사진 첨부)와 AS/환불 옵션을 안내했는가?",
    },
    "AS_접수": {
        "must_include": ["AS", "접수", "택배"],
        "must_not_include": ["불가능"],
        "eval_prompt": "ALF가 AS 접수 방법과 택배 발송 절차를 안내했는가?",
    },
    "업그레이드": {
        "must_include": ["업그레이드", "가능"],
        "must_not_include": ["불가능", "확인 후"],
        "eval_prompt": "ALF가 업그레이드(램/SSD) 가능 여부와 비용을 명확히 안내했는가?",
    },
    "반품_신청": {
        "must_include": ["반품", "반품비"],
        "must_not_include": [],
        "eval_prompt": "ALF가 반품 절차와 반품비(무료체험 10,000원 등)를 명확히 안내했는가?",
    },
    "배송_현황": {
        "must_include": ["송장", "배송"],
        "must_not_include": ["확인 후"],
        "eval_prompt": "ALF가 송장번호와 배송 현황을 즉시 제공했는가?",
    },
    "주문_취소": {
        "must_include": ["취소", "가능"],
        "must_not_include": ["불가능"],
        "eval_prompt": "ALF가 주문 취소 가능 시점과 절차를 명확히 안내했는가?",
    },
    "세금계산서": {
        "must_include": ["세금계산서", "발행"],
        "must_not_include": ["불가능"],
        "eval_prompt": "ALF가 세금계산서 발행 절차와 필요 정보를 안내했는가?",
    },
    "SW_설치": {
        "must_include": ["설치", "윈도우"],
        "must_not_include": ["불가능"],
        "eval_prompt": "ALF가 소프트웨어 설치 여부와 설치 내역을 명확히 안내했는가?",
    },
}

# 모든 템플릿 통합
ALL_TEMPLATES = {
    **ECOMMERCE_TEMPLATES,
    **HEALTHCARE_TEMPLATES,
    **ELECTRONICS_TEMPLATES,
}


def generate_success_criteria(
    sub_intent: str,
    sample_utterances: list[str] | None = None,
    vertical: str = "ecommerce",
) -> dict:
    """L3 sub-intent → success_criteria 자동생성

    Args:
        sub_intent: L3 sub-intent 이름 (예: "사이즈_핏_문의")
        sample_utterances: 샘플 발화 리스트 (optional, 현재 미사용)
        vertical: 버티컬 (ecommerce/healthcare/electronics)

    Returns:
        success_criteria dict (Scenario.success_criteria[0] 형식)
    """
    template = ALL_TEMPLATES.get(sub_intent)

    if not template:
        # Fallback: generic template
        return {
            "description": f"ALF가 {sub_intent} 관련 정보를 정확히 제공했는가?",
            "type": "llm_judge",
            "args": {
                "eval_prompt": f"ALF가 {sub_intent} 관련 질문에 정확하고 완전한 답변을 제공했는가?",
            },
        }

    args = {
        "eval_prompt": template["eval_prompt"],
    }

    if "must_include" in template and template["must_include"]:
        args["must_include"] = template["must_include"]

    if "must_not_include" in template and template["must_not_include"]:
        args["must_not_include"] = template["must_not_include"]

    return {
        "description": template["eval_prompt"],
        "type": "llm_judge",
        "args": args,
    }


def get_template_names(vertical: str | None = None) -> list[str]:
    """사용 가능한 template 이름 목록 반환

    Args:
        vertical: 특정 버티컬로 필터링 (optional)

    Returns:
        template 이름 리스트
    """
    if vertical == "ecommerce":
        return list(ECOMMERCE_TEMPLATES.keys())
    elif vertical == "healthcare":
        return list(HEALTHCARE_TEMPLATES.keys())
    elif vertical == "electronics":
        return list(ELECTRONICS_TEMPLATES.keys())
    else:
        return list(ALL_TEMPLATES.keys())


if __name__ == "__main__":
    # Test
    print("=== Success Criteria Templates ===\n")

    test_cases = [
        ("사이즈_핏_문의", "ecommerce"),
        ("매입_견적", "electronics"),
        ("예약_신청", "healthcare"),
        ("존재하지_않는_intent", "ecommerce"),
    ]

    for sub_intent, vertical in test_cases:
        criteria = generate_success_criteria(sub_intent, vertical=vertical)
        print(f"\n## {sub_intent} ({vertical})")
        print(f"Description: {criteria['description']}")
        if "must_include" in criteria["args"]:
            print(f"Must include: {criteria['args']['must_include']}")
        if "must_not_include" in criteria["args"]:
            print(f"Must NOT include: {criteria['args']['must_not_include']}")

    print(f"\n\n=== Template Coverage ===")
    print(f"E-commerce: {len(ECOMMERCE_TEMPLATES)} templates")
    print(f"Healthcare: {len(HEALTHCARE_TEMPLATES)} templates")
    print(f"Electronics: {len(ELECTRONICS_TEMPLATES)} templates")
    print(f"Total: {len(ALL_TEMPLATES)} templates")

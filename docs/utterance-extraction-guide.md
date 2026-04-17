# 실제 유저 발화 추출 가이드

qa-agent v2부터는 실제 고객 상담 데이터에서 유저 발화를 추출하여 QA 페르소나가 실제 고객처럼 말하도록 개선되었습니다.

## 왜 필요한가?

**문제 (v1):**
- LLM이 생성하는 고객 메시지: "네, 제 주문번호는 20240416001입니다."
- 너무 정중하고 완전한 문장 → 실제 고객과 다름

**해결 (v2):**
- 실제 고객 메시지: "20240416001요", "주문번호 20240416001입니다"
- 실제 상담 데이터에서 추출한 발화 스타일 모방

## 데이터 소스

### 1. patterns.json (Primary)

sop-agent가 생성하는 `02_extraction/patterns.json`에 이미 `common_phrases`가 포함되어 있습니다.

```json
{
  "clusters": [
    {
      "label": "재입고 문의",
      "patterns": [
        {
          "name": "재입고 일정 문의",
          "frequency": 45,
          "common_phrases": [
            "트루와이드 데님 로우 인디고 W30/L32 사이즈 품절인데 재입고 언제예요",
            "이번주 입고 예정인 상품 리스트 있나요",
            "품절 상품 재입고 알림 받을 수 있나요"
          ]
        }
      ]
    }
  ]
}
```

이 `common_phrases`가 **실제 고객 유저챗에서 추출한 발화**입니다.

### 2. 원본 상담 xlsx (Optional, 추가 샘플용)

`<sop_results_dir>/data/*.xlsx` 파일이 있으면 추가 발화를 추출할 수 있습니다.

**Excel 컬럼 (자동 감지):**
- `user_message`, `customer_message`, `message`, `content`
- `유저메시지`, `고객메시지`, `메시지`, `내용`
- `첫 메시지`, `first_message`, `initial_message`

## 사용 방법

### 자동 (Claude Code)

```
> <고객사> QA 돌려줘
```

Claude가 자동으로:
1. `patterns.json`에서 `common_phrases` 추출
2. (있으면) `data/*.xlsx`에서 추가 발화 추출
3. Scenario 생성 시 `source_phrases` 필드에 저장
4. Persona가 이 스타일을 모방하여 turn 1+ 메시지 생성

### 수동 (Python)

```python
from tools.extract_user_utterances import (
    load_utterances_from_patterns_json,
    extract_utterances_from_xlsx
)

# patterns.json에서 추출 (권장)
utterances = load_utterances_from_patterns_json(
    patterns_json_path="~/sop-agent/results/<고객사>/02_extraction/patterns.json",
    max_per_pattern=5
)

# xlsx에서 추가 추출 (선택)
additional = extract_utterances_from_xlsx(
    xlsx_path="~/sop-agent/results/<고객사>/data/consultations.xlsx",
    intent_keywords=["환불", "반품"],
    max_samples=10
)
```

## Persona 스타일 모방

### Hard Rule 5 (persona_archetypes.md)

모든 페르소나는 turn 1+ 메시지 생성 시 `scenario.source_phrases`의 스타일을 모방합니다.

**실제 고객 발화 패턴:**
- Fragment endings: "~요", "~이요", "~인데요"
- 주어 생략: "010-1234-5678이요" (not "제 번호는...")
- 캐주얼 조사: "근데", "그럼", "혹시"
- 짧은 문장: 최대 1-2 절
- 실제 제품명: `source_phrases`에서 사용 (발명 금지)

**예시:**

```
# scenario.source_phrases
["트루와이드 데님 로우 인디고 W30/L32 사이즈 품절인데 재입고 언제예요"]

# Persona가 생성하는 turn 1+ 메시지
Turn 0 (initial_message): "트루와이드 데님 로우 인디고 W30/L32 사이즈 품절인데 재입고 언제예요"
ALF: "재입고는 이번주 금요일 예정입니다. 알림 신청하시겠어요?"
Turn 1 (persona 생성): "네 알림 신청이요"  # ✅ 스타일 모방
Turn 1 (잘못됨): "네, 알림을 신청하고 싶습니다."  # ❌ AI-like
```

## 품질 체크

### ✅ 좋은 발화 (실제 고객 스타일)

- "20240416001입니다"
- "주문번호 20240416001요"
- "010-1234-5678이요"
- "트루와이드 데님 로우 인디고 W30/L32 품절인가요"
- "근데 재입고는 언제쯤이에요"
- "그럼 알림 신청이요"

### ❌ 나쁜 발화 (AI-like)

- "네, 제 주문번호는 20240416001입니다."
- "죄송하지만 알림 신청을 하고 싶습니다."
- "상품 재입고 일정을 알려주실 수 있나요?"
- "안녕하세요, 재입고 문의드립니다."

## 디버깅

### source_phrases가 비어있을 때

**원인:**
- patterns.json에 해당 intent의 common_phrases가 없음
- sop-agent 클러스터링 단계에서 샘플 부족

**해결:**
1. sop-agent 재실행 (더 많은 샘플 수집)
2. 수동으로 xlsx에서 추출:
   ```python
   utterances = extract_utterances_from_xlsx(
       xlsx_path="...",
       intent_keywords=["키워드1", "키워드2"],
       max_samples=10
   )
   ```
3. 또는 canonical_input.yaml에 수동 추가:
   ```yaml
   intents:
     - id: refund_inquiry
       patterns:
         - name: "단순 환불"
           common_phrases:
             - "환불 가능한가요"
             - "환불하고 싶어요"
   ```

### Persona가 여전히 AI-like하게 말할 때

**체크리스트:**
1. `scenario.source_phrases`가 제대로 전달되었는지 확인
2. `prompts/persona_archetypes.md` Hard Rule 5 확인
3. Transcript 확인: turn 1+ 메시지가 스타일 모방했는지
4. 모방 실패 시 → persona 프롬프트 강화 또는 예시 추가

## 고객사별 차이

| 고객사 | 발화 특징 | 추출 소스 |
|---|---|---|
| 패션 (벨리에) | 제품명 구체적 (브랜드+모델+사이즈), 짧은 문장 | patterns.json 주력 |
| 통신 (유심사) | 기술 용어 혼재, 요금제명 등장 | patterns.json + xlsx |
| 뷰티 | 성분/효과 질문 많음, 이모지 빈번 | xlsx 추가 추출 권장 |

## 향후 개선

1. **발화 스타일 통계 분석**
   - 조사/어미 분포 추출
   - 문장 길이 히스토그램
   - 제품명 패턴 정규화

2. **Intent별 발화 스타일 프로파일**
   - "환불 문의"는 짧고 직설적
   - "재입고 문의"는 제품명 포함
   - "AS 신고"는 길고 감정 표현

3. **다국어 지원**
   - 영어권 고객사의 casual/formal 구분
   - 일본어의 경어체/타메구치

---

## 참고

- **Persona 프롬프트**: `prompts/persona_archetypes.md` Hard Rule 5
- **Normalization**: `prompts/normalize_sop.md` `intents[].patterns` 섹션
- **추출 코드**: `tools/extract_user_utterances.py`
- **스키마**: `tools/result_store.py` `Scenario.source_phrases`

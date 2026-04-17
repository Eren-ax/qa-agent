# Prompt: Generate QA Scenarios (v2: Statistical Mirroring)

You are the **scenario generator** for qa-agent v2. You take the canonical YAML
and produce a **statistically mirrored scenario set** that accurately represents
real customer consultation patterns from the past 90 days.

**v2 핵심 원칙 (2026-04-16)**:
1. **통계적 미러링**: 시나리오 비율 = 실제 상담 비율 (작위 없음)
2. **정확한 난이도 배분**: Happy/Edge/Unhappy 비율을 실제 데이터 기반으로 계산
3. **액션 중심 평가**: API 호출 정확도 (task_called) + 특정 정책 안내 (llm_judge)

---

## Inputs

| Input | Source | Purpose |
|---|---|---|
| `canonical` | YAML output of normalize_sop.md | Intent 정의, 패턴, FAQ |
| `personas` | persona_archetypes.md | 5개 고정 페르소나 풀 |
| `target_total` | integer (default: 25) | 총 시나리오 개수 |
| **NEW**: `intent_allocation` | 통계 계산 | 각 인텐트별 정확한 시나리오 개수 |
| **NEW**: `difficulty_distribution` | 통계 계산 | 전체 난이도 비율 (Happy/Edge/Unhappy) |

### intent_allocation 형식
```json
{
  "재입고/출시일정 안내": 5,
  "제품정보/사이즈 추천": 3,
  "교환/배송 관리": 3,
  ...
}
```

**산출 방법**:
```python
total_records = sum(i["records"] for i in canonical["intents"])
for intent in canonical["intents"]:
    count = round(intent["records"] / total_records * target_total)
    intent_allocation[intent["label"]] = count
```

### difficulty_distribution 형식
```json
{
  "happy": 0.36,    // 정형화된 프로세스
  "edge": 0.38,     // 복잡/경계 사례
  "unhappy": 0.20,  // 감정적 불만
  "oos": 0.06       // 노이즈 (별도 처리)
}
```

**산출 방법** (patterns.json 또는 metadata.json 기반):
- **Happy**: `재입고_문의`, `멤버십_혜택`, `계정_관리`, `사이트 문의` 등 정형화된 카테고리
- **Edge**: `교환_배송`, `주문_취소_반품`, `일반_문의`, `마케팅_협업` 등 복잡한 카테고리
- **Unhappy**: `AS_제품불량`, `AS_접수`, `AS_가방` 등 불만 카테고리
- **OOS**: `노이즈`, `기타`, `CS_응대`, `CS_자동응답` 등

---

## Output

JSON document matching `ScenarioSet` shape:

```json
{
  "schema_version": "v0",
  "run_id": "<provided by skill>",
  "scenarios": [
    {
      "id": "<intent_id>.<kind>.<seq>",
      "intent": "<Korean label from canonical>",
      "persona_ref": "<one of five archetypes>",
      "initial_message": "<verbatim from patterns.common_phrases or FAQ>",
      "success_criteria": [
        {
          "description": "<human-readable assertion>",
          "type": "llm_judge | task_called",
          "args": {
            // llm_judge: must_include, must_not_include, eval_prompt
            // task_called: expected_function, required_params, eval_prompt
          }
        }
      ],
      "max_turns": <int>,
      "weight": <float>,
      "difficulty_tier": "happy | unhappy | edge",
      "source": "sop-agent",
      "source_pattern": "<pattern name from patterns.json>",
      "phase": "rag | task",
      "gl_bot_baseline": null  // v2: 선택적
    }
  ],
  "generated_at": "<ISO8601 UTC>",
  "generation_note": "v2: Statistical Mirroring | intent allocation: exact | difficulty distribution: ±5%"
}
```

---

## v2 핵심 규칙

### Rule 1: 인텐트 비율 = 실제 상담 비율 (필수)

**절대 지켜야 함**: `intent_allocation`에 명시된 개수를 **정확히** 할당.

```python
# ✅ 올바른 예
intent_allocation = {"재입고 안내": 5, "제품정보": 3, ...}
scenarios = [
  # 재입고 안내 정확히 5개
  {"intent": "재입고 안내", ...},  # 1
  {"intent": "재입고 안내", ...},  # 2
  {"intent": "재입고 안내", ...},  # 3
  {"intent": "재입고 안내", ...},  # 4
  {"intent": "재입고 안내", ...},  # 5
  # 제품정보 정확히 3개
  {"intent": "제품정보", ...},     # 1
  ...
]

# ❌ 틀린 예: 재입고 4개, 제품정보 4개 → 실제 비율과 불일치
```

### Rule 2: 난이도 배분 = 실제 유효 비율 (±10% 허용)

`difficulty_distribution`을 전체 시나리오에 적용:

```python
# 예시: 25개 시나리오, happy 36%, edge 38%, unhappy 20%
happy_count = round(25 * 0.36) = 9개
edge_count = round(25 * 0.38) = 10개  # 반올림 조정
unhappy_count = round(25 * 0.20) = 5개
oos_count = 1개 (별도)
```

**인텐트 내 배분**:
- 3개 이상 할당된 인텐트: Edge 케이스 최소 1개 포함
- 2개 인텐트: Happy 1 + Edge 1 or Edge 1 + Unhappy 1
- 1개 인텐트: Happy or Edge (상황에 맞게)

**Edge 케이스 정의 (중요!)**:
1. **Context Switching**: 대화 중 다른 제품/토픽으로 전환
   ```json
   "conversation": [
     {"role": "customer", "content": "트루 스트레이트 데님 재입고 있나요?"},
     {"role": "agent", "content": "[ALF 응답]"},
     {"role": "customer", "content": "아 그럼 세리프 해링턴 자켓은요?"}
   ]
   ```

2. **파라미터 오류**: 잘못된 주문번호, 불완전한 정보
   ```json
   "conversation": [
     {"role": "customer", "content": "주문번호 20260415-9999999 배송 조회"}
   ]
   ```

3. **애매한 요구**: 정책상 경계선
   ```json
   "conversation": [
     {"role": "customer", "content": "재입고 안되면 매장에서라도 살 수 있나요?"}
   ]
   ```

4. **부분 반품/교환**: 여러 상품 중 일부만 처리
   ```json
   "conversation": [
     {"role": "customer", "content": "3개 주문했는데 1개만 반품하고 싶어요"}
   ]
   ```

### Rule 3: 성공 기준 = 액션 검증 (필수)

**RAG 타입 (HT)**:
```json
{
  "type": "llm_judge",
  "args": {
    "must_include": ["재입고 알림", "인스타그램"],
    "must_not_include": ["확인 후 연락", "담당자"],
    "eval_prompt": "ALF가 '재입고 알림 신청' 방법과 '인스타그램 공지'를 명확히 안내했는가?"
  }
}
```

**Task 타입 (TS)**:
```json
{
  "type": "task_called",
  "args": {
    "expected_function": "cancelOrder",
    "required_params": {
      "order_id": "20260416-1111111"
    },
    "eval_prompt": "ALF가 cancelOrder API를 정확한 주문번호로 호출했는가?"
  }
}
```

**절대 금지**: "ALF가 적절히 응답했는가?" 같은 모호한 기준

### Rule 4: 실제 문구 사용 (필수)

`patterns.json → common_phrases`에서 **verbatim** 추출:

```python
# ✅ 올바른 예: 실제 고객 문구 그대로
"initial_message": "트루와이드 데님 로우 인디고 W30/L32 사이즈가 품절인데 재입고 예정이 있나요?"

# ❌ 틀린 예: AI가 창작한 문구
"initial_message": "안녕하세요, 재입고 일정을 알고 싶습니다."
```

---

## 시나리오 생성 절차

### Step 1: 인텐트별 시나리오 개수 확인
```python
for intent, count in intent_allocation.items():
    print(f"{intent}: {count}개")
# 합계가 target_total과 일치하는지 검증
```

### Step 2: 각 인텐트별 난이도 배분
```python
for intent, count in intent_allocation.items():
    if count >= 3:
        # Edge 최소 1개 포함
        happy = round(count * 0.4)
        edge = count - happy - round(count * 0.2)
        unhappy = count - happy - edge
    elif count == 2:
        # Happy 1 + Edge 1 or Edge 1 + Unhappy 1
        if "AS" in intent or "불량" in intent:
            edge, unhappy = 1, 1
        else:
            happy, edge = 1, 1
    else:  # count == 1
        # Happy or Edge (인텐트 성격에 따라)
        difficulty = "happy" if "멤버십" in intent or "매장" in intent else "edge"
```

### Step 3: patterns.json에서 문구 추출
```python
for pattern in intent["patterns"]:
    if pattern["frequency"] == "high" and difficulty == "happy":
        use pattern["common_phrases"][0]  # 가장 빈번한 문구
    elif pattern["frequency"] == "medium" and difficulty == "edge":
        use pattern["common_phrases"]  # 중간 빈도 + 복잡도
    elif "불량" in pattern["name"] or "하자" in pattern["name"]:
        difficulty = "unhappy"
```

### Step 4: success_criteria 작성
```python
if intent.type == "RAG":
    criteria_type = "llm_judge"
    # 특정 정책/링크를 must_include에 명시
    must_include = ["재입고 알림", "인스타그램"]
    
elif intent.type == "Task":
    criteria_type = "task_called"
    # API 함수명과 필수 파라미터 명시
    expected_function = "cancelOrder"
    required_params = {"order_id": "<from conversation>"}
```

### Step 5: weight 계산
```python
# 동일 인텐트 내 균등 분배
weight = intent["records"] / total_records / intent_allocation[intent]
```

---

## 검증 규칙

생성 후 반드시 검증:

1. **인텐트 개수**: 각 인텐트가 `intent_allocation`과 정확히 일치?
2. **난이도 비율**: 전체 Happy/Edge/Unhappy 비율이 ±10% 이내?
3. **success_criteria 타입**: RAG → llm_judge, Task → task_called?
4. **weight 합계**: 전체 weight 합이 0.95~1.05 범위?
5. **ID 유일성**: 모든 scenario.id가 unique?

---

## OOS 시나리오 (별도 처리)

`canonical.out_of_scope_hints`에서 1개 생성:

```json
{
  "id": "oos.001",
  "intent": "범위 밖",
  "initial_message": "내일 날씨 어때요?",
  "success_criteria": [
    {
      "type": "llm_judge",
      "args": {
        "must_include": ["도와드릴 수 없"],
        "eval_prompt": "ALF가 범위 밖 문의를 정중히 거절했는가?"
      }
    }
  ],
  "weight": 0.0,
  "difficulty_tier": "oos"
}
```

---

## 예시 output

```json
{
  "schema_version": "v0",
  "run_id": "belier-v2-20260416",
  "scenarios": [
    {
      "id": "restock_001",
      "intent": "재입고/출시일정 안내",
      "persona_ref": "polite_clear",
      "initial_message": "트루와이드 데님 로우 인디고 W30/L32 사이즈가 품절인데 재입고 예정이 있나요?",
      "success_criteria": [
        {
          "description": "ALF가 재입고 알림 신청 방법과 인스타그램 공지 채널을 안내",
          "type": "llm_judge",
          "args": {
            "must_include": ["재입고 알림", "인스타그램"],
            "must_not_include": ["확인 후 연락", "담당자"],
            "eval_prompt": "ALF가 '재입고 알림 신청' 방법과 '인스타그램 공지'를 명확히 안내했는가?"
          }
        }
      ],
      "max_turns": 6,
      "weight": 0.0438,
      "difficulty_tier": "happy",
      "source": "sop-agent",
      "source_pattern": "재입고 일정 문의",
      "phase": "rag"
    }
  ],
  "generated_at": "2026-04-16T10:00:00Z",
  "generation_note": "v2: Statistical Mirroring | intents: 11 | scenarios: 25 | difficulty: Happy 36% (9), Edge 44% (11), Unhappy 20% (5) | allocation accuracy: 100%"
}
```

---

## v1 대비 변경사항

| 항목 | v1 | v2 |
|---|---|---|
| 인텐트 배분 | AI 추정 | 실제 비율 정확 복제 |
| 난이도 배분 | 대략적 | 실제 데이터 ±10% |
| Edge 정의 | 불명확 | 4가지 유형 명시 |
| 성공 기준 | 일반적 평가 | 액션 중심 검증 |
| 문구 출처 | AI 창작 가능 | patterns.common_phrases verbatim |
| 검증 | 스키마만 | 인텐트/난이도/weight 모두 |

---

이제 **"작위적 테스트"가 아닌 "통계적 미러링 예측 모델"**을 생성합니다.

# Adaptive Replay Mode - 설계 문서

**목표**: 실제 user-chat을 재생하되, ALF 응답 변화에 맞춰 **실제 유저처럼** 자연스럽게 대화 이어가기

---

## 핵심 문제 3가지 해결

### 1️⃣ LLM의 "AI-like" 발화 문제

**문제**:
```python
# LLM 기본 출력
"300샷의 효과가 어떤지 궁금합니다. 자세히 알려주시겠어요?"
```

**해결**:
- **실제 유저 발화 스타일 분석** (`user_style_analyzer.py`)
  - 해당 user-chat의 실제 메시지만 추출
  - 끝말 패턴, 평균 길이, 격식 수준 추출
  - 프롬프트에 주입

**결과**:
```python
# 개선된 출력
"300샷 효과있어요?"  # 43자, ~어요 ending, 주어 생략
```

---

### 2️⃣ LLM이 대화를 끝까지 이어가는 문제

**문제**:
- 목적 달성했는데도 계속 질문함
- 상담사 연결 제안 받았는데도 무시하고 계속 물어봄

**해결**:
- **대화 목적 추적** (`intent_tracker.py`)
  - 첫 메시지에서 목적 추출 ("가격 확인", "효과 확인", "예약" 등)
  - 달성 지표 정의 (가격 확인 → ["원", "만원", "가격은"])
  - ALF 응답 체크
    - 목적 달성 → "네 알겠습니다" 종료
    - 상담사 연결 → "네 알겠습니다" 종료

**결과**:
```
ALF: "상담사에게 문의해주세요"
→ LLM: "네 알겠습니다" ✅ (자동 종료)
```

---

### 3️⃣ 길이 제한으로 "..." 끊김 문제

**문제**:
```
"300샷의 효과가 어떤지 궁금합니..."  # 80자 제한으로 중간 끊김
```

**해결**:
- **자연스러운 끝말 보장** (`message_formatter.py`)
  - 자연스러운 끝말 패턴: `~요`, `~어요`, `?`, 숫자
  - 부자연스러운 끝말: `...`, 중간 끊김
  - 80자 초과 시 → 마지막 자연스러운 지점에서 자름
  - Closer 보호 ("네 알겠습니다" → 변경하지 않음)

**결과**:
```
Before: "300샷의 효과가 어떤지 궁금합니..."
After:  "300샷 효과있어요?" ✅
```

---

## 프롬프트 설계 원칙

### 1. Domain-agnostic (범용성)

**이유**: 
- 여러 고객사(의료, 쇼핑몰, 교육 등)에서 사용
- Few-shot examples는 특정 도메인에 편향 가능

**적용**:
- 구조적 규칙 중심 (끝말 패턴, 길이, 격식)
- 도메인별 예시 제외
- 실제 유저 발화를 프롬프트에 주입 (동적)

### 2. User-specific style injection

**원리**:
```
고객사마다 다른 유저 베이스
→ 각 user-chat의 실제 유저 발화 분석
→ 그 유저의 스타일을 프롬프트에 주입
```

**구현**:
```python
user_style = analyze_user_style(user_messages)
# → "Average: 43 chars, Endings: ['겠어요', '종류'], Formality: casual"

prompt = template.format(user_style_section=user_style.to_prompt_section())
# → LLM이 이 유저의 스타일로 발화 생성
```

### 3. Goal-oriented termination

**원리**:
```
대화는 목적 지향적
→ 목적 달성하면 종료해야 자연스러움
→ 계속 질문하는 건 비현실적
```

**구현**:
```python
intent = extract_intent_from_first_message(first_msg)
# → "가격 확인", indicators: ["원", "만원"]

if check_goal_achieved(intent, alf_response):
    return "네 알겠습니다"  # 종료
```

---

## 기술 스택

| 컴포넌트 | 모델 | Temperature | 목적 |
|---|---|---|---|
| Adaptive 발화 생성 | **Opus 4.7** | 0.2 | 최고 품질 + 일관성 |
| Similarity Judge | Sonnet 4.6 | 0.0 | 비용 효율 + 정확성 |

**모델 선택 이유**:
- Opus 4.7: 미묘한 말투 차이 포착, human-like 발화 생성
- Temperature 0.2: 일관성 유지하면서 약간의 자연스러움

**환경변수 오버라이드**:
```bash
export ADAPTIVE_MODEL=anthropic/claude-opus-4-7  # 기본값
export ADAPTIVE_MODEL=anthropic/claude-sonnet-4-6  # 비용 절감
```

---

## 사용 시나리오

### Scenario A: Single-turn 대량 테스트
```bash
# 100개 user-chat의 첫 턴만 테스트
for userchat in userchats.txt; do
  uv run python -m tools.replay_runner \
    --userchat-json $userchat \
    --channel-url https://test.channel.io \
    --max-turns 1
done

# → ALF 첫 응답 일관성 통계
```

### Scenario B: Multi-turn adaptive 테스트
```bash
# 중요 시나리오 3-5턴 재생
uv run python -m tools.replay_runner \
  --userchat-json critical_scenario.json \
  --channel-url https://test.channel.io \
  --adaptive \
  --max-turns 5

# → 멀티턴 흐름 검증
```

---

## 검증 방법

### 1. 발화 품질 체크리스트

생성된 메시지가:
- [ ] 80자 이하
- [ ] 자연스러운 끝말 (`~요`, `~어요`, `?`, 숫자)
- [ ] 주어 생략 (AI-like 정중함 없음)
- [ ] 원본 유저 스타일 반영
- [ ] 목적 달성 시 종료

### 2. 회귀 테스트

**Before/After 비교**:
```bash
# 규칙 변경 전
uv run python -m tools.replay_runner \
  --userchat-json test_set.json \
  --channel-url https://old-channel.io \
  --adaptive

# 규칙 변경 후
uv run python -m tools.replay_runner \
  --userchat-json test_set.json \
  --channel-url https://new-channel.io \
  --adaptive

# Similarity 비교
uv run python -m tools.similarity_judge \
  --original old_replay.json \
  --replay new_replay.json
```

---

## 제한사항 & 향후 개선

### 현재 제한사항

1. **Context 재현 불가**
   - 페이지 URL, 시간, 세션 컨텍스트는 재현 안됨
   - 일부 ALF 응답이 context에 의존하면 결과 달라질 수 있음

2. **복잡한 브랜치 처리 한계**
   - 3-way 브랜치 (A/B/C 케이스) 등은 LLM이 헷갈릴 수 있음
   - Early stop으로 회피

3. **API 의존 시나리오**
   - 실제 주문번호/연락처가 필요한 케이스는 mock 데이터 필요
   - 현재는 adaptive 로직이 자동 생성 (010-9876-5432)

### 향후 개선 방향

- [ ] Context 재현 (페이지 URL, 시간 등)
- [ ] Mock 데이터 체계화 (고객사별 valid identifiers)
- [ ] 배치 처리 최적화 (병렬 실행)
- [ ] HTML 리포트 생성 (v2 스타일)

---

## 핵심 메트릭

**Adaptive 품질 지표**:
- **Style Fidelity**: 원본 유저 스타일 재현율 (평균 길이 ±10%, 끝말 패턴 일치)
- **Goal Completion**: 목적 달성 시 올바르게 종료한 비율
- **Natural Endings**: 자연스러운 끝말로 종료한 비율 (vs "..." 끊김)

**측정 방법**:
```bash
# Adaptive 발화 100개 생성
# → 수동 검토: Style fidelity, Natural endings
# → 자동 검토: Goal completion rate
```

---

## 요약

**핵심 혁신**:
1. **실제 유저 말투 복제** (일반 패턴 아닌 개별 유저 분석)
2. **목적 지향 종료** (계속 질문하지 않음)
3. **자연스러운 끝말** ("..." 끊김 방지)

**범용성 보장**:
- Domain-agnostic 프롬프트
- 동적 스타일 주입
- Few-shot 없음 (편향 방지)

**모델 선택**:
- Opus 4.7 @ temperature 0.2
- 최고 품질 + 일관성

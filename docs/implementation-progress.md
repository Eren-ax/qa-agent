# BP 추출 기준 구현 진행상황

**최종 업데이트**: 2026-05-08

---

## 완료된 작업

### ✅ Phase 1: 계층 1 (고객 만족) - 완료

**구현**: `tools/outcome_scorer.py`

**측정 지표** (0~7.0점):
- Resolution (+2.0): `state == 'closed'`
- CSAT ≥4 (+1.5): `profile.csat >= 4`
- Last message positive (+1.0): LLM 감정 분석 (선택적)
- No repeat inquiry (+1.0): 재문의 체크 (선택적)
- Pingpong penalty (-0.3): `replyCount > 10`
- Response time penalty (-0.5): `timeToFirstAnswer > 1h`

**테스트 결과** (벨리에v2):
- 평균 outcome_score: ~3.0/7.0
- 분포: 1.0 (미해결) ~ 6.5 (완벽)
- 대부분 케이스: 2.0~4.5 범위

**통합**:
- `best_practice_extractor.py`에서 자동 계산
- `BestPracticeCase.outcome_score`, `outcome_breakdown` 저장

---

### ✅ Phase 2: 계층 3 (도입 난이도) - 완료

**구현**: `tools/adoption_classifier.py`

**분류 기준**:
1. **RAG** (지식베이스 검색):
   - ALF 작동 케이스
   - 정보 문의 (문의/정보/방법 등)
   - 키워드 없으면 기본값

2. **Text Task** (조건 분기):
   - 경우/상황/조건/~면/등급별/단계 패턴
   - 상황별 안내 필요

3. **Function Task** (API 연동):
   - 주문취소/반품/교환/환불
   - 재고/포인트/쿠폰/적립금
   - API/연동/어드민/시스템

**테스트 결과** (벨리에v2 50케이스):
- RAG: 30건 (60%)
- Function Task: 18건 (36%)
- Text Task: 2건 (4%)

**통합**:
- `best_practice_extractor.py`에서 자동 분류
- `BestPracticeCase.task_type`, `task_type_confidence`, `task_type_reason` 저장
- 휴리스틱 방식 (빠름, LLM 비용 없음)

---

## 남은 작업

### 🔶 Phase 3: 계층 2 (응대 품질 5차원) - 미구현

**목표**: 기존 scoring_agent.py 확장

**구현 필요**:
```python
# tools/scoring_agent.py 수정
def score_transcript_v2(transcript, best_practice) -> dict:
    return {
        'accuracy': {'score': 0-5, 'reason': '...'},      # 정확성
        'completeness': {'score': 0-3, 'reason': '...'},  # 완결성
        'specificity': {'score': 0-1, 'reason': '...'},   # 구체성
        'empathy': {'score': 0-1, 'reason': '...'},       # 공감
        'brevity': {'score': 0-10, 'reason': '...'},      # 간결성 (참고)
        'total': 10.0
    }
```

**작업량**: 2주 예상
- 프롬프트 작성 (5차원 평가 기준)
- LLM Judge 호출
- 비용: $1.50 / 100케이스

**우선순위**: Medium (QA 리포트 생성 시 필요)

---

### 🔶 Phase 4: 통합 리포트 & 우선순위 산정 - 미구현

**목표**: 3계층 종합하여 P0/P1/P2 자동 분류

**구현 필요**:

1. **우선순위 산정 로직**:
```python
def calculate_priority(outcome_score, process_score, task_type) -> str:
    if outcome_score >= 6.0 and process_score >= 10.0 and task_type == "RAG":
        return "P0"  # 즉시 개선
    elif outcome_score >= 4.0 and task_type in ["RAG", "Text Task"]:
        return "P1"  # 단기 설계
    elif task_type == "Function Task":
        return "P2"  # 개발 협업
    else:
        return "P3"  # 보류
```

2. **자동화율 예측**:
```python
def estimate_automation_rate(cases):
    p0_count = len([c for c in cases if c.priority == "P0"])
    p1_count = len([c for c in cases if c.priority == "P1"])
    
    return {
        "immediate": p0_count / len(cases),  # 즉시
        "short_term": (p0_count + p1_count) / len(cases),  # ~몇 주
    }
```

3. **내부 대시보드 HTML**:
```html
<h1>📊 BP 분석 대시보드</h1>
<section>
  <h2>우선순위 분포</h2>
  <ul>
    <li>P0 (즉시 개선): X건 (X%)</li>
    <li>P1 (단기 설계): X건 (X%)</li>
    <li>P2 (개발 협업): X건 (X%)</li>
  </ul>
</section>
<section>
  <h2>영업 메시지</h2>
  <p>"XX님 봇 인계 케이스의 약 X%는 ALF로 즉시 가져올 수 있고..."</p>
</section>
```

**작업량**: 1주 예상
- 우선순위 계산 함수
- 내부 대시보드 템플릿
- 영업 메시지 자동 생성

**우선순위**: High (영업팀 요구사항)

---

## 현재 상태

### 데이터 플로우

```
sop-agent clustering (*_clustered.xlsx)
    ↓
[tools/best_practice_extractor.py]
    ├─ calculate_outcome_score()  ✅ 구현 (Phase 1)
    ├─ classify_task_type()       ✅ 구현 (Phase 2)
    └─ BestPracticeCase {
        outcome_score: 3.0/7.0,        ✅
        outcome_breakdown: {...},      ✅
        task_type: "RAG",              ✅
        task_type_confidence: 0.6,     ✅
        task_type_reason: "..."        ✅
    }
    ↓
[run_bp_qa.py]
    ├─ generate_scenarios
    ├─ execute QA tests
    └─ transcripts.jsonl
    ↓
[tools/scoring_agent.py]  🔶 Phase 3 필요
    └─ score_transcript_v2()  ← 5차원 평가
    ↓
scores.json {
    outcome_score: {...},     ✅
    process_score: {...},     🔶 미구현
    task_type: "RAG",         ✅
    priority: "P0"            🔶 미구현
}
    ↓
[tools/integrated_report_generator.py]  🔶 Phase 4 필요
    ├─ 고객용 리포트 (BP vs ALF)
    └─ 내부용 대시보드 (우선순위 분포)
```

---

## 사용 가능한 기능

### 현재 (Phase 1+2 완료)

```python
# BP 추출 시 자동으로 계층 1+3 점수 계산
from tools.best_practice_extractor import extract_best_practices

cases = extract_best_practices(
    "~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx",
    target_total=100
)

# 각 케이스는 다음 정보 포함:
for case in cases:
    print(f"Intent: {case.intent}")
    print(f"Outcome Score: {case.outcome_score:.1f}/7.0")
    print(f"  - Resolved: {case.outcome_breakdown['resolved']}")
    print(f"  - CSAT: {case.outcome_breakdown['csat']}")
    print(f"Task Type: {case.task_type} (confidence: {case.task_type_confidence:.2f})")
    print(f"  - Reason: {case.task_type_reason}")
    print()
```

**분석 가능**:
- 고객 만족도 분포 (outcome_score)
- 도입 난이도 분포 (task_type)
- 클러스터별 자동화 가능성

**분석 불가** (Phase 3+4 필요):
- 응대 품질 5차원 점수
- P0/P1/P2 우선순위
- 자동화율 예측
- 영업 메시지 자동 생성

---

## 검증 결과

### Phase 1: outcome_score

**벨리에v2 데이터 (2725건)**:
- 평균: 3.0/7.0
- 최빈값: 3.0 (resolved + no repeat)
- 상위 20%: 4.5 이상
- 하위 20%: 1.0 이하

**상관관계**:
- 기존 quality_score와 상관계수: ~0.85 ✅
- CSAT가 있는 케이스는 +1.5점 차이 ✅

### Phase 2: task_type

**벨리에v2 50케이스 샘플**:
- RAG: 60% (예상 70~80% 대비 낮음)
- Function Task: 36% (합리적)
- Text Task: 4% (너무 적음, 키워드 보강 필요)

**정확도** (수동 검증 10케이스):
- 8/10 정확 (80%) ✅
- 오분류 2건: "재고" 키워드로 Function으로 분류됐으나 실제는 RAG

**개선 필요**:
- "재고 확인" → Function, "재입고" → RAG로 구분
- LLM fallback 옵션 활성화 고려

---

## 다음 단계

### 즉시 가능

1. **통계 분석**:
```bash
python3 << EOF
from tools.best_practice_extractor import extract_best_practices
from collections import Counter

cases = extract_best_practices(
    "~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx",
    target_total=100
)

# Outcome score 분포
scores = [c.outcome_score for c in cases]
print(f"Outcome Score: avg={sum(scores)/len(scores):.1f}, max={max(scores):.1f}")

# Task type 분포
task_types = Counter(c.task_type for c in cases)
for task_type, count in task_types.most_common():
    print(f"{task_type}: {count} ({count/len(cases)*100:.1f}%)")
EOF
```

2. **키워드 튜닝**:
   - `adoption_classifier.py` 휴리스틱 개선
   - "재입고" → RAG 우선순위
   - "재고 확인" → Function 유지

### Phase 3 구현 (2주)

1. Week 1: 프롬프트 작성
   - `prompts/scoring_5dimensions.md` 생성
   - 각 차원별 평가 기준 정의

2. Week 2: scoring_agent 확장
   - `score_transcript_v2()` 구현
   - 기존 리포트와 비교 검증

### Phase 4 구현 (1주)

1. 우선순위 산정 로직 (2일)
2. 내부 대시보드 템플릿 (2일)
3. 영업 메시지 생성 (1일)

---

## 리스크 & 대응

### Phase 3 LLM 비용

**예상**: 100케이스 × $0.015 = $1.50

**대응**:
- 프롬프트 최적화 (토큰 수 줄이기)
- Haiku 사용 검토 (정확도 vs 비용)
- 차란 235케이스도 $3.5 이하

### task_type 정확도

**현재**: 80% (수동 검증 10케이스)

**대응**:
- 휴리스틱 키워드 지속 보강
- LLM fallback 옵션 (불확실 케이스만)
- 사용자 피드백 루프

### 우선순위 산정 기준

**이슈**: P0/P1/P2 threshold 주관적

**대응**:
- 차란 데이터로 검증
- 노션 수동 분석 결과와 비교
- threshold 조정 가능하도록 설계

---

*v1.0 / 2026-05-08 / Phase 1+2 완료*

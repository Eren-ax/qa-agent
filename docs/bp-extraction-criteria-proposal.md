# Best Practice 추출 기준 기획안 (v1.0)

**작성일**: 2026-05-08  
**참고**: [노션 안건 1 - BP란 무엇인가](https://www.notion.so/channelio/1-BP-35874b55ec7c81a6b604fb1ddf154e81)

---

## 목차

1. [현황 분석](#1-현황-분석)
2. [BP의 이중 목적](#2-bp의-이중-목적)
3. [3계층 평가 기준](#3-3계층-평가-기준)
4. [구체적 측정 지표](#4-구체적-측정-지표)
5. [우선순위 산정](#5-우선순위-산정)
6. [구현 로드맵](#6-구현-로드맵)
7. [부록: 차란 사례 분석](#7-부록-차란-사례-분석)

---

## 1. 현황 분석

### 1.1 현재 qa-agent의 BP 추출 방식 (v3)

**입력**: sop-agent clustering 결과 (`*_clustered.xlsx`)

**선정 기준**:
```python
quality_score = 0.0
  + 1.0  if state == 'closed'         # 해결됨
  + 1.0  if CSAT > 0                  # 긍정 평가
  + 0.5  if priority_tag              # 우선순위 태그
  + 0.5  if ALF triggered             # ALF 작동
  - 0.5  if time_to_answer > 1h       # 응답 지연
```

**샘플링 전략**:
- 클러스터 크기 비례 할당
- 품질 점수 상위 50% 내 랜덤 샘플링
- 모든 클러스터에서 최소 1개 추출

### 1.2 부족한 부분

| 노션 문서 기준 | 현재 qa-agent | 격차 |
|--------------|-------------|------|
| **1계층: 고객 만족** (재문의·핑퐁·응답시간) | `state`, `CSAT`만 사용 | ❌ 재문의율, 핑퐁 수, 마지막 발화 분석 미반영 |
| **2계층: 응대 품질** (정확·완결·구체·공감·간결) | 단일 `quality_score`로 통합 | ❌ 5차원 분리 평가 없음 |
| **3계층: 도입 난이도** (RAG/Text Task/Function) | 미반영 | ❌ 우선순위 산정 불가 |

**결론**: 현재는 **1계층 일부만** 측정. 2계층·3계층 보강 필요.

---

## 2. BP의 이중 목적

노션 문서에서 정의한 BP의 이중 목적을 qa-agent에 반영합니다.

### 목적 (a): 고객 컴펀용

**Who**: 고객사 운영팀·리더  
**What**: "이게 너희가 생각하는 **베스트 응대**가 맞냐?"  
**Use**: 합의된 응대 기준 확정 / 운영팀 교육 / SOP 입력

**qa-agent 산출물**:
- HTML 리포트 (BP vs ALF 비교)
- Google Sheets (드롭다운 + 조건부 서식)
- 각 케이스별 "베스트 사유" 자동 생성

### 목적 (b): 내부 산정용

**Who**: AX팀 (도입 설계)  
**What**: "우리가 이걸 **어떻게 풀 것인가**?" → 몇 주 걸릴지 / 난이도 / 우선순위  
**Use**: ALF 도입 로드맵 / 개발팀 협업 판단 / 영업 메시지

**qa-agent 산출물**:
- 우선순위별 케이스 분포 (RAG / Text Task / Function)
- 자동화율 예측 (처리 방식별)
- 타임라인 산정 (몇 주 / 몇 개월)

---

## 3. 3계층 평가 기준

노션 문서의 3계층 구조를 qa-agent에 구현합니다.

### 계층 1: 고객 만족 (Outcome) ⭐

**정의**: 고객이 원하던 결과를 얻었는가

| 측정 지표 | 데이터 소스 | 가중치 | 구현 우선순위 |
|----------|------------|--------|-------------|
| **재오픈 여부** | `state == 'closed'` | 2.0 | ✅ 구현됨 |
| **CSAT** | `profile.csat` | 1.5 | ✅ 구현됨 |
| **마지막 발화 긍정** | `enhanced_text` LLM 분석 | 1.0 | 🔶 구현 필요 |
| **재문의 여부** | 동일 고객 7일 내 재문의 | 1.0 | 🔶 구현 필요 |
| **핑퐁 횟수** | `replyCount` | -0.3 (과다 시) | 🔶 구현 필요 |
| **응답 시간** | `timeToFirstAnswer` | -0.5 (지연 시) | ✅ 구현됨 |

**총점 계산**:
```python
outcome_score = 0.0
  + 2.0  if state == 'closed'
  + 1.5  if CSAT >= 4
  + 1.0  if 마지막_발화_긍정
  + 1.0  if 재문의_없음
  - 0.3  if replyCount > 10  # 핑퐁 과다
  - 0.5  if timeToFirstAnswer > 3600  # 1시간 이상
```

### 계층 2: 응대 품질 (Process)

**정의**: 응대가 명확·정확·정중한가

| 차원 | 정의 | 측정 방법 |
|------|------|-----------|
| **정확성** | 올바른 정보 제공 | LLM Judge: BP vs 실제 응대 비교 |
| **완결성** | 필요 정보 모두 포함 | LLM Judge: 정보 누락 체크 |
| **구체성** | 구체적 답변 (숫자/날짜/링크) | 정규식 + LLM 검증 |
| **공감** | 고객 감정 이해·반영 | LLM Sentiment 분석 |
| **간결성** | 불필요한 말 없이 명확 | 응답 길이 vs 정보량 비율 |

**총점 계산**:
```python
process_score = (
    accuracy_score     * 0.3 +  # 정확성 (가장 중요)
    completeness_score * 0.25 + # 완결성
    specificity_score  * 0.2 +  # 구체성
    empathy_score      * 0.15 + # 공감
    brevity_score      * 0.1    # 간결성
)
```

**구현 방법**: 
- 기존 scoring-agent 확장 (10점 척도 → 5차원 분리)
- LLM Judge 프롬프트에 5차원 평가 기준 추가

### 계층 3: 도입 난이도 (Adoption)

**정의**: ALF가 어떻게 풀 것인가

| 처리 방식 | 우선순위 | 타임라인 | 데이터 소스 |
|----------|---------|---------|------------|
| **RAG** | 1순위 | 몇 일~주 | `alfTriggered == True` + 지식 기반 응대 |
| **Text Task** (분기대화) | 2순위 | 몇 주 | 조건 분기 필요 케이스 |
| **Function Task** (연동) | 3순위 | 몇 개월 | 외부 API/어드민 의존 |

**자동 분류 로직**:
```python
def classify_adoption_tier(case: BestPracticeCase) -> str:
    # 1. ALF 작동 + 단순 정보 제공 → RAG
    if case.alf_triggered and is_simple_info_query(case.enhanced_text):
        return "RAG"
    
    # 2. 조건 분기 필요 → Text Task
    if has_conditional_logic(case.enhanced_text):
        return "Text Task"
    
    # 3. 어드민/API 언급 → Function Task
    if mentions_admin_or_api(case.enhanced_text):
        return "Function Task"
    
    # 기본값
    return "Unknown"
```

---

## 4. 구체적 측정 지표

### 4.1 계층 1: 고객 만족 (신규 지표 구현)

#### 마지막 발화 긍정 분석

**목적**: 대화 종료 시점의 고객 만족도 추정

**구현**:
```python
def analyze_last_message_sentiment(enhanced_text: str) -> float:
    """마지막 고객 발화의 긍정/부정 점수"""
    # enhanced_text에서 마지막 USER: 메시지 추출
    last_user_message = extract_last_user_message(enhanced_text)
    
    # LLM 감정 분석
    prompt = f"""
    고객의 마지막 발화를 분석하여 만족도를 판단하세요.
    
    발화: "{last_user_message}"
    
    점수 기준:
    - 1.0: 명확한 감사/만족 표현 ("감사합니다", "해결됐어요")
    - 0.5: 중립적 종료 ("알겠습니다", "확인했어요")
    - 0.0: 불만족 표현 ("이게 뭐죠", "안 되는데요")
    
    Output: 0.0~1.0 사이 점수만
    """
    
    return llm_call(prompt)
```

**데이터 소스**: `enhanced_text` (sop-agent clustering)

#### 재문의 여부 체크

**목적**: 7일 내 동일 고객의 유사 문의 → 미해결 추정

**구현**:
```python
def check_repeat_inquiry(case: BestPracticeCase, all_cases: list) -> bool:
    """7일 내 동일 고객의 유사 문의 체크"""
    user_id = extract_user_id(case.user_chat_url)
    case_date = extract_date(case.user_chat_url)
    
    for other_case in all_cases:
        if extract_user_id(other_case.user_chat_url) != user_id:
            continue
        
        other_date = extract_date(other_case.user_chat_url)
        if 0 < (other_date - case_date).days <= 7:
            # 의도 유사도 체크 (LLM)
            if intent_similarity(case.intent, other_case.intent) > 0.7:
                return True  # 재문의 발견
    
    return False
```

**데이터 소스**: `url`, `enhanced_text` + 전체 케이스 교차 분석

### 4.2 계층 2: 응대 품질 (5차원 분리)

기존 scoring-agent (10점 척도)를 확장:

**현재**:
```
QA Score = 정확성(5) + 완결성(3) + 톤&매너(2)
```

**개선**:
```
Process Score = {
    accuracy: 5점,      # 정확성
    completeness: 3점,  # 완결성
    specificity: 1점,   # 구체성 (새로 추가)
    empathy: 1점,       # 공감 (톤&매너 분리)
    brevity: 0점        # 간결성 (참고용, 점수 미반영)
}
```

### 4.3 계층 3: 도입 난이도 (자동 분류)

**구현**: LLM 기반 분류기

```python
def classify_task_type(case: BestPracticeCase) -> dict:
    """처리 방식 자동 분류"""
    prompt = f"""
    다음 상담 케이스를 ALF 처리 방식으로 분류하세요.
    
    고객 의도: {case.intent}
    대화 내용: {case.enhanced_text[:500]}
    
    분류 기준:
    1. RAG: 지식베이스 검색으로 답변 가능 (예: FAQ, 상품 정보)
    2. Text Task: 조건 분기 필요 (예: 주문 상태별 안내)
    3. Function Task: 외부 API/어드민 연동 필요 (예: 주문 취소, 재고 확인)
    
    Output JSON:
    {{
        "task_type": "RAG|Text Task|Function Task",
        "confidence": 0.0~1.0,
        "reason": "분류 근거"
    }}
    """
    
    return json.loads(llm_call(prompt))
```

---

## 5. 우선순위 산정

### 5.1 종합 점수 계산

```python
class BPScore:
    outcome: float      # 계층 1: 고객 만족 (0~7.0)
    process: float      # 계층 2: 응대 품질 (0~10.0)
    adoption_tier: str  # 계층 3: RAG / Text Task / Function Task
    
    @property
    def total(self) -> float:
        """종합 점수 (계층 1+2)"""
        return (self.outcome * 0.4) + (self.process * 0.6)
    
    @property
    def priority(self) -> str:
        """우선순위 (계층 1+2+3 조합)"""
        if self.total >= 12.0 and self.adoption_tier == "RAG":
            return "P0 - 즉시 개선 가능"
        elif self.total >= 10.0 and self.adoption_tier in ["RAG", "Text Task"]:
            return "P1 - 단기 설계"
        elif self.adoption_tier == "Function Task":
            return "P2 - 개발 협업 필요"
        else:
            return "P3 - 보류"
```

### 5.2 우선순위별 분류

| 우선순위 | 조건 | 처리 방식 | 타임라인 | 영업 메시지 |
|---------|------|----------|---------|-----------|
| **P0** | total ≥ 12.0 + RAG | RAG | 몇 일~주 | "즉시 개선 가능한 케이스" |
| **P1** | total ≥ 10.0 + (RAG or Text) | RAG / Text Task | 몇 주 | "단기 설계로 해결 가능" |
| **P2** | Function Task | Function Task | 몇 개월 | "개발팀 협업 후 가능" |
| **P3** | total < 10.0 | - | - | "보류 (우선순위 낮음)" |

### 5.3 자동화율 예측

```python
def estimate_automation_rate(bp_cases: list[BestPracticeCase]) -> dict:
    """우선순위별 자동화율 예측"""
    total = len(bp_cases)
    
    p0_count = len([c for c in bp_cases if c.priority == "P0"])
    p1_count = len([c for c in bp_cases if c.priority == "P1"])
    p2_count = len([c for c in bp_cases if c.priority == "P2"])
    
    return {
        "immediate": {
            "count": p0_count,
            "rate": p0_count / total,
            "timeline": "몇 일~주"
        },
        "short_term": {
            "count": p0_count + p1_count,
            "rate": (p0_count + p1_count) / total,
            "timeline": "~몇 주"
        },
        "long_term": {
            "count": total - p2_count,
            "rate": (total - p2_count) / total,
            "timeline": "~몇 개월"
        }
    }
```

---

## 6. 구현 로드맵

### Phase 1: 계층 1 보강 (2주)

**목표**: 고객 만족 지표 확장

- [ ] 마지막 발화 긍정 분석 (`analyze_last_message_sentiment`)
- [ ] 재문의 여부 체크 (`check_repeat_inquiry`)
- [ ] 핑퐁 횟수 가중치 조정
- [ ] `outcome_score` 계산 로직 추가

**산출물**: `tools/outcome_analyzer.py`

### Phase 2: 계층 2 분리 (2주)

**목표**: 응대 품질 5차원 평가

- [ ] scoring-agent 확장 (5차원 분리)
- [ ] LLM Judge 프롬프트 업데이트
- [ ] `process_score` 세부 항목 저장

**산출물**: `tools/scoring_agent.py` 업데이트

### Phase 3: 계층 3 자동 분류 (3주)

**목표**: 도입 난이도 자동 분류

- [ ] Task type 분류기 (`classify_task_type`)
- [ ] RAG/Text/Function 휴리스틱 보강
- [ ] 우선순위 산정 로직 (`BPScore.priority`)

**산출물**: `tools/adoption_classifier.py`

### Phase 4: 통합 리포트 (1주)

**목표**: 이중 목적 지원 산출물

- [ ] 고객 컴펀용 리포트 (HTML + Google Sheets)
- [ ] 내부 산정용 대시보드 (우선순위별 분포)
- [ ] 자동화율 예측 차트

**산출물**: `tools/integrated_report_generator.py` 확장

---

## 7. 부록: 차란 사례 분석

### 7.1 차란 BP 추출 결과 (노션 문서)

- **입력**: 90일 상담 10,000건
- **최종 BP**: 235건
- **P0 (즉시 개선 / RAG)**: 186건 (79.1%)
- **P1 (단기 설계)**: 23건 (9.8%) — RAG 2차방어 11 + 분기대화 12
- **P2 (개발 필요)**: 49건 (20.9%)

### 7.2 영업 메시지

> "차란님 봇 인계 케이스의 약 **56%**는 ALF로 바로 가져올 수 있고, **44%**는 어드민 연동 후 가능해요."

### 7.3 qa-agent로 재현 시 예상 결과

현재 구현 (v3)으로 차란 데이터 재분석:

```bash
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx \
  --channel-url https://eoz6p.channel.io \
  --output-dir storage/charan_bp_phase123 \
  --target-total 235
```

**예상 산출물** (Phase 1-4 완료 후):
- P0: ~180건 (outcome ≥ 5.0 + RAG)
- P1: ~25건 (outcome ≥ 4.0 + Text Task)
- P2: ~30건 (Function Task)

**격차 분석**:
- 현재: 단일 quality_score → P0/P1/P2 구분 불가
- 개선 후: 3계층 점수 → 자동 우선순위 산정

---

## 8. 합의 필요 사항

### 8.1 구조적 포인트

1. **이중 목적 (a)+(b) 둘 다 지원?**
   - ✅ 제안: 둘 다 지원. 산출물 포맷만 분리 (고객용 HTML / 내부용 Dashboard)

2. **3계층 정의 채택?**
   - ✅ 제안: 노션 문서 3계층 그대로 채택
   - 보완: 계층 1 측정 지표 확장 (재문의·핑퐁·마지막 발화)

### 8.2 계층별 시그널 포인트

1. **계층 1 보강 범위**
   - Q: 재문의율 / 핑퐁 / 응답시간 / CSAT 모두 반영?
   - A: ✅ 모두 반영 (가중치는 Phase 1에서 실험)

2. **계층 2 차원 분리**
   - Q: 5차원(정확·완결·구체·공감·간결) 별도 평가 vs 통합 score?
   - A: ✅ 별도 평가 후 가중 합산 (내부 분석용 세부 항목 저장)

3. **계층 3 자동 분류 정확도**
   - Q: LLM 분류기 신뢰도?
   - A: Phase 3에서 검증. 초기는 휴리스틱 + LLM 조합, 정확도 80% 목표

### 8.3 우선순위 포인트

1. **P0/P1/P2 명칭 고객 전달 시**
   - 제안: "즉시 개선" / "단기 설계" / "개발 협업"
   - 영업팀 피드백 필요

2. **우선순위 시작점 고객사별 조정**
   - ✅ 제안: 가능. `--priority-strategy` 플래그 추가
   - 예: `--priority-strategy rag_first` (차란), `--priority-strategy all_parallel` (다른 고객사)

---

## 9. 다음 단계

1. **AX팀 리뷰 & 합의** (1주)
   - 이 기획안 공유 → 8. 합의 필요 사항 논의
   - 노션 안건 2 합의 후 최종 확정

2. **Phase 1 구현** (2주)
   - 계층 1 보강 (마지막 발화·재문의·핑퐁)
   - 차란 데이터로 검증

3. **Phase 2-4 순차 진행** (6주)
   - 계층 2 분리 → 계층 3 분류 → 통합 리포트

4. **고객사 파일럿** (2주)
   - 차란 재분석 (235건 BP)
   - 영업 메시지 자동 생성 검증

---

*v1.0 / 2026-05-08 / Eren*

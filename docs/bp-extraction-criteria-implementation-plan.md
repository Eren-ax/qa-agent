# Best Practice 추출 기준 구현 계획

**작성일**: 2026-05-08  
**대상**: qa-agent 코드베이스  
**참고**: [노션 안건 1 - BP란 무엇인가](https://www.notion.so/channelio/1-BP-35874b55ec7c81a6b604fb1ddf154e81)

---

## 목차

1. [현재 qa-agent 아키텍처 분석](#1-현재-qa-agent-아키텍처-분석)
2. [3계층 구현 전략](#2-3계층-구현-전략)
3. [데이터 플로우 설계](#3-데이터-플로우-설계)
4. [Phase별 구현 계획](#4-phase별-구현-계획)
5. [구현 난이도 평가](#5-구현-난이도-평가)
6. [산출물 설계](#6-산출물-설계)

---

## 1. 현재 qa-agent 아키텍처 분석

### 1.1 데이터 플로우

```
sop-agent clustering
    ↓
[tools/best_practice_extractor.py]
    ├─ extract_best_practices()
    └─ quality_score (현재: 단일 점수)
    ↓
[run_bp_qa.py]
    ├─ generate_scenarios (Layer 1/2/3)
    └─ execute QA tests
    ↓
transcripts.jsonl
    ↓
[tools/scoring_agent.py]
    └─ QA Score (10점 척도)
    ↓
[tools/integrated_report_generator.py]
    └─ HTML 리포트
```

### 1.2 현재 구현된 기능

| 모듈 | 기능 | 측정 지표 |
|------|------|----------|
| `best_practice_extractor.py` | BP 추출 | `quality_score` (단일) |
| `scenario_runner.py` | QA 실행 | transcript 수집 |
| `scoring_agent.py` | 채점 | 정확성(5) + 완결성(3) + 톤(2) |
| `integrated_report_generator.py` | 리포트 | HTML (BP vs ALF) |

### 1.3 sop-agent clustering 데이터 구조

`*_clustered.xlsx`에서 사용 가능한 컬럼:

```python
# 이미 있는 것
- cluster_id, label, category, cluster_size
- enhanced_text  # 전체 대화 텍스트
- url, id  # UserChat 링크, ID
- state  # closed, opened
- profile.csat  # 고객 만족도
- tags, priority
- alfTriggered  # ALF 작동 여부
- timeToFirstAnswer  # 응답 시간
- replyCount  # 턴 수

# 새로 활용 가능한 것 (있는지 확인 필요)
- createdAt, closedAt  # 생성/종료 시간
- channelId, userId  # 재문의 추적용
- firstUserMessage, lastUserMessage  # 첫/마지막 발화
```

### 1.4 부족한 부분

| 노션 기준 | 현재 qa-agent | 데이터 존재 여부 | 구현 방법 |
|----------|-------------|---------------|-----------|
| 재문의 여부 | ❌ | ⚠️ `userId` + `createdAt`로 추정 가능 | 전체 데이터셋 교차 분석 |
| 마지막 발화 긍정 | ❌ | ⚠️ `enhanced_text`에서 추출 | LLM 감정 분석 |
| 응대 품질 5차원 | ❌ | ✅ transcript 있음 | scoring_agent 확장 |
| 도입 난이도 분류 | ❌ | ⚠️ `enhanced_text` + `alfTriggered` | LLM 분류기 |

---

## 2. 3계층 구현 전략

### 계층 1: 고객 만족 (Outcome)

**구현 위치**: `tools/best_practice_extractor.py`

**현재 코드**:
```python
# tools/best_practice_extractor.py:159-179
cluster_df['quality_score'] = 0.0
cluster_df.loc[cluster_df['state'] == 'closed', 'quality_score'] += 1.0
cluster_df.loc[cluster_df['profile.csat'] > 0, 'quality_score'] += 1.0
# ... (생략)
```

**개선 코드**:
```python
# tools/outcome_scorer.py (신규)
def calculate_outcome_score(row: pd.Series, all_data: pd.DataFrame) -> dict:
    """계층 1: 고객 만족 점수 (0~7.0)"""
    scores = {
        'resolved': 2.0 if row['state'] == 'closed' else 0.0,
        'csat': 1.5 if row.get('profile.csat', 0) >= 4 else 0.0,
        'last_message_positive': 0.0,  # LLM 분석 필요
        'no_repeat_inquiry': 1.0,  # 재문의 체크
        'pingpong_penalty': 0.0,  # 과다 핑퐁 감점
        'response_time_penalty': -0.5 if row.get('timeToFirstAnswer', 0) > 3600 else 0.0,
    }
    
    # 마지막 발화 긍정 분석 (선택적)
    if 'enhanced_text' in row and pd.notna(row['enhanced_text']):
        last_msg_score = analyze_last_message(row['enhanced_text'])
        scores['last_message_positive'] = last_msg_score
    
    # 재문의 체크 (전체 데이터 필요)
    has_repeat = check_repeat_inquiry(row, all_data)
    if has_repeat:
        scores['no_repeat_inquiry'] = 0.0
    
    # 핑퐁 과다 감점
    if row.get('replyCount', 0) > 10:
        scores['pingpong_penalty'] = -0.3
    
    return {
        'scores': scores,
        'total': sum(scores.values())
    }
```

**데이터 요구사항**:
- ✅ 이미 있음: `state`, `profile.csat`, `timeToFirstAnswer`, `replyCount`
- ⚠️ 추출 필요: `enhanced_text`에서 마지막 USER 메시지
- ⚠️ 분석 필요: `userId` + `createdAt`로 재문의 추적 (계산 비용 큼)

**구현 난이도**: 🟡 중 (LLM 호출 + 전체 데이터 교차 분석)

### 계층 2: 응대 품질 (Process)

**구현 위치**: `tools/scoring_agent.py`

**현재 코드**:
```python
# tools/scoring_agent.py (기존)
def score_transcript(transcript, best_practice) -> dict:
    return {
        'accuracy': 5,      # 정확성
        'completeness': 3,  # 완결성
        'tone': 2,          # 톤&매너
        'total': 10
    }
```

**개선 코드**:
```python
# tools/scoring_agent.py (확장)
def score_transcript_v2(transcript, best_practice) -> dict:
    """계층 2: 응대 품질 5차원 평가"""
    
    # LLM Judge 프롬프트
    prompt = f"""
    다음 ALF 응대를 Best Practice와 비교하여 5차원으로 평가하세요.
    
    [Best Practice]
    {best_practice['enhanced_text']}
    
    [실제 ALF 응대]
    {format_transcript(transcript)}
    
    평가 기준:
    1. 정확성 (5점): BP와 동일한 정보 제공
    2. 완결성 (3점): 필요한 정보 모두 포함
    3. 구체성 (1점): 구체적 정보 (숫자/날짜/링크)
    4. 공감 (1점): 고객 감정 이해·반영
    5. 간결성 (0점, 참고용): 불필요한 말 없이 명확
    
    Output JSON:
    {{
        "accuracy": {{"score": 0-5, "reason": "..."}},
        "completeness": {{"score": 0-3, "reason": "..."}},
        "specificity": {{"score": 0-1, "reason": "..."}},
        "empathy": {{"score": 0-1, "reason": "..."}},
        "brevity": {{"score": 0-10, "reason": "..."}}  // 참고용
    }}
    """
    
    result = llm_call(prompt, model="claude-sonnet-4-6")
    scores = json.loads(result)
    
    return {
        'accuracy': scores['accuracy'],
        'completeness': scores['completeness'],
        'specificity': scores['specificity'],
        'empathy': scores['empathy'],
        'brevity': scores['brevity'],
        'total': (
            scores['accuracy']['score'] +
            scores['completeness']['score'] +
            scores['specificity']['score'] +
            scores['empathy']['score']
        )
    }
```

**데이터 요구사항**:
- ✅ 이미 있음: `transcripts.jsonl`, BP `enhanced_text`
- ✅ LLM 호출만 필요

**구현 난이도**: 🟢 쉬움 (기존 scoring_agent 확장)

### 계층 3: 도입 난이도 (Adoption)

**구현 위치**: `tools/adoption_classifier.py` (신규)

**구현 코드**:
```python
# tools/adoption_classifier.py (신규)
def classify_task_type(case: BestPracticeCase) -> dict:
    """계층 3: 도입 난이도 자동 분류"""
    
    # 1차: 휴리스틱 분류
    heuristic_result = heuristic_classify(case)
    
    # 2차: LLM 검증 (불확실할 때만)
    if heuristic_result['confidence'] < 0.7:
        llm_result = llm_classify(case)
        return llm_result
    
    return heuristic_result


def heuristic_classify(case: BestPracticeCase) -> dict:
    """휴리스틱 기반 분류 (빠름, 비용 없음)"""
    text = case.enhanced_text.lower()
    
    # Function Task 키워드
    function_keywords = [
        '주문 취소', '반품', '교환', '재고 확인', '배송 조회',
        '포인트 적립', '쿠폰 발급', '회원 등급', 'api', '연동',
        '어드민', '시스템', '데이터베이스'
    ]
    if any(kw in text for kw in function_keywords):
        return {
            'task_type': 'Function Task',
            'confidence': 0.8,
            'reason': f'키워드 매칭: {[kw for kw in function_keywords if kw in text]}'
        }
    
    # Text Task 키워드
    text_task_keywords = [
        '경우', '상황', '조건', '만약', '~면', '~하면',
        '상태별', '타입별', '케이스별'
    ]
    if any(kw in text for kw in text_task_keywords):
        return {
            'task_type': 'Text Task',
            'confidence': 0.7,
            'reason': '조건 분기 패턴 감지'
        }
    
    # RAG (기본값)
    if case.alf_triggered:
        return {
            'task_type': 'RAG',
            'confidence': 0.9,
            'reason': 'ALF 작동 + 단순 정보 제공'
        }
    
    return {
        'task_type': 'RAG',
        'confidence': 0.5,
        'reason': '기본값 (LLM 검증 필요)'
    }


def llm_classify(case: BestPracticeCase) -> dict:
    """LLM 기반 분류 (정확하지만 비용 있음)"""
    prompt = f"""
    다음 상담 케이스를 ALF 처리 방식으로 분류하세요.
    
    고객 의도: {case.intent}
    대화 내용:
    {case.enhanced_text[:800]}
    
    분류 기준:
    - RAG: 지식베이스 검색으로 답변 가능 (FAQ, 상품 정보, 일반 문의)
    - Text Task: 조건 분기 필요 (주문 상태별 안내, 회원 등급별 혜택)
    - Function Task: 외부 API/어드민 연동 필요 (주문 취소, 재고 조회, 포인트 적립)
    
    Output JSON only:
    {{
        "task_type": "RAG|Text Task|Function Task",
        "confidence": 0.0-1.0,
        "reason": "분류 근거 (한 문장)"
    }}
    """
    
    result = llm_call(prompt, model="claude-haiku-4-5")  # 비용 절감
    return json.loads(result)
```

**데이터 요구사항**:
- ✅ 이미 있음: `enhanced_text`, `intent`, `alfTriggered`
- ⚠️ LLM 호출 비용 (불확실 케이스만, haiku 사용)

**구현 난이도**: 🟡 중 (휴리스틱 + LLM 조합)

---

## 3. 데이터 플로우 설계

### 3.1 개선된 플로우

```
sop-agent clustering (*_clustered.xlsx)
    ↓
[tools/best_practice_extractor.py]
    ├─ extract_best_practices()
    ├─ [NEW] calculate_outcome_score()  ← 계층 1
    └─ BestPracticeCase {
        outcome_score: 7.0,
        outcome_breakdown: {resolved, csat, ...}
    }
    ↓
[run_bp_qa.py]
    ├─ generate_scenarios
    ├─ execute QA tests
    └─ [NEW] classify_task_type()  ← 계층 3
    ↓
transcripts.jsonl + task_type
    ↓
[tools/scoring_agent.py]
    └─ [UPDATED] score_transcript_v2()  ← 계층 2
    ↓
scores.json {
    outcome_score: {...},      // 계층 1
    process_score: {...},      // 계층 2
    task_type: "RAG",          // 계층 3
    priority: "P0"             // 종합 우선순위
}
    ↓
[tools/integrated_report_generator.py]
    ├─ 고객용 리포트 (BP vs ALF)
    └─ [NEW] 내부용 대시보드 (우선순위 분포)
```

### 3.2 데이터 스키마 변경

**BestPracticeCase** (기존 확장):
```python
@dataclass
class BestPracticeCase:
    # 기존 필드
    user_chat_id: str
    user_chat_url: str
    cluster_id: int
    enhanced_text: str
    # ...
    
    # 계층 1 추가
    outcome_score: float  # 0~7.0
    outcome_breakdown: dict  # {resolved, csat, last_msg, repeat, ...}
    
    # 계층 3 추가
    task_type: str  # "RAG" | "Text Task" | "Function Task"
    task_type_confidence: float  # 0.0~1.0
    task_type_reason: str
```

**TranscriptScore** (신규):
```python
@dataclass
class TranscriptScore:
    scenario_id: str
    
    # 계층 2: 응대 품질 (5차원)
    accuracy: dict  # {score: 5, reason: "..."}
    completeness: dict  # {score: 3, reason: "..."}
    specificity: dict  # {score: 1, reason: "..."}
    empathy: dict  # {score: 1, reason: "..."}
    brevity: dict  # {score: 10, reason: "..."}
    
    process_total: float  # 0~10.0
    
    # 종합
    priority: str  # "P0" | "P1" | "P2" | "P3"
```

---

## 4. Phase별 구현 계획

### Phase 1: 계층 1 보강 (1주, 즉시 가능)

**목표**: outcome_score 확장

**작업 내용**:
1. `tools/outcome_scorer.py` 신규 생성
   - `calculate_outcome_score()` 구현
   - 마지막 발화 분석 (선택적, LLM)
   - 재문의 체크 (선택적, 계산 비용 큼)

2. `tools/best_practice_extractor.py` 수정
   - `quality_score` → `outcome_score` 변경
   - `BestPracticeCase`에 `outcome_breakdown` 추가

3. 테스트
   - 벨리에v2 데이터로 검증
   - outcome_score 분포 확인 (0~7.0)

**산출물**:
- `tools/outcome_scorer.py`
- `best_practice_extractor.py` 수정
- 테스트 스크립트

**구현 난이도**: 🟢 쉬움 (기존 로직 확장)

**LLM 비용**: 
- 마지막 발화 분석: 100건 × $0.003 = $0.30 (선택적)
- 재문의 체크: 계산만, LLM 불필요

### Phase 2: 계층 3 분류 (1주)

**목표**: task_type 자동 분류

**작업 내용**:
1. `tools/adoption_classifier.py` 신규 생성
   - `heuristic_classify()` 구현 (키워드 기반)
   - `llm_classify()` 구현 (불확실 케이스용)

2. `run_bp_qa.py` 수정
   - BP 추출 후 task_type 분류 추가
   - `transcripts.jsonl`에 task_type 저장

3. 테스트
   - 차란 데이터 (235건) 분류 정확도 검증
   - P0/P1/P2 분포 확인

**산출물**:
- `tools/adoption_classifier.py`
- `run_bp_qa.py` 수정

**구현 난이도**: 🟡 중 (휴리스틱 + LLM)

**LLM 비용**:
- 휴리스틱 신뢰도 높으면 LLM 호출 30% 정도
- 100건 × 0.3 × $0.001 (haiku) = $0.03

### Phase 3: 계층 2 분리 (2주)

**목표**: 응대 품질 5차원 평가

**작업 내용**:
1. `tools/scoring_agent.py` 대폭 수정
   - `score_transcript_v2()` 구현
   - LLM Judge 프롬프트 5차원 분리
   - `TranscriptScore` 스키마 적용

2. 프롬프트 작성
   - `prompts/scoring_5dimensions.md` 생성
   - 각 차원별 평가 기준 상세화

3. 테스트
   - 기존 차란 리포트와 비교
   - 5차원 점수 분포 확인

**산출물**:
- `scoring_agent.py` v2
- `prompts/scoring_5dimensions.md`

**구현 난이도**: 🟢 쉬움 (기존 코드 확장)

**LLM 비용**:
- 100건 × $0.015 (sonnet, 긴 프롬프트) = $1.50
- **가장 비용 큼** (케이스당 실행)

### Phase 4: 통합 리포트 (1주)

**목표**: 이중 목적 산출물

**작업 내용**:
1. `tools/integrated_report_generator.py` 확장
   - 고객용: 기존 HTML + 베스트 사유 자동 생성
   - 내부용: 우선순위 분포 대시보드 (신규)

2. 우선순위 산정 로직
   - `calculate_priority()` 함수
   - P0/P1/P2/P3 분류

3. 자동화율 예측
   - `estimate_automation_rate()` 함수
   - 영업 메시지 자동 생성

**산출물**:
- `integrated_report_generator.py` v2
- `templates/internal_dashboard.html` (신규)

**구현 난이도**: 🟡 중 (HTML 템플릿 작업)

**LLM 비용**: $0 (계산만)

---

## 5. 구현 난이도 평가

### 5.1 기술적 난이도

| Phase | 난이도 | 주요 챌린지 | 해결 방안 |
|-------|--------|------------|----------|
| Phase 1 | 🟢 쉬움 | 재문의 체크 계산 비용 | 선택적 기능으로 구현, 기본 off |
| Phase 2 | 🟡 중 | 휴리스틱 정확도 | 차란 데이터로 검증 후 개선 |
| Phase 3 | 🟢 쉬움 | 프롬프트 엔지니어링 | 기존 scoring_agent 확장 |
| Phase 4 | 🟡 중 | HTML 템플릿 작업 | 기존 리포트 참고 |

### 5.2 LLM 비용 추정

**100건 BP 기준**:

| 단계 | LLM 호출 | 모델 | 단가 | 비용 |
|------|---------|------|------|------|
| Phase 1: 마지막 발화 | 100건 (선택) | sonnet | $0.003 | $0.30 |
| Phase 2: task_type | 30건 (불확실) | haiku | $0.001 | $0.03 |
| Phase 3: 응대 품질 | 100건 | sonnet | $0.015 | $1.50 |
| **합계** | - | - | - | **$1.83** |

**결론**: 100건 기준 약 $2 이하로 저렴함. 차란 235건도 $5 이하.

### 5.3 데이터 가용성

| 데이터 | 존재 여부 | 대안 |
|--------|----------|------|
| `state`, `CSAT` | ✅ 있음 | - |
| `enhanced_text` | ✅ 있음 | - |
| `alfTriggered` | ✅ 있음 | - |
| `replyCount` | ✅ 있음 | - |
| `userId` | ⚠️ 확인 필요 | 없으면 재문의 체크 skip |
| `lastUserMessage` | ⚠️ 확인 필요 | `enhanced_text`에서 파싱 |

**Action**: 벨리에v2 clustering Excel 컬럼 확인 필요

---

## 6. 산출물 설계

### 6.1 고객 컴펀용 리포트

**기존**: `QA_REPORT_*.html`
- BP vs ALF 2열 비교
- 10점 척도 점수

**개선**:
- ✅ 유지: 2열 레이아웃
- ➕ 추가: "베스트 사유" 자동 생성
- ➕ 추가: 5차원 점수 세부 항목
- ➕ 추가: Google Sheets export (드롭다운)

**예시**:
```html
<div class="case">
  <h3>케이스 #1: 데님 팬츠 재입고 문의</h3>
  
  <div class="best-reason">
    ✨ <b>베스트 사유</b>: 고객이 원하는 정보를 즉시 제공하고 대안까지 안내
  </div>
  
  <div class="comparison">
    <div class="bp">...</div>
    <div class="alf">...</div>
  </div>
  
  <div class="scores">
    <div>정확성: 5/5 ⭐⭐⭐⭐⭐</div>
    <div>완결성: 3/3 ⭐⭐⭐</div>
    <div>구체성: 1/1 ⭐</div>
    <div>공감: 1/1 ⭐</div>
  </div>
</div>
```

### 6.2 내부 산정용 대시보드

**신규**: `DASHBOARD_*.html`

**구성**:

```
┌────────────────────────────────────────┐
│ 📊 BP 분석 대시보드 (벨리에v2)         │
├────────────────────────────────────────┤
│                                        │
│ 총 BP: 235건                           │
│                                        │
│ ▶ 우선순위 분포                         │
│   P0 (즉시 개선): 186건 (79.1%) 🟢     │
│   P1 (단기 설계): 23건 (9.8%) 🟡       │
│   P2 (개발 협업): 49건 (20.9%) 🔴      │
│                                        │
│ ▶ 처리 방식                            │
│   RAG: 197건 (83.8%)                   │
│   Text Task: 11건 (4.7%)               │
│   Function Task: 49건 (20.9%)          │
│                                        │
│ ▶ 자동화율 예측                        │
│   즉시 (RAG): 79.1%                    │
│   단기 (~몇 주): 88.9%                  │
│   장기 (~몇 개월): 100%                 │
│                                        │
│ ▶ 영업 메시지                          │
│   "벨리에님 봇 인계 케이스의 약 79%는   │
│   ALF로 즉시 가져올 수 있고, 21%는     │
│   어드민 연동 후 가능해요."            │
│                                        │
└────────────────────────────────────────┘

[P0 상세 케이스 리스트]
1. 데님 팬츠 재입고 (cluster 7) - RAG
2. 반품 수거 지연 (cluster 4) - RAG
...

[P2 상세 케이스 리스트]
1. 주문 취소 (cluster 10) - Function Task
2. 포인트 적립 (cluster 15) - Function Task
...
```

### 6.3 출력 파일 구조

```
storage/qa_run_20260508/
├── transcripts.jsonl          # 기존
├── scores.json                # 확장 (3계층 점수)
├── QA_REPORT_client.html      # 고객용 (개선)
├── DASHBOARD_internal.html    # 내부용 (신규)
├── best_practice_analysis.md  # 선정 근거 (신규)
└── automation_estimate.json   # 자동화율 예측 (신규)
```

**scores.json 스키마**:
```json
{
  "scenario_id": "bp_6997a6f8_c7_layer3",
  "bp_url": "https://desk.channel.io/...",
  
  "outcome_score": {
    "total": 6.5,
    "breakdown": {
      "resolved": 2.0,
      "csat": 1.5,
      "last_message_positive": 1.0,
      "no_repeat_inquiry": 1.0,
      "pingpong_penalty": 0.0,
      "response_time_penalty": 0.0
    }
  },
  
  "process_score": {
    "total": 10.0,
    "accuracy": {"score": 5, "reason": "정확한 정보 제공"},
    "completeness": {"score": 3, "reason": "모든 정보 포함"},
    "specificity": {"score": 1, "reason": "구체적 날짜 제시"},
    "empathy": {"score": 1, "reason": "공감 표현 적절"},
    "brevity": {"score": 8, "reason": "간결함"}
  },
  
  "adoption": {
    "task_type": "RAG",
    "confidence": 0.9,
    "reason": "지식베이스 검색으로 해결 가능"
  },
  
  "priority": "P0",
  "priority_reason": "outcome ≥ 6.0 + process ≥ 10.0 + RAG"
}
```

---

## 7. 실행 계획

### Week 1: Phase 1 + Phase 2

**Day 1-2**: Phase 1 구현
- `tools/outcome_scorer.py` 작성
- `best_practice_extractor.py` 수정
- 테스트

**Day 3-5**: Phase 2 구현
- `tools/adoption_classifier.py` 작성
- 휴리스틱 키워드 튜닝
- 차란 데이터 검증

### Week 2: Phase 3

**Day 1-3**: scoring_agent 확장
- 5차원 프롬프트 작성
- `score_transcript_v2()` 구현

**Day 4-5**: 테스트 & 검증
- 기존 리포트와 비교
- 점수 분포 분석

### Week 3: Phase 4

**Day 1-3**: 리포트 생성
- 내부 대시보드 템플릿
- 자동화율 계산

**Day 4-5**: 통합 테스트
- 차란 데이터 end-to-end
- 영업 메시지 검증

---

## 8. 검증 기준

### 8.1 Phase 1 검증

**벨리에v2 데이터 (3000건)**:
- outcome_score 분포: 평균 4~5점 예상
- 상위 20%: 6점 이상
- 하위 20%: 3점 이하

**Pass 기준**:
- ✅ 기존 quality_score와 상관계수 > 0.7
- ✅ 재문의 케이스가 실제로 낮은 점수

### 8.2 Phase 2 검증

**차란 데이터 (235건)**:
- task_type 분포: RAG 70~80%, Text 10~15%, Function 20%
- 휴리스틱 정확도: > 70%

**Pass 기준**:
- ✅ 수동 분류 30건 샘플과 비교 → 정확도 > 80%
- ✅ LLM 분류와 휴리스틱 일치율 > 70%

### 8.3 Phase 3 검증

**차란 QA 결과 (100건)**:
- 5차원 점수가 기존 10점 척도와 비슷한 분포
- 정확성 > 완결성 > 구체성 순 중요도

**Pass 기준**:
- ✅ 기존 total score와 상관계수 > 0.8
- ✅ 5차원 중 정확성이 가장 큰 영향

### 8.4 Phase 4 검증

**차란 영업 메시지**:
- 노션 결과: "56% 즉시, 44% 연동 후"
- qa-agent 결과: 비슷한 비율 (±10%)

**Pass 기준**:
- ✅ 자동화율 예측이 노션 수동 분석과 ±10% 이내
- ✅ 고객 컴펀 가능한 HTML 리포트 생성

---

## 9. 리스크 & 대응

### 9.1 데이터 부족 리스크

**리스크**: `userId`, `lastUserMessage` 컬럼이 없을 수 있음

**대응**:
- Plan A: `enhanced_text` 파싱으로 대체
- Plan B: 재문의 체크 기능 선택적으로 구현 (기본 off)

### 9.2 LLM 비용 리스크

**리스크**: Phase 3 (응대 품질) 비용이 예상보다 클 수 있음

**대응**:
- 프롬프트 최적화 (토큰 수 줄이기)
- Haiku 사용 검토 (정확도 vs 비용)
- 배치 처리로 할인 활용

### 9.3 정확도 리스크

**리스크**: task_type 자동 분류 정확도 < 80%

**대응**:
- 휴리스틱 키워드 지속 보강
- LLM 프롬프트 Few-shot 추가
- 사용자 피드백 루프 (수동 수정 → 학습)

---

## 10. 다음 단계

### 즉시 실행 가능

1. **벨리에v2 데이터 컬럼 확인**
   ```bash
   python3 -c "
   import pandas as pd
   df = pd.read_excel('~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx')
   print(df.columns.tolist())
   "
   ```

2. **Phase 1 구현 시작**
   - `tools/outcome_scorer.py` 생성
   - 기본 로직 구현 (마지막 발화, 재문의 제외)

### 합의 필요

1. **LLM 비용 승인** ($5~10 / 235건 차란)
2. **Phase 우선순위** (1→2→3→4 순서 맞는지)
3. **산출물 포맷** (내부 대시보드 필요성)

---

*v1.0 / 2026-05-08 / Eren*
*실제 구현 가능한 수준으로 작성됨*

# sop-agent → qa-agent 통합 워크플로우

sop-agent의 상담 데이터 분석 결과를 기반으로 Best Practice를 자동 추출하고, QA 시나리오를 생성하여 ALF 성능을 테스트하는 end-to-end 워크플로우입니다.

## 📊 전체 파이프라인

```
sop-agent 분석 결과 (clustering + extraction)
    │
    ▼
Step 1: Best Practice 추출
    │   - Cluster별 대표 케이스 선정
    │   - 볼륨 비례 샘플링
    │   - 품질 기반 우선순위
    │
    ▼
Step 2: QA 시나리오 생성
    │   - Best Practice → initial_message
    │   - Layer 1/2/3 랜덤 선택
    │   - Style bank 활용 (자연스러운 발화)
    │
    ▼
Step 3: ALF 테스트 실행
    │   - Playwright + headless Chrome
    │   - 실제 채널에서 대화
    │   - Transcript 수집
    │
    ▼
Step 4: QA 리포트 생성
    │   - BP vs 실제 ALF 비교
    │   - 점수 산정 (정확성/완결성/톤)
    │   - HTML 시각화 리포트
    │
    ▼
최종 산출물: QA_REPORT_*.html + transcripts.jsonl
```

## 🎯 Step 1: Best Practice 추출

### 입력
- `<sop_results_dir>/01_clustering/<client>_clustered.xlsx` — sop-agent Stage 1 결과

### 실행
```python
from tools.best_practice_extractor import extract_best_practices, generate_bp_report

# Best Practice 추출
cases = extract_best_practices(
    clustered_excel="~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx",
    target_total=100,
    filters={
        "min_cluster_size": 10,    # 최소 클러스터 크기
        "require_alf": False,       # ALF 작동 필수 여부
        "max_per_cluster": 10,      # 클러스터당 최대 케이스
    }
)

# 선정 리포트 생성
generate_bp_report(cases, "storage/best_practice_selection.md")

print(f"✅ Extracted {len(cases)} cases")
```

### 출력
- `storage/best_practice_selection.md` — 선정된 케이스 리스트
- `List[BestPracticeCase]` — Python 객체

### 선정 로직

1. **Cluster별 할당량 계산**
   - 클러스터 크기에 비례하여 케이스 수 할당
   - 예: 1000건 클러스터 → 10개, 100건 클러스터 → 1개

2. **품질 점수 산정**
   ```python
   quality_score = 0.0
   + 1.0  if state == 'closed'         # 해결됨
   + 1.0  if CSAT > 0                  # 긍정 평가
   + 0.5  if priority_tag present      # 우선순위 태그
   + 0.5  if ALF triggered            # ALF 작동
   - 0.5  if time_to_answer > 1h      # 응답 지연
   ```

3. **샘플링**
   - 각 클러스터에서 quality_score 상위 50% 추출
   - 그 중에서 랜덤 샘플링 (다양성 확보)

## 🎨 Step 2: QA 시나리오 생성

### 입력
- `List[BestPracticeCase]` from Step 1
- `style_bank.json` — 고객 발화 스타일 (선택)

### 실행
```python
from tools.scenario_generator import generate_scenarios_from_bp

scenarios = generate_scenarios_from_bp(
    bp_cases=cases,
    style_bank_path="storage/charan_style_bank_100.json",  # 선택
    layer_strategy="random",  # random, balanced, or specific layer
)

# Save scenarios
import json
with open("storage/scenarios.json", "w", encoding="utf-8") as f:
    json.dump([s.__dict__ for s in scenarios], f, ensure_ascii=False, indent=2)
```

### Layer 전략

| Layer | 설명 | 발화 생성 방식 |
|-------|------|----------------|
| **Layer 1** | Style Reference Injection | LLM이 실제 발화 스타일 참고하여 생성 |
| **Layer 2** | Utterance Transplant | 실제 고객 발화 그대로 재사용 (가장 자연스러움) |
| **Layer 3** | Layer 1 + Validation | 생성 후 스타일 검증, 재시도 |

**권장:** `layer_strategy="random"` (균등 분포로 다양성 확보)

### 출력
- `storage/scenarios.json` — QA 시나리오 리스트
- 각 시나리오 포함:
  - `id`, `intent`, `initial_message`
  - `bp_url` — Best Practice 원본 링크
  - `cluster_id`, `cluster_category`
  - `layer` — 사용된 Layer 번호

## 🚀 Step 3: ALF 테스트 실행

### 입력
- `storage/scenarios.json` from Step 2
- `channel_url` — 테스트 채널 URL

### 실행
```bash
python3 run_qa_from_scenarios.py \
  --scenarios storage/scenarios.json \
  --channel-url https://eoz6p.channel.io \
  --output-dir storage/qa_run_$(date +%Y%m%d) \
  --timeout 120.0
```

### 프로세스

1. **Playwright 초기화**
   - Headless Chrome 실행
   - Anti-detection 설정 (stealth mode)

2. **각 시나리오 실행**
   ```python
   for scenario in scenarios:
       # 채널 열기
       await driver.open(channel_url)
       
       # 초기 메시지 전송
       await driver.send(scenario.initial_message)
       
       # ALF 응답 대기
       replies = await driver.wait_reply(timeout=120.0)
       
       # Transcript 저장
       transcript = {
           'scenario_id': scenario.id,
           'turns': [...],
           'terminated_reason': 'completed',
       }
   ```

3. **Turn 진행**
   - Persona LLM이 고객 역할
   - ALF 응답 분석 → 다음 발화 생성
   - Max 6 turns까지 진행

### 출력
- `storage/qa_run_*/transcripts.jsonl` — 모든 대화 기록
- 각 라인: JSON object (scenario + transcript)

## 📊 Step 4: QA 리포트 생성

### 입력
- `storage/qa_run_*/transcripts.jsonl` from Step 3
- `<sop_results_dir>/01_clustering/<client>_clustered.xlsx` — BP 기대값

### 실행
```bash
python3 generate_qa_report.py \
  --transcripts storage/qa_run_20260508/transcripts.jsonl \
  --clustered-excel ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx \
  --output-dir storage/qa_run_20260508 \
  --report-name "QA_REPORT_차란_$(date +%Y%m%d)"
```

### QA 채점 기준

| 항목 | 배점 | 기준 |
|------|------|------|
| **정확성** | 5점 | BP와 동일한 정보 제공 (5점), 상담원 연결 (3점) |
| **완결성** | 3점 | 필요한 정보 모두 포함 |
| **톤&매너** | 2점 | 친근하고 적절한 고객 응대 |

**감점 사유:**
- Error 종료: 0점
- `</thinking>` 노출: 0점
- Timeout (응답 없음): 0점

### 출력 파일

1. **`QA_REPORT_*.html`** — 시각화 리포트
   - BP vs 실제 ALF 대화 나란히 비교
   - 2열 그리드 레이아웃
   - 결과별 섹션 (성공/부분성공/타임아웃/오류)

2. **`QA_REPORT_*.md`** — Markdown 버전

3. **`qa_scores.json`** — 점수 데이터

### HTML 리포트 구조

```
┌─────────────────────────────────────────────────┐
│ 📊 전체 요약                                     │
│ - 성공: X건 (X%), 평균 X점                       │
│ - 부분 성공: X건 (X%), 평균 X점                  │
│ - 타임아웃: X건 (X%), 평균 X점                   │
│ - 오류: X건 (X%), 평균 X점                       │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ 🟢 성공 케이스                                   │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────┬──────────────────┐        │
│  │ 📋 Best Practice │ 🤖 실제 ALF 대화 │        │
│  │ (클러스터 원본)   │ (테스트 결과)     │        │
│  ├──────────────────┼──────────────────┤        │
│  │ 👤 고객 의도      │ 👤 실제 메시지   │        │
│  │ 💬 (원본 텍스트)  │ 💬 (생성 메시지) │        │
│  │                  │                  │        │
│  │ 🎯 BP 봇 응대    │ 🤖 ALF 응답      │        │
│  │ (빨강 말풍선)     │ (하늘색 말풍선)   │        │
│  └──────────────────┴──────────────────┘        │
│                                                 │
│  📈 메트릭: 턴 수 X, 응대 시간 X초               │
│  📊 QA Score: X/10 (정확성 X + 완결성 X + 톤 X) │
│                                                 │
└─────────────────────────────────────────────────┘
```

## 🔄 전체 실행 예시

### 전체 파이프라인 실행 (One command)
```bash
cd /Users/eren/qa-agent

uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx \
  --channel-url https://eoz6p.channel.io \
  --output-dir storage/qa_run_$(date +%Y%m%d) \
  --target-total 100 \
  --timeout 120.0

# 출력: storage/qa_run_YYYYMMDD/transcripts.jsonl
```

위 명령으로 Step 1-3이 한 번에 실행됩니다:
- Best Practice 추출 (clustering 기반)
- QA 시나리오 생성 (Layer 1/2/3)
- ALF 테스트 실행 (Playwright headless)

### 개별 단계 실행 (고급)

필요시 각 단계를 수동으로 실행할 수 있습니다:

#### 1단계: Best Practice 추출만
```bash
python3 tools/best_practice_extractor.py \
  ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx \
  100

# 출력: storage/best_practice_selection.md
```

#### 2-3단계: 시나리오 생성 + 테스트
위의 `run_bp_qa.py` 사용 (추천)

#### 4단계: QA 리포트 생성
```bash
python3 generate_qa_report.py \
  --transcripts storage/qa_run_20260508/transcripts.jsonl \
  --clustered-excel ~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx \
  --output-dir storage/qa_run_20260508
```

## 🎯 주요 개선사항

### 기존 (Excel 수동 작성)
- ❌ Best Practice 수동 선정 (시간 소요)
- ❌ Excel 포맷 제약
- ❌ 업데이트 어려움

### 개선 (sop-agent 기반)
- ✅ 자동 Best Practice 추출
- ✅ Cluster 기반 균등 분포
- ✅ sop-agent 업데이트 시 자동 반영
- ✅ 실제 고객 발화 스타일 활용

## 📝 설정 파일

### `qa_config.yaml` (선택)
```yaml
best_practice:
  target_total: 100
  min_cluster_size: 10
  max_per_cluster: 10
  require_alf: false

scenario_generation:
  layer_strategy: random  # random, balanced, layer1, layer2, layer3
  style_bank: storage/charan_style_bank_100.json
  max_turns: 6

qa_execution:
  channel_url: https://eoz6p.channel.io
  timeout: 120.0
  headless: true

qa_scoring:
  accuracy_weight: 5
  completeness_weight: 3
  tone_weight: 2
```

## 🔧 트러블슈팅

### Headless 모드에서 "문의하기" 버튼 안 보임
→ `chat_driver.py`에 anti-detection 설정 이미 적용됨 (commit f912f21)

### Layer 2 fallback 빈번
→ Style bank에 해당 cluster의 발화가 부족함. `userchat_style_bank.py`로 재생성

### QA 점수가 모두 낮음
→ Best Practice 기대값(clustering Excel)과 ALF 세팅 불일치. ALF 규칙/지식 업데이트 필요

## 📚 참고 문서

- `docs/layer-comparison.md` — Layer 1/2/3 비교 분석
- `prompts/generate_scenarios_v2.md` — 시나리오 생성 프롬프트
- `prompts/persona_archetypes.md` — Persona 정의
- `tools/chat_driver.py` — Playwright 드라이버 구현

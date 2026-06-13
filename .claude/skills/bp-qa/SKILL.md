---
name: bp-qa
description: Best Practice QA pipeline — sop-agent clustering → BP 추출 → Layer 1/2/3 시나리오 생성 → ALF 테스트 → BP vs ALF 비교 리포트(HTML/MD). 품질 점수(10점 만점)로 실제 우수 케이스 재현 검증.
---

# bp-qa — Best Practice QA Orchestration Spec

You are the **bp-qa orchestrator**. Your job is to take a clustering Excel file
and a test channel URL, extract Best Practice cases, generate Layer 1/2/3 scenarios,
execute QA tests, and produce BP vs ALF comparison reports.

**Core approach**:
1. **Best Practice 기반**: 실제 우수 상담 케이스를 재현
2. **품질 중심 평가**: QA Score (10점 만점) = 정확성(5) + 완결성(3) + 톤&매너(2)
3. **Layer 전략**: Layer 1 (LLM 생성) / Layer 2 (원문 추출) / Layer 3 (검증)
4. **시각적 비교**: BP vs ALF 대화를 2열 레이아웃으로 나란히 표시

---

## When to invoke this skill

A user asks for any of:
- "BP QA 돌려줘 / Best Practice QA 해줘"
- "우수 케이스 재현 테스트 해줘"
- "특정 UserChat 테스트해줘"
- Provides clustering Excel + channel URL

Out of scope (route to a different tool):
- 전체 볼륨 대표성 측정: use `/rag-qa` skill (statistical mirroring)
- 단일 ad-hoc 대화: use `tools/cli.py --record`

---

## First message — mandatory questions on trigger

스킬이 트리거되면 **다른 작업을 시작하기 전에** 반드시 아래 항목들을 한 번에 질문한다.
이미 사용자 메시지에 포함된 항목은 재질문하지 않는다.

1. **Clustering Excel 경로** (`clustered_excel`) — **필수**
   > "sop-agent Stage 1 clustering 결과 Excel 파일 경로를 알려주세요.
   > (예: ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx)"

2. **채널 URL** (`channel_url`) — **필수**
   > "테스트할 Channel.io URL을 알려주세요.
   > (예: https://vqnol.channel.io)"

3. **BP 선택 모드** (`mode`) — 2지선다
   > "Best Practice 선택 방법을 선택해주세요:
   > 1) 자동 추출 (clustering 결과에서 품질 기반 자동 선정, 권장)
   > 2) 수동 지정 (특정 UserChat ID 리스트 제공)"

4. **테스트 케이스 수** (`target_total`) — mode=자동일 때만
   > "몇 개의 Best Practice 케이스를 추출할까요?
   > (기본값: 100, 권장: 50-100)"

5. **수동 BP 파일 경로** (`manual_bp`) — mode=수동일 때만
   > "수동 BP 파일 경로를 알려주세요 (TSV/CSV/Excel).
   > 파일 형식: user_chat_id 또는 url 컬럼 포함
   > (예: ~/manual_bp.tsv)"

6. **Layer 전략** (`layer_strategy`) — 선택
   > "Layer 전략을 선택해주세요:
   > 1) random (Layer 1/2/3 랜덤, 기본값)
   > 2) balanced (Layer 1/2/3 균등 분배)
   > 3) layer1 (LLM 생성만)
   > 4) layer2 (원문 추출만)
   > 5) layer3 (검증된 LLM 생성)"

7. **출력 디렉토리** (`output_dir`) — 선택
   > "결과 저장 경로를 지정하시겠습니까?
   > (기본값: storage/qa_YYYYMMDD)"

---

## Required inputs (gather before starting)

| Input | Required | Default | Description |
|---|---|---|---|
| `clustered_excel` | ✅ | — | sop-agent Stage 1 결과 (`*_clustered.xlsx`) |
| `channel_url` | ✅ | — | 테스트 대상 Channel.io URL |
| `mode` | ✅ | `automatic` | `automatic` (자동 추출) / `manual` (수동 지정) |
| `target_total` | — | `100` | 추출할 BP 케이스 수 (mode=automatic) |
| `manual_bp` | — | — | 수동 BP 파일 경로 (mode=manual) |
| `layer_strategy` | — | `random` | `random` / `balanced` / `layer1` / `layer2` / `layer3` |
| `min_cluster_size` | — | `10` | 최소 클러스터 크기 (mode=automatic) |
| `max_per_cluster` | — | `10` | 클러스터당 최대 케이스 수 (mode=automatic) |
| `headed` | — | `false` | `true`로 설정 시 브라우저 창 표시 |
| `timeout` | — | `120.0` | ALF 응답 대기 시간 (초) |
| `output_dir` | — | `storage/qa_YYYYMMDD` | 결과 저장 경로 |

If any required input is missing or the path doesn't exist, **stop and ask
the user** before proceeding. Do not invent paths.

---

## Output contract

On success, you produce:

```
<output_dir>/
├── transcripts.jsonl           # BP + ALF 대화 기록
├── QA_REPORT_<client>_<date>.html    # BP vs ALF 비교 리포트 (HTML)
└── QA_REPORT_<client>_<date>.md      # 텍스트 요약 리포트 (Markdown)
```

**HTML 리포트 특징**:
- 2열 grid 레이아웃: 좌측 BP 대화, 우측 ALF 대화
- 채팅 말풍선 UI (Channel.io 위젯 스타일)
- QA Score (10점 만점): 정확성(5) + 완결성(3) + 톤&매너(2)
- 성공/부분성공/타임아웃/오류 자동 분류
- 카테고리별 평균 점수 통계

---

## Implementation — Pipeline Phases

### Phase 1 — Extract Best Practice

**Tool**: `tools/best_practice_extractor.py` or `load_manual_bp()`

**Automatic mode**:
```python
from tools.best_practice_extractor import extract_best_practices

bp_cases = extract_best_practices(
    clustered_excel=clustered_excel,
    target_total=target_total,
    filters={
        "min_cluster_size": min_cluster_size,
        "require_alf": False,
        "max_per_cluster": max_per_cluster,
    }
)
```

**Scoring criteria (품질 점수)**:
- 해결됨 (state = "solved"): +10점
- CSAT 높음 (≥4.0): +5점
- ALF 작동 (alfTriggered=True): +3점
- 클러스터 크기 정규화: +0~5점

**Output**: `List[BestPracticeCase]`

**Manual mode**:
User provides TSV/CSV/Excel with columns:
- `user_chat_id` or `url` (required)
- `intent`, `category` (optional)

Looks up full details from clustering Excel.

---

### Phase 2 — Generate Scenarios

**Layer strategies**:

| Layer | Method | Use case |
|---|---|---|
| **Layer 1** | LLM generates message with BP style reference | 자연스러운 변형 생성 |
| **Layer 2** | Extract first user utterance from BP conversation | 원문 재현 (최대 80자) |
| **Layer 3** | Layer 1 + validation (20-100자) | 검증된 생성 |

**Implementation**: Inline in orchestration (no separate tool)

```python
# Layer 1: LLM generation
prompt = f"""Generate customer inquiry that matches:
- Intent: {bp_case.intent}
- Style: {bp_case.enhanced_text[:200]}...
Requirements: 30-80 chars, natural Korean, no greetings"""

# Layer 2: Extract from BP
lines = bp_case.enhanced_text.split("\n")
for line in lines:
    if line.startswith("USER:") or line.startswith("고객:"):
        utterance = line.split(":", 1)[1].strip()
        # Remove greetings, check length <= 80

# Layer 3: Layer 1 + retry validation
```

---

### Phase 3 — Execute QA Tests

**Tool**: `tools/scenario_runner.py`

For each BP case:
1. Generate `initial_message` based on selected layer
2. Create `Scenario` object
3. Run `run_one_scenario()` with Playwright + Persona LLM
4. Collect `Transcript`

**Concurrency**: Sequential with 2s delay between tests

**Output**: `transcripts.jsonl` (one line per BP case)

```jsonl
{
  "bp_url": "https://desk.channel.io/.../user-chats/abc123",
  "bp_user_chat_id": "abc123",
  "bp_intent": "배송 조회",
  "bp_cluster_id": 42,
  "bp_cluster_category": "배송",
  "bp_cluster_size": 87,
  "layer": 2,
  "initial_message": "주문한 상품 배송 언제 오나요?",
  "transcript": { ... }
}
```

---

### Phase 4 — Generate Reports

**Tool**: `tools/bp_qa_report_generator.py`

```python
from tools.bp_qa_report_generator import generate_bp_qa_reports

html_path, md_path = generate_bp_qa_reports(
    transcripts_path=output_dir / "transcripts.jsonl",
    output_dir=output_dir,
    client_name=client_name
)
```

**QA Scoring criteria**:

| 지표 | 배점 | 기준 |
|---|---|---|
| **정확성** | 5점 | BP와 동일한 정보 제공 (5점) / 상담원 연결 제안 (3점) / 오류 (0점) |
| **완결성** | 3점 | 필요한 정보 모두 포함 (3점) / 부분 정보 (1-2점) / 오류 (0점) |
| **톤&매너** | 2점 | 친근하고 적절한 톤 (2점) / 기계적 (1점) / 부적절 (0점) |

**Output**:
- `QA_REPORT_<client>_<timestamp>.html` — 브라우저에서 바로 열기
- `QA_REPORT_<client>_<timestamp>.md` — 텍스트 요약

---

## Orchestration Steps

### Step 1: Validate inputs

Check that all required inputs are provided and paths exist.

### Step 2: Extract Best Practice

Run Phase 1 (automatic or manual mode).

Print:
- Total BP cases extracted
- Distribution by category
- Cluster size statistics

### Step 3: Generate and test scenarios

For each BP case:
1. Select layer based on strategy
2. Generate initial_message
3. Print: case index, cluster info, intent, layer, message preview
4. Run `run_one_scenario()`
5. Collect result
6. Sleep 2 seconds

### Step 4: Save transcripts

Write `transcripts.jsonl` in output_dir.

### Step 5: Generate reports

Run `generate_bp_qa_reports()`.

Print:
- HTML report path
- Markdown report path

### Step 6: Print summary

```
Total tested: X/Y
Success rate: Z%
Layer distribution: Layer 1: A, Layer 2: B, Layer 3: C
✅ HTML 리포트: <path>
✅ Markdown 리포트: <path>
```

Return to the user:
- Output directory path
- HTML report path (open in browser)
- Success rate
- Key statistics

---

## Error Handling

- **File not found**: Stop and ask user to verify paths
- **Empty BP extraction**: Print warning and suggest adjusting filters
- **Test failure**: Continue with remaining tests, mark as failed
- **Report generation failure**: Print manual command for retry

---

## Example Conversation

**User**: "벨리에 BP QA 돌려줘"

**Assistant**:
```
Best Practice QA를 시작합니다.

몇 가지 정보가 필요합니다:

1. Clustering Excel 경로?
   (예: ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx)

2. 채널 URL?
   (예: https://vqnol.channel.io)

3. BP 선택 모드?
   1) 자동 추출 (권장)
   2) 수동 지정

4. 테스트 케이스 수?
   (기본값: 100)

5. Layer 전략?
   1) random (기본값)
   2) balanced
   3) layer1/layer2/layer3
```

**User**: 
```
1. ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx
2. https://vqnol.channel.io
3. 자동 추출
4. 50
5. balanced
```

**Assistant**:
```
✅ 설정 확인:
- Clustering: ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx
- 채널: https://vqnol.channel.io
- 모드: 자동 추출
- 케이스 수: 50
- Layer 전략: balanced

시작하겠습니다...

[Phase 1] Best Practice 추출 중...
✅ 50개 BP 케이스 추출 완료

카테고리별 분포:
  배송: 15
  반품/교환: 12
  상품문의: 10
  ...

[Phase 2-3] 시나리오 생성 및 테스트 실행 중...
[1/50] Cluster 42 — 배송 조회
  Layer: 1
  Message: "주문한 상품 언제 받을 수 있을까요?"
  → completed (3 turns)
...

[Phase 4] 결과 저장 중...
✅ transcripts.jsonl 저장 완료

[Phase 5] 리포트 생성 중...
✅ HTML 리포트 생성 완료
✅ Markdown 리포트 생성 완료

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total tested: 48/50
Success rate: 96.0%

Layer 분포:
  Layer 1: 17
  Layer 2: 16
  Layer 3: 17

평균 QA Score: 7.2/10
  정확성: 3.8/5
  완결성: 2.1/3
  톤&매너: 1.3/2

✅ 결과 저장: storage/qa_20260610/
✅ HTML 리포트: storage/qa_20260610/QA_REPORT_벨리에_20260610.html
   → 브라우저에서 열어보세요!
```

---

## CLI Fallback (manual execution)

If orchestration fails, provide manual command:

```bash
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_$(date +%Y%m%d) \
  --target-total 50 \
  --layer-strategy balanced
```

**Manual BP mode**:
```bash
# 1. Create manual_bp.tsv
cat > manual_bp.tsv <<EOF
user_chat_id	intent
6997a6f8bc02a881342e	데님 팬츠 재입고 문의
6981fe3c37a26d3d48a5	반품 수거 지연
EOF

# 2. Run
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_manual \
  --manual-bp manual_bp.tsv
```

---

## Notes

- **vs. rag-qa**: bp-qa는 우수 케이스 재현, rag-qa는 전체 볼륨 대표성
- **Layer 2 fallback**: Layer 2 추출 실패 시 자동으로 Layer 1로 폴백
- **Timeout**: ALF 응답 없으면 타임아웃 (기본 120초)
- **브라우저**: headless 기본, 디버깅 시 `headed=true`
- **Dependencies**: Playwright, pandas, openpyxl required

# bp-qa — Best Practice QA Skill

ALF 응답 품질을 Best Practice 기반으로 자동 측정하는 Claude Code 스킬.

실제 우수 상담 케이스를 재현하여 ALF와 비교하고, QA Score (10점 만점)로 평가합니다.

---

## 🎯 핵심 특징

### 1. **Best Practice 기반 검증**
- sop-agent clustering 결과에서 품질 높은 케이스 자동 추출
- 해결 상태, CSAT, ALF 작동 여부 기반 우선순위

### 2. **Layer 1/2/3 시나리오 생성**
- **Layer 1**: LLM이 BP 스타일 참고하여 새로운 메시지 생성
- **Layer 2**: BP 대화에서 첫 발화 원문 추출
- **Layer 3**: Layer 1 + 검증 (20-100자)

### 3. **QA Score (10점 만점)**
- **정확성 (5점)**: BP와 동일한 정보 제공 여부
- **완결성 (3점)**: 필요한 정보 포함 여부
- **톤&매너 (2점)**: 친근하고 적절한 톤

### 4. **시각적 비교 리포트**
- BP vs ALF 대화를 2열 레이아웃으로 나란히 표시
- 채팅 말풍선 UI (Channel.io 위젯 스타일)
- 카테고리별 평균 점수 통계

---

## 📦 사용법

### Claude Code에서 실행

```
/bp-qa
```

Claude가 다음 정보를 순서대로 물어봅니다:

1. **Clustering Excel 경로** — sop-agent Stage 1 결과 파일
2. **채널 URL** — 테스트 대상 Channel.io URL
3. **BP 선택 모드** — 자동 추출 / 수동 지정
4. **테스트 케이스 수** — 기본값 100 (자동 모드)
5. **Layer 전략** — random / balanced / layer1/2/3

### 자동 추출 모드 (권장)

clustering 결과에서 품질 기반으로 자동 선정:

```
1. Clustering Excel: ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx
2. 채널 URL: https://vqnol.channel.io
3. 모드: 자동 추출
4. 케이스 수: 50
5. Layer: balanced
```

### 수동 지정 모드

특정 UserChat ID를 직접 지정:

```
1. Clustering Excel: ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx
2. 채널 URL: https://vqnol.channel.io
3. 모드: 수동 지정
4. BP 파일: ~/manual_bp.tsv
```

**manual_bp.tsv 형식**:
```tsv
user_chat_id	intent
6997a6f8bc02a881342e	데님 팬츠 재입고 문의
6981fe3c37a26d3d48a5	반품 수거 지연
```

---

## 📊 출력 산출물

```
storage/qa_YYYYMMDD/
├── transcripts.jsonl                      # BP + ALF 대화 기록
├── QA_REPORT_<client>_<date>.html        # BP vs ALF 비교 리포트 (HTML)
└── QA_REPORT_<client>_<date>.md          # 텍스트 요약 리포트
```

### HTML 리포트 예시

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 벨리에 QA Report — 2026-06-10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total: 50 cases
Success: 42 (84.0%)
평균 QA Score: 7.2/10

┌─────────────────────┬─────────────────────┐
│  Best Practice      │  ALF 실제 응답      │
├─────────────────────┼─────────────────────┤
│ 고객: 주문한 상품    │ 고객: 주문한 상품    │
│ 언제 오나요?        │ 언제 받을 수 있나요? │
│                     │                     │
│ CS: 배송 조회해      │ ALF: 주문번호를      │
│ 드릴게요. 주문번호는 │ 알려주시면 배송      │
│ 무엇인가요?         │ 조회해드리겠습니다.  │
│                     │                     │
│ ✅ QA Score: 8/10   │ ✅ 정확성: 4/5       │
│   정확성: 4/5       │ ✅ 완결성: 3/3       │
│   완결성: 3/3       │ ✅ 톤&매너: 1/2      │
│   톤&매너: 1/2      │                     │
└─────────────────────┴─────────────────────┘
```

---

## 🔧 수동 CLI 실행

Claude Code 없이 직접 실행:

```bash
# 1. 의존성 설치
uv sync
uv run playwright install chromium

# 2. 환경변수 설정
export ANTHROPIC_API_KEY=sk-ant-...

# 3. 자동 추출 모드
uv run python -m tools.bp_qa_runner \
  --clustered-excel ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_$(date +%Y%m%d) \
  --target-total 50 \
  --layer-strategy balanced

# 4. 수동 지정 모드
uv run python -m tools.bp_qa_runner \
  --clustered-excel ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_manual \
  --manual-bp ~/manual_bp.tsv
```

---

## 🆚 bp-qa vs rag-qa

| 항목 | **bp-qa** | **rag-qa** |
|---|---|---|
| **목적** | 우수 케이스 재현 검증 | 전체 볼륨 대표성 측정 |
| **입력** | Clustering Excel | sop-agent 전체 결과 |
| **시나리오** | BP 기반 Layer 1/2/3 | 통계적 미러링 (볼륨 가중) |
| **평가** | QA Score (10점) | 3단계 지표 (coverage × engagement × resolution) |
| **리포트** | BP vs ALF 1:1 비교 | 비즈니스 리포트 + 슬라이드 |
| **사용 시점** | 특정 케이스 검증, 데모 | 정기 측정, 고객사 보고 |

**선택 가이드**:
- 🎯 특정 우수 케이스 재현 필요 → **bp-qa**
- 📊 전체 상담 커버리지 측정 → **rag-qa**
- 🤝 고객사 발표/보고 → **rag-qa** (슬라이드 자동 생성)
- 🔍 개별 케이스 디버깅 → **bp-qa** (1:1 비교 리포트)

---

## 🏗️ 디렉토리 구조

```
skills/bp-qa/
├── SKILL.md                    # Claude Code 스킬 명세
├── README.md                   # 이 파일
├── tools/                      # Python 도구
│   ├── best_practice_extractor.py      # BP 자동 추출
│   ├── best_practice_loader.py         # 수동 BP 로드
│   ├── bp_qa_report_generator.py       # 리포트 생성
│   ├── chat_driver.py                  # Playwright 드라이버
│   ├── scenario_runner.py              # 시나리오 실행
│   ├── llm_client.py                   # LLM 클라이언트
│   └── result_store.py                 # 데이터 I/O
├── prompts/                    # LLM 프롬프트
│   ├── generate_scenarios_v2.md        # Layer 1/2/3 시나리오 생성
│   ├── persona_archetypes.md           # 페르소나 정의
│   └── judge_scenario.md               # QA 채점 루브릭
└── examples/                   # 예시 데이터
    └── sample-run-r-20260413-example/
```

---

## 📝 Layer 전략 상세

### Layer 1: LLM 생성 (스타일 참고)

BP 대화 스타일을 참고하여 LLM이 새로운 메시지 생성:

```
BP enhanced_text (첫 200자):
"고객: 주문한 상품 배송 조회 부탁드립니다. 
CS: 네, 주문번호 알려주시면..."

→ LLM 생성:
"주문한 상품 언제 받을 수 있을까요?"
```

**장점**: 자연스러운 변형, 다양성
**단점**: 원문과 다를 수 있음

### Layer 2: 원문 추출

BP 대화에서 첫 발화를 그대로 추출 (최대 80자):

```
BP enhanced_text:
"USER: 주문한 상품 배송 조회 부탁드립니다.
ALF: 네, 주문번호 알려주시면..."

→ Layer 2:
"주문한 상품 배송 조회 부탁드립니다."
```

**장점**: 원문 재현, 정확성
**단점**: 인사말 포함 가능, 길이 제한

### Layer 3: 검증된 생성

Layer 1 + 검증 (20-100자, 2회 재시도):

```
Layer 1 생성 → 20-100자 체크 → Pass/Retry
```

**장점**: Layer 1 + 길이 보장
**단점**: 재시도 오버헤드

### Layer 전략 선택

| 전략 | 설명 | 사용 시점 |
|---|---|---|
| `random` | Layer 1/2/3 랜덤 (기본값) | 다양성 필요 시 |
| `balanced` | Layer 1/2/3 균등 분배 | 각 Layer 비교 시 |
| `layer1` | LLM 생성만 | 자연스러운 변형 중심 |
| `layer2` | 원문 추출만 | 정확한 재현 중심 |
| `layer3` | 검증된 생성만 | 품질 보장 필요 시 |

---

## 🔍 QA Score 상세

### 정확성 (5점)

| 점수 | 기준 |
|---|---|
| 5점 | BP와 동일한 정보 제공 (완전 일치) |
| 3점 | 상담원 연결 제안 (부분 해결) |
| 0점 | 오류 또는 무관한 답변 |

### 완결성 (3점)

| 점수 | 기준 |
|---|---|
| 3점 | 필요한 정보 모두 포함 |
| 2점 | 주요 정보만 포함 (일부 누락) |
| 1점 | 핵심 정보 누락 |
| 0점 | 정보 없음 |

### 톤&매너 (2점)

| 점수 | 기준 |
|---|---|
| 2점 | 친근하고 적절한 톤 |
| 1점 | 기계적이거나 딱딱한 톤 |
| 0점 | 부적절한 톤 (무례, 공격적) |

---

## 🛠️ 의존성

**Python 패키지**:
- `anthropic>=0.40.0` — LLM 클라이언트
- `playwright>=1.48.0` — 브라우저 자동화
- `pandas>=2.0.0` — 데이터 처리
- `openpyxl>=3.1.0` — Excel 읽기
- `python-dotenv>=1.0.1` — 환경변수
- `pyyaml>=6.0.2` — YAML 파싱

**설치**:
```bash
uv sync
uv run playwright install chromium
```

---

## 📖 관련 문서

- [sop-agent](../userchat-to-sop-pipeline/README.md) — 상담 데이터 분석 (BP QA 입력 생산)
- [rag-qa](../rag-qa/README.md) — 통계적 미러링 QA (볼륨 대표성 측정)
- [Best Practice 선택 가이드](docs/manual-bp-selection.md) — 수동 BP 파일 작성법

---

## 🐛 트러블슈팅

### Clustering Excel을 찾을 수 없습니다

```bash
# 경로 확인
ls -la ~/sop-agent/results/<client>/01_clustering/

# sop-agent Stage 1 실행
cd ~/sop-agent
/userchat-to-sop-pipeline --stage 1
```

### Playwright 브라우저가 없습니다

```bash
uv run playwright install chromium
```

### ANTHROPIC_API_KEY 없음

```bash
# .env 파일 생성
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

### Layer 2 추출 실패

Layer 2는 첫 발화가 80자 이하일 때만 성공. 실패 시 자동으로 Layer 1로 폴백합니다.

### 타임아웃 발생

ALF 응답이 느린 경우 `--timeout` 옵션으로 대기 시간 증가:

```bash
--timeout 180.0  # 3분
```

---

## 📄 라이센스

내부용 도구 (AX팀)

# alf-qa-agent (v3: Best Practice from Clustering)

ALF(채널톡 AI Agent) 응답 품질을 자동 측정하고, 고객사 대상 성과 리포트를 산출하는 도구.

**v3 핵심 개선 (2026-05-08)**:
1. **Best Practice 자동 추출**: sop-agent clustering 결과에서 cluster별 대표 케이스 자동 선정
2. **균등 분포 샘플링**: 클러스터 크기에 비례하여 Best Practice 추출, 모든 intent 커버
3. **품질 기반 우선순위**: CSAT, 해결 상태, 응답 시간 등 품질 지표 기반 케이스 선정
4. **Headless 안정성**: Chrome headless detection 회피 (차란 리뉴얼 채널 대응)
5. **시각화 리포트**: BP vs 실제 ALF 대화를 2열 레이아웃으로 나란히 비교

## 입력

| 입력 | 필수 | 설명 |
|---|---|---|
| `clustered_excel` | **필수** | sop-agent Stage 1 clustering 결과 (`*_clustered.xlsx`) |
| `channel_url` | **필수** | ALF가 세팅된 테스트 채널 URL |
| `target_total` | 선택 | 추출할 Best Practice 케이스 수 (기본 100) |
| `style_bank` | 선택 | 고객 발화 스타일 JSON (Layer 2/3에서 사용) |

sop-agent 결과 중 사용하는 파일:

```
<sop_results_dir>/
└── 01_clustering/
    └── <client>_clustered.xlsx  # 필수 — 클러스터링된 상담 데이터
        ├── cluster_id           # 클러스터 ID
        ├── label                # 클러스터 라벨 (intent)
        ├── category             # 카테고리
        ├── cluster_size         # 클러스터 크기
        ├── enhanced_text        # 고객 메시지 전문
        ├── url                  # UserChat URL (Best Practice 원본)
        ├── state, csat, tags    # 품질 지표
        └── alfTriggered, time*  # ALF 작동 여부, 응답 시간
```

**새로운 기능 (v3)**: 
- clustering 결과에서 자동으로 Best Practice 추출 (수동 Excel 작성 불필요)
- 클러스터 크기 비례 샘플링으로 모든 intent 균등 커버
- 품질 점수 기반 우선순위 (해결됨 > CSAT 높음 > ALF 작동)

이 입력을 받아:
1. Cluster별 대표 Best Practice를 자동 추출하고
2. Layer 1/2/3 전략으로 자연스러운 QA 시나리오 생성하고
3. Playwright로 ALF와 실제 대화를 돌리고
4. BP vs 실제 ALF 비교 리포트를 자동 생성합니다.

## 파이프라인

```
sop-agent clustering 결과 (*_clustered.xlsx)
    │
    ▼
Step 1. Extract Best Practice ─── Best Practice 자동 추출
    │                              - Cluster별 대표 케이스 선정
    │                              - 품질 기반 우선순위
    │                              - 볼륨 비례 샘플링
    │
    ▼
Step 2. Generate Scenarios ─────── QA 시나리오 생성
    │                              - BP → initial_message
    │                              - Layer 1/2/3 전략
    │                              - Style bank 활용
    │
    ▼
Step 3. Execute QA Tests ───────── ALF 테스트 실행
    │                              - Playwright + headless Chrome
    │                              - Persona LLM (고객 역할)
    │                              - transcripts.jsonl
    │
    ▼
Step 4. Generate QA Report ─────── QA 리포트 생성
                                   - BP vs 실제 ALF 비교
                                   - 점수 산정 (10점 만점)
                                   - HTML 시각화 리포트
```

모든 아티팩트는 `storage/<run_dir>/` 아래에 적재됩니다.

**상세 워크플로우**: [`docs/sop-to-qa-workflow.md`](docs/sop-to-qa-workflow.md)

## 핵심 지표

| 지표 | 정의 | 산출 방식 |
|---|---|---|
| **QA Score** | Best Practice 대비 ALF 응답 품질 | 정확성(5) + 완결성(3) + 톤&매너(2) = 10점 만점 |
| **성공률** | 전체 케이스 중 성공 비율 | (성공 케이스 수 / 전체 케이스 수) × 100% |
| **평균 점수** | 결과별 평균 QA Score | 성공/부분성공/타임아웃/오류 각각의 평균 |
| **Cluster 커버리지** | 테스트한 클러스터 비율 | (테스트 클러스터 수 / 전체 클러스터 수) × 100% |

### QA 채점 기준

- **정확성 (5점)**: BP와 동일한 정보 제공 (5점), 상담원 연결 제안 (3점), 오류 (0점)
- **완결성 (3점)**: 필요한 정보 모두 포함 (3점), 부분 정보 (1-2점), 오류 (0점)
- **톤&매너 (2점)**: 친근하고 적절한 톤 (2점), 기계적 (1점), 부적절 (0점)

## 빠른 시작

### 옵션 A: 자동 추출 (추천)

Clustering 결과에서 자동으로 Best Practice를 추출합니다.

```bash
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_$(date +%Y%m%d) \
  --target-total 100
```

### 옵션 B: 수동 지정

특정 UserChat을 직접 지정하여 테스트합니다.

```bash
# 1. manual_bp.tsv 파일 생성 (user_chat_id 또는 url 컬럼)
cat > manual_bp.tsv <<EOF
user_chat_id	intent
6997a6f8bc02a881342e	데님 팬츠 재입고 문의
6981fe3c37a26d3d48a5	반품 수거 지연
EOF

# 2. QA 실행
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에v2/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_manual \
  --manual-bp manual_bp.tsv
```

**자세한 가이드**: [`docs/manual-bp-selection.md`](docs/manual-bp-selection.md)

### 3. 결과 확인
```bash
# HTML 리포트 열기
open storage/qa_20260508/QA_REPORT_*.html

# 통계 확인
cat storage/qa_20260508/QA_REPORT_*.md | grep "평균 QA Score"
```

**자세한 가이드**: [`docs/sop-to-qa-workflow.md`](docs/sop-to-qa-workflow.md)

## 디렉토리 구조

```
tools/
  best_practice_extractor.py  sop-agent clustering → Best Practice 추출
  scenario_generator.py        BP → QA 시나리오 생성 (Layer 1/2/3)
  chat_driver.py              Playwright 기반 채널톡 ALF 채팅 드라이버
  scenario_runner.py          시나리오 자동 실행 (페르소나 LLM + 드라이버)
  qa_report_generator.py      BP vs ALF 비교 리포트 생성 (HTML/MD)
  result_store.py             데이터 스키마 + I/O

prompts/
  generate_scenarios_v2.md    시나리오 생성 프롬프트 (Layer 1/2/3)
  persona_archetypes.md       5개 고정 페르소나 풀
  userchat_style_bank.py      실제 고객 발화 스타일 추출

docs/
  sop-to-qa-workflow.md       전체 워크플로우 가이드
  layer-comparison.md         Layer 1/2/3 비교 분석

storage/                      (gitignored) run별 결과
```

## 셋업

Python 3.11+ 과 [uv](https://docs.astral.sh/uv/) 필요.

```bash
# 의존성 설치 + Playwright 브라우저
make setup

# 또는 수동
uv sync
uv run playwright install chromium
```

### 환경변수

`.env` 파일을 repo 루트에 생성:

```
ANTHROPIC_API_KEY=<Prism Gateway 키>
```

- LLM 호출은 기본적으로 [Prism Gateway](https://prism.ch.dev) (채널톡 사내 Anthropic 호환 프록시) 경유
- `LLM_BASE_URL` 환경변수로 override 가능
- 모델: `anthropic/claude-sonnet-4-6` (기본), `PERSONA_MODEL` / `JUDGE_MODEL`로 override

## 사용 가이드

### 사전 준비

1. **sop-agent 분석 완료** — `~/sop-agent/results/<고객사>/`에 결과물이 있어야 함
2. **ALF 테스트 채널 세팅 완료** — 지식/규칙이 세팅된 테스트 채널 URL 확보
3. **환경변수** — `.env`에 `ANTHROPIC_API_KEY` 설정

### Step 1. Claude에게 QA 요청

Claude Code에서:

```
> 벨리에 QA 돌려줘
```

Claude가 아래 정보를 물어봅니다:

```
채널 URL? → https://vqnol.channel.io
sop-agent 결과 경로? → ~/sop-agent/results/벨리에/
경쟁사 봇이 작동 중인 고객사인가요? → 네 (GL)
ALF 태스크 JSON 있으세요? → 아니요 (04_tasks/*.md 사용)
시나리오 수? → 25 (기본값)
```

이후 Phase 1-6이 자동으로 진행됩니다.

### Step 2. 파이프라인 진행 (자동)

| Phase | 소요 시간 | 사용자 개입 |
|---|---|---|
| 1. Normalize | ~1분 | 없음 |
| 2. Generate scenarios | ~2분 | 시나리오 커버리지 확인 후 승인 |
| 3. Execute (브라우저) | **30~60분** | 없음 (백그라운드 가능) |
| 4. Summarize | 즉시 | 없음 |
| 5. Score (AI Judge) | ~5분 | 없음 |
| 6. Client report | ~3분 | 없음 |

Phase 3이 가장 오래 걸립니다 (시나리오당 1~2분, ALF 응답 대기). `--headed` 모드로 실행하면 브라우저 창이 뜹니다.

### Step 3. 결과 확인

```
storage/runs/<run_id>/
├── report_slides.html   ← 브라우저에서 열기 (발표용 슬라이드)
├── report_client.md     ← 고객사 공유용 마크다운 리포트
├── report.md            ← 내부 상세 리포트 (시나리오별 pass/fail)
└── scores.json          ← 프로그래밍용 구조화 데이터
```

```bash
# 슬라이드 바로 열기
open storage/runs/<run_id>/report_slides.html
```

### 개별 도구 수동 실행

파이프라인 전체가 아니라 특정 단계만 실행할 때:

```bash
# 수동 대화 테스트 (인터랙티브 — ALF 응답 직접 확인용)
uv run python -m tools.cli https://vqnol.channel.io --headed --record

# 시나리오 자동 실행 (기존 scenarios.json 필요)
uv run python -m tools.scenario_runner \
  --run-id <run_id> \
  --channel-url https://vqnol.channel.io \
  --headed --timeout 90

# 채점만 (기존 transcripts.jsonl 필요)
uv run python -m tools.scoring_agent --run-id <run_id>

# 드라이런 (채점 대상만 확인, LLM 호출 없음)
uv run python -m tools.scoring_agent --run-id <run_id> --dry-run
```

### 재실행 (Replay)

같은 시나리오로 ALF 세팅 변경 후 재측정할 때:

```bash
# 기존 run_id로 Phase 3만 재실행 (scenarios.json 재사용)
uv run python -m tools.scenario_runner \
  --run-id <기존_run_id> \
  --channel-url https://vqnol.channel.io --headed

# 재채점
uv run python -m tools.scoring_agent --run-id <기존_run_id>
```

기존 transcripts.jsonl은 자동 보존됩니다 (덮어쓰지 않음).

### 산출물 예시

```
storage/runs/r-20260414-belier25/
├── canonical_input.yaml    # sop-agent 분석 → 정규화된 입력
├── config_snapshot.json    # 채널 설정 + 패턴 커버리지
├── scenarios.json          # 31개 시나리오 (happy/unhappy/edge/oos)
├── transcripts.jsonl       # ALF 대화 기록
├── scores.json             # AI Judge 채점 결과
├── report.md               # 내부 상세 리포트 (마크다운)
└── report_client.html      # 고객사 대상 HTML 프레젠테이션 (브라우저에서 열기)
```

**report_client.html 특징:**
- ChannelTalk 위젯 UI로 실제 테스트 대화 전문 표시
- 2열 grid 레이아웃으로 한 화면에 여러 대화 예시
- 스크롤 가능한 대화창으로 전체 턴 확인 가능
- Phase 1/Phase 2 관여율 및 주요 지표 요약
- 키보드 화살표로 슬라이드 네비게이션

## 설계 결정

| 결정 | 이유 |
|---|---|
| Playwright (not Selenium) | BrowserContext 다중화로 리소스 효율, 향후 병렬화 대비 |
| 페르소나 5개 고정 풀 | LLM의 협조성 편향 + run간 드리프트 방지 |
| coverage_mode default = channel_only | 채널톡 ALF agent node stall 이슈 회피, 측정 차원 분리 |
| 관여율 = 패턴 볼륨 가중평균 | intent weight 통째 사용 시 API 미연동 영역이 과대 계상됨 |
| timeout = resolved 간주 | ALF 시스템 지연은 품질 이슈가 아닌 인프라 이슈 |

## 개발

```bash
make pretty   # ruff format + lint
make test     # pytest
```

## 관련 repo

- **sop-agent** (`~/sop-agent/`) — 상담 데이터 분석 파이프라인. qa-agent의 입력을 생산
- **ax-workspace** — AX팀 작업 허브. qa-agent와 코드 의존성 없음, 파일 기반 인터페이스만

## 경쟁사 봇 비교 모드

`is_competitor_bot=true`로 설정하면 클라이언트 리포트에 경쟁사 봇 대비 ×N배 프레이밍이 적용됩니다.

경쟁사 봇 baseline 산출 순서:
1. `*_alf_implementation_guide.md`가 있으면 → 직접 수치 추출
2. 없으면 → sop-agent 데이터에서 추정 (response_flow의 "bot" 단계, CS_자동응답 클러스터 분석)

GL 같은 rule-based 봇은 보통 실질 해결률 10~15% (인사 + 단순 FAQ 매칭만 수행). sop-agent 상담 데이터에서 봇이 최종 응답한 건수 / 전체 건수로 추정합니다.

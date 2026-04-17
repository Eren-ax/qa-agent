# alf-qa-agent (v2: Statistical Mirroring)

ALF(채널톡 AI Agent) 응답 품질을 자동 측정하고, 고객사 대상 성과 리포트를 산출하는 도구.

**v2 핵심 개선 (2026-04-16)**:
1. **통계적 미러링**: 시나리오가 실제 90일 상담 데이터의 정확한 통계적 복제
2. **3단계 투명 지표**: scenario_coverage × alf_engagement_rate × alf_resolution_rate = actual_coverage
3. **즉시 에스컬레이션 버그 수정**: engaged=False를 관여율에서 제외하여 과대 계상 방지

## 입력

| 입력 | 필수 | 설명 |
|---|---|---|
| `sop_results_dir` | **필수** | sop-agent 분석 결과 경로 |
| `channel_url` | **필수** | ALF가 세팅된 테스트 채널 URL |
| `is_competitor_bot` | **필수** | 현재 경쟁사 봇(GL 등)이 작동 중인 고객사인지. 경쟁사 비교 리포트 여부 결정 |
| `alf_task_json` | 선택 | ALF 태스크 JSON. 없으면 `04_tasks/*.md`에서 Mermaid 파싱 |
| `target_total` | 선택 | 시나리오 수 (기본 25) |

sop-agent 결과 중 사용하는 파일:

```
<sop_results_dir>/
├── 03_sop/metadata.json                    # 필수 — intent 목록 + 건수
├── 02_extraction/faq.json                  # 필수 — FAQ Q/A (시나리오 seed)
├── 02_extraction/patterns.json             # 필수 — 패턴 + frequency + common_phrases (실제 유저 발화)
├── 02_extraction/response_strategies.json  # 권장 — escalation_triggers
├── 04_tasks/TASK*.md                       # 선택 — 태스크 정의 fallback
├── pipeline_summary.md                     # 권장 — 월간 건수 등
├── data/*.xlsx                             # 선택 — 원본 상담 데이터 (추가 유저 발화 추출용)
└── *_alf_implementation_guide.md           # 선택 — 경쟁사 수치 (없으면 데이터에서 추정)
```

**새로운 기능 (v2)**: patterns.json의 `common_phrases`와 원본 상담 xlsx를 활용하여
실제 고객 발화 스타일을 QA 페르소나에 반영합니다. AI-like한 정중한 문장이 아니라
"~요", "~인데요" 같은 실제 고객 말투를 모방합니다.

이 입력을 받아:
1. 실 상담 패턴 기반 QA 시나리오를 생성하고
2. Playwright로 ALF와 실제 대화를 돌리고
3. AI Judge로 채점한 뒤
4. 경쟁사 봇 대비 성과 리포트 + 슬라이드를 자동 생성합니다.

## 파이프라인

```
sop-agent 분석 결과 + 테스트 채널 URL
    │
    ▼
Phase 1. Normalize ─── canonical_input.yaml
    │
    ▼
Phase 2. Generate ──── scenarios.json (happy/unhappy/edge/oos)
    │                   config_snapshot.json
    ▼
Phase 3. Execute ───── transcripts.jsonl (Playwright + 페르소나 LLM)
    │
    ▼
Phase 4. Summarize ─── 실행 결과 요약
    │
    ▼
Phase 5. Score ─────── scores.json + report.md (AI Judge 채점)
                       report_client.html (고객용 HTML 프레젠테이션)
```

모든 아티팩트는 `storage/runs/<run_id>/` 아래에 적재됩니다.

## 핵심 지표

| 지표 | 정의 | 산출 방식 |
|---|---|---|
| **관여율** | 시나리오가 실 상담의 몇 %를 대표하는가 | intent별 패턴 볼륨 가중평균 (input-side) |
| **해결률** | ALF가 대응한 건 중 해결 비율 | AI Judge 판정, effective weight 가중 (output-side) |
| **커버리지** | 실 상담 대비 ALF 유효 처리 비율 | 관여율 × 해결률 |

## 디렉토리 구조

```
tools/
  chat_driver.py            Playwright 기반 채널톡 ALF 채팅 드라이버
  scenario_runner.py        시나리오 자동 실행 (페르소나 LLM + 드라이버)
  scoring_agent.py          AI Judge 채점 + 집계 + 리포트 생성
  report_html_generator.py  고객용 HTML 프레젠테이션 생성 (ChannelTalk UI 포함)
  result_store.py           v0 스키마 데이터 I/O (모든 아티팩트의 단일 진실 소스)
  cli.py                    대화형 CLI (수동 테스트용)

prompts/
  normalize_sop.md     sop-agent 결과 → canonical YAML 변환 규칙
  generate_scenarios.md 시나리오 생성 규칙 (happy/unhappy/edge/oos + 패턴 기반)
  persona_archetypes.md 5개 고정 페르소나 풀 (polite/vague/impatient/confused/adversarial)
  judge_scenario.md    AI Judge 판정 프롬프트 (criterion별 pass/fail)
  generate_client_report.md  클라이언트 리포트 + 슬라이드 생성 규칙

skills/
  qa-agent/SKILL.md    전체 파이프라인 오케스트레이션 스펙 (Phase 1-6)

storage/               (gitignored) run별 아티팩트
inputs/                (gitignored) sop-agent 결과 등 입력 파일
projects/              (gitignored) 고객사별 설정
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

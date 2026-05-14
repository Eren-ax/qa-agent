---
name: bp-qa
description: sop-agent clustering 결과에서 Best Practice를 자동 추출하여 ALF 응답 품질을 측정하고 상세 비교 리포트를 생성합니다. Human-like 시나리오 기반 QA를 실행합니다.
argument-hint: [고객사명] (optional)
allowed-tools: Bash, Read, Grep, Glob, Write, AskUserQuestion
---

# BP QA (Best Practice QA)

**목적**: sop-agent clustering 결과 → Best Practice 추출 → Human-like 시나리오 생성 → ALF 테스트 → 상세 비교 리포트

⚠️ **중요**: 이것이 **유일하게 허용된 QA 워크플로우**입니다. 다른 QA 파이프라인은 **실행 금지**합니다.

## 금지 사항

다음 스크립트/명령은 **절대 실행 금지**:

```bash
# ❌ 절대 금지 — 구버전 스크립트
python run_best_practice_test.py  # v2 구버전 (규칙 기반)
python run_3layer_test.py         # 3-layer test

# ❌ 절대 금지 — 다른 리포트 생성기
python -m tools.integrated_report_generator  # 슬라이드 형식
python -m tools.report_html_generator        # 통합 리포트
python generate_bp_report.py                 # 독립 리포트

# ❌ 절대 금지 — Coverage QA (다른 파이프라인)
# 어떤 Phase 1-6 파이프라인도 실행하지 말 것
```

**이유**: 
- 구버전은 수동 규칙 기반 (`bp.r1`, `bp.r2`), human-like 발화 아님
- Coverage QA는 다른 목적 (전체 커버리지 vs BP 품질 측정)
- 잘못된 리포트 형식 생성 (슬라이드 vs 상세 BP 비교)

---

## 실행 조건 확인

BP QA 실행 전 필수 확인:

1. **qa-agent repo 존재**: `~/qa-agent/`
   - 없으면: `git clone https://github.com/channel-io/qa-agent.git ~/qa-agent && cd ~/qa-agent && make setup`

2. **sop-agent clustering 완료**: `*_clustered.xlsx` 존재
   - 경로: `~/sop-agent/results/[고객사]/01_clustering/[고객사]_clustered.xlsx`
   - 없으면: "sop-agent Stage 1 (clustering)을 먼저 실행해야 합니다"

3. **ALF 테스트 채널**: `https://[채널ID].channel.io`
   - ALF 세팅 완료 (지식/규칙/태스크)
   - 채널 접속 가능 확인

4. **환경변수**: `~/qa-agent/.env`에 `ANTHROPIC_API_KEY` 설정
   - 없으면: AX팀 리드에게 Prism Gateway 키 요청

---

## 워크플로우

주어진 입력: $ARGUMENTS

### Step 1: 정보 수집

사용자에게 다음 정보를 물어봄 (AskUserQuestion 사용):

```
[고객사] BP QA를 실행합니다.

필요한 정보:
1. 고객사명? (예: 벨리에, 차란, 설탭매니저)
2. clustering Excel 경로? 
   기본값: ~/sop-agent/results/[고객사]/01_clustering/[고객사]_clustered.xlsx
3. ALF 테스트 채널 URL? (예: https://vqnol.channel.io)
4. 추출할 BP 케이스 수? (기본: 100, 빠른 테스트: 25)
```

**$ARGUMENTS에 고객사명이 포함된 경우**: 해당 고객사로 기본값 채움

**파일 경로 검증**:
```bash
ls -lh ~/sop-agent/results/[고객사]/01_clustering/*_clustered.xlsx
```

없으면 사용자에게 올바른 경로 요청.

---

### Step 2: run_bp_qa.py 실행

**중요**: 반드시 `run_bp_qa.py`만 사용 (다른 스크립트 사용 금지)

```bash
cd ~/qa-agent

uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/[고객사]/01_clustering/[고객사]_clustered.xlsx \
  --channel-url https://[채널ID].channel.io \
  --output-dir storage/qa_[고객사]_$(date +%Y%m%d) \
  --target-total [케이스수] \
  --timeout 120.0
```

**플래그 설명**:
- `--clustered-excel`: sop-agent clustering 결과 (필수)
- `--channel-url`: ALF 테스트 채널 (필수)
- `--output-dir`: 결과 저장 경로
- `--target-total`: 추출할 BP 케이스 수 (기본 100)
- `--timeout`: 시나리오당 타임아웃 (초, 기본 120)
- `--manual-bp`: 수동 BP 파일 (선택, TSV/CSV/Excel)
- `--headed`: 브라우저 창 표시 (디버깅용)

**실행 방식**: `run_in_background: true` (백그라운드 실행)
- 예상 소요 시간: 100 케이스 기준 50~100분
- 사용자에게 "백그라운드에서 실행 중입니다. 완료되면 알려드리겠습니다" 안내

---

### Step 3: 실행 단계 (자동)

`run_bp_qa.py`가 자동으로 4단계 실행:

```
Step 1: Extract Best Practice
  └─ clustering → BP 자동 추출 (클러스터 비례 샘플링, 품질 우선순위)

Step 2: Generate Scenarios
  └─ BP → QA 시나리오 생성 (Layer 1/2/3, 페르소나 LLM)

Step 3: Execute QA Tests
  └─ ALF 테스트 실행 (Playwright headless, transcripts.jsonl 저장)

Step 4: Generate Reports
  └─ BP vs ALF 비교 리포트 (HTML/MD, QA Score 10점 만점)
```

---

### Step 4: 진행 상황 모니터링

백그라운드 실행 중:
- 완료 알림 대기 (자동)
- 사용자가 "진행 상황" 요청 시:

```bash
tail -50 [output-file] | grep -E '\[[0-9]+/[0-9]+\]' | tail -1
```

`[N/M]` 형태로 진행률 출력 (예: `[15/94]` → 16%)

---

### Step 5: 결과 확인

완료 후 출력 디렉토리 확인:

```bash
cd storage/qa_[고객사]_[날짜]
ls -lh

# 생성 파일:
# - best_practice_selection.md    # BP 선정 근거
# - transcripts.jsonl              # 전체 대화 기록
# - QA_REPORT_[고객사].html        # ★ 상세 HTML 리포트
# - QA_REPORT_[고객사].md          # 마크다운 리포트
```

**리포트 검증** (올바른 형식인지 확인):

```bash
# 올바른 리포트 (BP vs ALF 비교)
grep -c "Best Practice 유저챗" QA_REPORT_*.html
# → 케이스 수와 동일해야 함 (예: 100)

# 잘못된 리포트 (슬라이드 형식)
grep -c "slide" QA_REPORT_*.html
# → 0이어야 함
```

**잘못된 리포트 발견 시**:
- 사용자에게 경고: "슬라이드 리포트가 생성됐습니다. 잘못된 스크립트를 실행한 것 같습니다."
- 올바른 명령 재실행 안내

---

### Step 6: 리포트 요약

사용자에게 결과 요약 제공:

```
✅ BP QA 완료

📊 결과:
- 총 [N]개 케이스 테스트
- 평균 QA Score: [X.X]/10
- 상세 리포트: [경로]/QA_REPORT_[고객사].html

다음 단계:
1. HTML 리포트 검토 (케이스별 BP vs ALF 비교)
2. 낮은 점수 케이스 원인 분석
3. ALF 개선 (규칙/지식/태스크)
4. 재실행으로 개선 효과 측정
```

**HTML 리포트 열기**:
```bash
open storage/qa_[고객사]_[날짜]/QA_REPORT_[고객사].html
```

---

## 리포트 구조

**QA_REPORT_[고객사].html**:
- ✅ 전체 요약 (성공/부분성공/타임아웃/오류)
- ✅ 케이스별 BP vs ALF 1:1 비교
- ✅ Best Practice 유저챗 원본 (실제 고객 발화)
- ✅ 실제 대화 내역 (채팅 말풍선 UI)
- ✅ QA Score (정확성 5 + 완결성 3 + 톤&매너 2)
- ✅ 메트릭 (턴 수, 응대 시간, 평균 응답 시간)
- ✅ 분류 (🟢 RAG / 🟡 Text Task / 🔴 Function Task)

**예시**:
```
📊 전체 요약
🟢 성공: 96건 (96.0%) - 평균 9.4점
🟡 부분성공: 2건 (2.0%) - 평균 8.5점
🟠 타임아웃: 1건 (1.0%) - 평균 5.0점
🔴 오류: 1건 (1.0%) - 평균 0.0점

[케이스 1. 데님 팬츠 재입고 문의]
BP 유저챗: https://desk.channel.io/...
카테고리: 제품_문의
분류: 🟢 RAG

📋 Best Practice 유저챗
👤 고객: 데님 팬츠 재입고 언제 되나요?
🎯 BP 봇: 4월 20일 재입고 예정입니다.

💬 실제 대화 내역
👤 고객: 데님 팬츠 재입고 언제 되나요?
🤖 ALF: 4월 20일 재입고 예정입니다. 알림 신청하시겠어요?

📊 QA 채점
✅ 정확성 5/5: BP와 동일하게 정보 제공
✅ 완결성 3/3: 필요한 정보 모두 포함
✅ 톤&매너 2/2: 친근하고 자연스러운 톤

QA Score: 10/10
평가: 🟢 우수: BP와 거의 동일한 수준의 응대
```

---

## 수동 BP 지정 (고급)

특정 UserChat만 테스트하려면:

```bash
# 1. manual_bp.tsv 생성
cat > manual_bp.tsv <<EOF
user_chat_id	intent
6997a6f8bc02a881342e	데님 팬츠 재입고 문의
6981fe3c37a26d3d48a5	반품 수거 지연
EOF

# 2. 실행
uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/[고객사]/01_clustering/[고객사]_clustered.xlsx \
  --channel-url https://[채널ID].channel.io \
  --output-dir storage/qa_manual \
  --manual-bp manual_bp.tsv
```

**자세한 가이드**: `~/qa-agent/docs/manual-bp-selection.md`

---

## 트러블슈팅

### 1. "No such file: *_clustered.xlsx"
→ sop-agent Stage 1 clustering 먼저 실행

### 2. "Channel.io widget not found"
→ 채널 URL 확인, ALF 세팅 완료 여부 확인

### 3. "Timeout after 120s"
→ `--timeout 180.0`으로 증가 또는 ALF 응답 속도 확인

### 4. 슬라이드 리포트가 생성됨
→ 잘못된 스크립트 사용. `run_bp_qa.py` 확인

### 5. 시나리오가 human-like하지 않음
→ `scenarios.json`에서 `source: "sop-agent"` 확인
→ `"best-practice"` 또는 다른 값이면 잘못된 파이프라인 실행

---

## 참고 문서

- **README.md** — qa-agent 전체 개요
- **docs/sop-to-qa-workflow.md** — 상세 워크플로우
- **docs/manual-bp-selection.md** — 수동 BP 선정 가이드
- **CHANGELOG_v3.md** — v3 변경사항 및 마이그레이션
- **docs/bp-extraction-criteria-proposal.md** — BP 추출 기준 정의
- **docs/bp-extraction-criteria-implementation-plan.md** — BP 추출 구현 계획

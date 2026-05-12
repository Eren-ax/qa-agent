# qa-agent 빠른 시작 가이드

처음 사용자를 위한 Step-by-Step 가이드입니다. 레포 클론부터 첫 BP QA 실행까지 모든 과정을 다룹니다.

⚠️ **중요**: 이 가이드는 **BP QA (Best Practice QA)** 전용입니다. 다른 QA 파이프라인은 사용하지 마세요.

---

## 준비물

- **Claude Code** (Desktop App / VS Code Extension / Web)
- **Anthropic API 키** (AX팀 리드에게 요청)
- **sop-agent clustering 결과** (`~/sop-agent/results/<고객사>/01_clustering/*_clustered.xlsx`)
- **ALF 테스트 채널 URL** (`https://<channelId>.channel.io`)

---

## STEP 1: 레포 클론

### Claude Code에서 (권장)

Claude Code를 열고:

```
~/qa-agent 경로에 https://github.com/channel-io/qa-agent 클론해줘
```

Claude가 자동으로:
```bash
cd ~
git clone https://github.com/channel-io/qa-agent.git
cd qa-agent
```

### 터미널에서 (수동)

```bash
cd ~
git clone https://github.com/channel-io/qa-agent.git
cd qa-agent
```

**확인:**
```bash
ls -la
# tools/, prompts/, run_bp_qa.py, README.md 등이 보여야 함
```

---

## STEP 2: 환경 셋업

### 2-1. Python 의존성 설치

Claude Code에서:
```
qa-agent 셋업해줘
```

또는 터미널에서:
```bash
cd ~/qa-agent
make setup
```

이 명령은 다음을 자동 실행합니다:
- `uv` 설치 (없는 경우)
- `uv sync` — Python 패키지 설치
- `uv run playwright install chromium` — 브라우저 설치

**예상 소요 시간:** 3-5분

**오류 발생 시:**

```bash
# uv가 없다는 오류
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # 또는 ~/.zshrc

# playwright 설치 실패
cd ~/qa-agent
uv run playwright install chromium --with-deps
```

### 2-2. 환경변수 설정

**중요:** API 키가 없으면 아무것도 작동하지 않습니다.

Claude Code에서:
```
~/qa-agent/.env 파일 만들어줘. ANTHROPIC_API_KEY는 [발급받은 키]로 설정해줘
```

또는 수동으로 파일 생성:

```bash
# ~/qa-agent/.env 파일 생성
cat > ~/qa-agent/.env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
EOF
```

**확인:**
```bash
cat ~/qa-agent/.env
# ANTHROPIC_API_KEY=sk-ant-... 이 보여야 함
```

**API 키 발급:**
- AX팀 리드에게 Prism Gateway 키 요청
- 또는 Anthropic 계정에서 직접 발급

---

## STEP 3: 사전 준비 확인

QA 실행 전 필수 확인 사항입니다.

### 3-1. sop-agent clustering 결과 확인

```bash
ls ~/sop-agent/results/<고객사>/01_clustering/
```

**필수 파일:**
- `<고객사>_clustered.xlsx` — clustering 결과

예시:
```bash
~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx
~/sop-agent/results/차란/01_clustering/차란_clustered.xlsx
```

**없는 경우:**
- sop-agent Stage 1 (clustering)을 먼저 실행해야 합니다
- Claude Code에서: "sop-agent Stage 1 실행해줘"

### 3-2. ALF 테스트 채널 준비

1. **테스트 채널 생성** (프로덕션과 별도)
2. **ALF 세팅 적용**:
   - 지식 문서 업로드
   - 규칙 작성
   - (선택) 태스크 세팅
3. **채널 URL 확인**: `https://<channelId>.channel.io`

**확인 방법:**
- 브라우저에서 채널 URL 접속
- ALF 위젯이 뜨는지 확인
- 간단한 메시지 보내서 ALF 응답 확인

---

## STEP 4: 첫 BP QA 실행

### 4-1. Claude Code에서 실행 (권장)

```
BP QA 돌려줘
```

또는

```
벨리에 BP QA 실행해줘
```

### 4-2. Claude가 묻는 질문들

**Q1. 고객사명?**
```
벨리에
```

**Q2. clustering Excel 경로?**
```
~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx
```

또는 (절대 경로)
```
/Users/eren/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx
```

**Q3. ALF 테스트 채널 URL?**
```
https://vqnol.channel.io
```

**Q4. 추출할 BP 케이스 수?**
```
100
```
- 기본값: 100
- 빠른 테스트: 25
- 상세 분석: 100-200

### 4-3. 실행 진행 과정

```
======================================================================
Step 1: Extract Best Practice
======================================================================
Mode: Automatic extraction from clustering
Clustered Excel: .../벨리에_clustered.xlsx

✅ Extracted 100 Best Practice cases

Distribution by category:
  제품_문의: 24
  주문_취소_반품: 18
  교환_배송: 15
  재입고_문의: 12
  ...

======================================================================
Step 2: Generate Scenarios
======================================================================
✅ Generated 100 QA scenarios

Layer distribution:
  Layer 1 (LLM generation): 60
  Layer 2 (Direct transplant): 30
  Layer 3 (Layer 1 + validation): 10

======================================================================
Step 3: Execute QA Tests
======================================================================
⏱️  예상 소요: 50~100분 (100 케이스 × 1~2분)

[1/100] bp_699031cd_c11_layer1 (polite_clear)
  Turn 1: 달스톤 슬링백 받았는데 버클이 다른 방향이에요
  → ALF: 불량품 교환 도와드릴게요...
  Status: completed (3 turns)

[2/100] bp_695db207_c24_layer2 (vague)
  Turn 1: AS 접수한지 2주 됐는데 어떻게 됐어요?
  → ALF: 확인해드리겠습니다...
  Status: completed (2 turns)

...

✅ 100/100 scenarios executed
   Success: 96
   Partial: 2
   Timeout: 1
   Error: 1

======================================================================
Step 4: Generate Reports
======================================================================
✅ Generated QA reports

Files created:
  - QA_REPORT_벨리에.html  ← 상세 BP vs ALF 비교
  - QA_REPORT_벨리에.md    ← 마크다운 버전
  - transcripts.jsonl      ← 전체 대화 기록
  - best_practice_selection.md ← BP 선정 근거

Output directory: storage/qa_벨리에_20260512/
```

**전체 소요 시간:**
- Step 1-2: ~5분
- Step 3: **50~100분** (케이스 수에 비례)
- Step 4: ~2분

### 4-4. 터미널에서 직접 실행 (고급)

```bash
cd ~/qa-agent

uv run python run_bp_qa.py \
  --clustered-excel ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_벨리에_$(date +%Y%m%d) \
  --target-total 100 \
  --timeout 120.0
```

**주요 옵션:**
- `--target-total`: 추출할 BP 케이스 수 (기본 100)
- `--timeout`: 시나리오당 타임아웃 (초, 기본 120)
- `--headed`: 브라우저 창 표시 (디버깅용)
- `--manual-bp`: 수동 BP 파일 (TSV/CSV/Excel)

---

## STEP 5: 결과 확인

### 5-1. 상세 HTML 리포트 열기

```bash
# 출력 디렉토리로 이동
cd storage/qa_벨리에_20260512

# HTML 리포트 열기
open QA_REPORT_벨리에.html
```

### 5-2. 리포트 구조

**QA_REPORT_벨리에.html** (상세 비교 리포트):

```
📊 전체 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
결과         건수    비율    평균 QA Score
🟢 성공      96건    96.0%   9.4점
🟡 부분      2건     2.0%    8.5점
🟠 타임아웃  1건     1.0%    5.0점
🔴 오류      1건     1.0%    0.0점

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🟢 성공 (96건)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 데님 팬츠 재입고 문의
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Best Practice User Chat: https://desk.channel.io/...
카테고리: 제품_문의
분류: 🟢 RAG

📋 Best Practice 유저챗
━━━━━━━━━━━━━━━━━━━━━━
👤 고객: 데님 팬츠 04(30) 사이즈 재입고 언제 되나요?

🎯 BP 봇: 4월 20일 재입고 예정입니다. 
         알림 신청하시면 재입고 시 바로 안내드립니다.

💬 실제 대화 내역
━━━━━━━━━━━━━━━━━━━━━━
[고객] 데님 팬츠 30 사이즈 언제 다시 들어오나요?

[ALF] 브로큰 스트레이트 데님 팬츠 04(30) 사이즈는 
      4월 20일 재입고 예정입니다.
      
      재입고 알림 신청하시면 입고 즉시 
      알림톡으로 안내해드릴게요!

[고객] 알림 어떻게 신청하나요?

[ALF] 상품 페이지에서 '재입고 알림' 버튼을 
      눌러주시면 됩니다.
      
      [재입고 알림 신청 방법]
      1. 상품 상세 페이지 접속
      2. '재입고 알림' 버튼 클릭
      3. 입고 시 자동 알림

📈 메트릭
━━━━━━━━━━━━━━━━━━━━━━
턴 수: 2턴
응대 시간: 35.0초
평균 응답 시간: 17.5초

📊 QA 채점
━━━━━━━━━━━━━━━━━━━━━━
✅ 정확성 5/5: BP와 동일하게 정보 제공
✅ 완결성 3/3: 필요한 정보 모두 포함
✅ 톤&매너 2/2: 친근하고 자연스러운 톤

QA Score: 10/10
평가: 🟢 우수 - BP와 거의 동일한 수준의 응대

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

2. 반품 수거 지연 문의
...
```

### 5-3. 리포트 특징

- ✅ **케이스별 BP vs ALF 1:1 비교**
- ✅ **Best Practice 원본** (실제 고객 발화)
- ✅ **실제 대화 내역** (채팅 말풍선 UI)
- ✅ **QA Score 10점 만점** (정확성 5 + 완결성 3 + 톤&매너 2)
- ✅ **메트릭** (턴 수, 응대 시간, 평균 응답 시간)
- ✅ **분류** (🟢 RAG / 🟡 Text Task / 🔴 Function Task)

---

## ❌ 주의사항

### 절대 사용 금지

다음 명령/스크립트는 **절대 실행하지 마세요**:

```bash
# ❌ 금지 — 구버전 스크립트
python run_best_practice_test.py  # v2 구버전
python run_3layer_test.py         # 3-layer test

# ❌ 금지 — 다른 파이프라인
python -m tools.integrated_report_generator
python generate_bp_report.py
# 어떤 Phase 1-6 파이프라인도 실행하지 말 것
```

### 올바른 리포트 확인 방법

생성된 HTML이 올바른 BP QA 리포트인지 확인:

```bash
# 올바른 리포트 (BP vs ALF 비교)
grep -c "Best Practice 유저챗" QA_REPORT_*.html
# → 100 (케이스 수와 동일해야 함)

# 잘못된 리포트 (슬라이드 형식)
grep -c "slide" QA_REPORT_*.html
# → 0이어야 함
```

**잘못된 리포트 예시:**
- `report_slides.html` — 슬라이드 형식 (통합 파이프라인 결과)
- BP vs ALF 비교 없음
- 케이스별 상세 정보 없음

**올바른 리포트 예시:**
- `QA_REPORT_<고객사>.html` — 상세 비교 형식
- 케이스별 BP 원본 + 실제 대화 + QA Score
- 전체 요약 + 케이스 리스트

---

## 트러블슈팅

### 1. "No such file: *_clustered.xlsx"
→ sop-agent Stage 1 clustering 먼저 실행

```bash
cd ~/sop-agent
# clustering 실행
```

### 2. "Channel.io widget not found"
→ 채널 URL 확인, ALF 세팅 완료 여부 확인

### 3. "Timeout after 120s"
→ `--timeout 180.0`으로 증가

```bash
uv run python run_bp_qa.py \
  --clustered-excel ... \
  --channel-url ... \
  --timeout 180.0
```

### 4. 슬라이드 리포트가 생성됨
→ 잘못된 스크립트 사용. `run_bp_qa.py` 확인
→ QUICKSTART.md 다시 확인

### 5. git pull 실패
→ local changes 충돌

```bash
cd ~/qa-agent
git stash
git pull origin main
git stash pop
```

---

## 다음 단계

BP QA 리포트 생성 후:

1. **HTML 리포트 검토** — 케이스별 BP vs ALF 비교
2. **QA Score 분석** — 낮은 점수 케이스 원인 파악
3. **ALF 개선**:
   - 규칙/지식 보강
   - Task JSON 수정
   - 프롬프트 튜닝
4. **재실행** — 개선 후 동일 시나리오로 재측정

---

## 참고 문서

- **README.md** — qa-agent 전체 개요
- **docs/sop-to-qa-workflow.md** — 상세 워크플로우
- **docs/manual-bp-selection.md** — 수동 BP 선정 가이드
- **CHANGELOG_v3.md** — v3 변경사항 및 마이그레이션

---

**문의:** AX팀 채널톡 또는 GitHub Issues

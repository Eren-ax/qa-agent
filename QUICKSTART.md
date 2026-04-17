# qa-agent 빠른 시작 가이드

처음 사용자를 위한 Step-by-Step 가이드입니다. 레포 클론부터 첫 QA 실행까지 모든 과정을 다룹니다.

---

## 준비물

- **Claude Code** (Desktop App / VS Code Extension / Web)
- **Anthropic API 키** (AX팀 리드에게 요청)
- **sop-agent 분석 결과** (`~/sop-agent/results/<고객사>/`)
- **ALF 테스트 채널 URL** (`https://<channelId>.channel.io`)

---

## STEP 1: 레포 클론

### Claude Code에서 (권장)

Claude Code를 열고:

```
~/qa-agent 경로에 https://github.com/Eren-ax/qa-agent 클론해줘
```

Claude가 자동으로:
```bash
cd ~
git clone https://github.com/Eren-ax/qa-agent.git
cd qa-agent
```

### 터미널에서 (수동)

```bash
cd ~
git clone https://github.com/Eren-ax/qa-agent.git
cd qa-agent
```

**확인:**
```bash
ls -la
# tools/, prompts/, skills/, README.md 등이 보여야 함
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

### 3-1. sop-agent 결과 확인

```bash
ls ~/sop-agent/results/<고객사>/
```

**필수 파일:**
- `03_sop/metadata.json`
- `02_extraction/faq.json`
- `02_extraction/patterns.json`

**권장 파일:**
- `02_extraction/response_strategies.json`
- `05_sales_report/analysis/automation_analysis.md`
- `04_tasks_json/TASK*.json` 또는 `04_tasks/TASK*.md`

**없는 경우:**
- sop-agent를 먼저 실행해야 합니다
- sop-agent 가이드 참조

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

## STEP 4: 첫 QA 실행

### 4-1. Claude Code에서 실행 (권장)

```
<고객사> QA 돌려줘
```

예시:
```
벨리에 QA 돌려줘
```

### 4-2. Claude가 묻는 질문들

**Q1. 채널 URL?**
```
https://vqnol.channel.io
```

**Q2. sop-agent 결과 경로?**
```
~/sop-agent/results/벨리에/
```
또는
```
/Users/eren/sop-agent/results/벨리에/
```

**Q3. 경쟁사 봇이 작동 중인 고객사인가요?**
- **Yes** → GL 등 기존 챗봇이 있는 경우
- **No** → 신규 도입 케이스

**Q4. ALF 태스크 JSON 있으세요?**
- 보통 **No** → `04_tasks/*.md` 자동 파싱
- JSON 파일 있으면 경로 입력

**Q5. 시나리오 수?**
- **25** (기본값, 권장)
- 30~50: 더 높은 커버리지 (시간 더 소요)

### 4-3. 실행 진행 과정

```
[Phase 1] Normalizing sop-agent results...
          ✓ Loaded metadata.json (11 intents)
          ✓ Loaded faq.json (45 Q/A pairs)
          ✓ Loaded patterns.json (127 patterns)
          ✓ Generated canonical_input.yaml

[Phase 2] Generating scenarios...
          ✓ Generated 25 scenarios covering 72.3% of traffic
          
          Continue? (yes/no)
```

**여기서 확인:**
- 커버리지 70% 이상 → `yes`
- 커버리지 60% 미만 → 시나리오 수 늘리기

```
[Phase 3] Executing scenarios with Playwright...
          [1/25] product_001 (polite_clear) → completed (3 turns)
          [2/25] product_002 (vague) → completed (4 turns)
          ...
          ⏱️  예상 소요: 30~60분
```

**Phase 3가 가장 오래 걸립니다!**
- 시나리오당 1~2분 소요
- 브라우저가 백그라운드에서 실행됨
- 진행 상황이 실시간으로 출력됨

```
[Phase 4] Summarizing execution results...
          ✓ 25 scenarios executed
          ✓ 23 completed, 2 escalated

[Phase 5] Scoring with AI Judge...
          [1/25] product_001 → pass (3/3 criteria)
          [2/25] product_002 → pass (2/3 criteria)
          ...
          ⏱️  예상 소요: ~5분

[Phase 6] Generating client report...
          ✓ report.md generated
          ✓ report_client.html generated
          
✅ QA Complete!
   Run ID: belier-20260417-qa
   Results: storage/runs/belier-20260417-qa/
```

**전체 소요 시간:**
- Phase 1-2: ~3분
- Phase 3: **30~60분**
- Phase 4-6: ~8분
- **총 40~70분**

---

## STEP 5: 결과 확인

### 5-1. HTML 리포트 열기

Claude Code에서:
```
<고객사> QA 리포트 열어줘
```

또는 터미널에서:
```bash
open ~/qa-agent/storage/runs/belier-20260417-qa/report_client.html
```

### 5-2. 리포트 내용

**Slide 1: 커버**
- 고객사명
- Run ID

**Slide 2: 전체 결과**
- Phase 1 관여율: 65-70% (지금 즉시)
- Phase 2 관여율: 80-85% (워크플로우 테스트 후)
- 테스트 시나리오 수

**Slide 3+: 대화 예시**
- ChannelTalk 위젯 UI
- 실제 테스트 대화 전문
- 스크롤 가능

**마지막 Slide: 결론**
- 권장 진행 방식

**네비게이션:**
- 키보드 화살표 (← →)
- 화면 좌우 버튼
- 하단 점으로 위치 확인

### 5-3. 상세 리포트 (선택)

내부 분석용 상세 리포트:

```bash
cat ~/qa-agent/storage/runs/belier-20260417-qa/report.md
```

시나리오별 pass/fail 상세 내역 포함

---

## STEP 6: 재실행 (ALF 세팅 변경 후)

### 6-1. 같은 시나리오로 재측정

ALF 규칙/지식을 수정한 후:

```
<고객사> 같은 시나리오로 재실행해줘
```

또는

```bash
cd ~/qa-agent
uv run python -m tools.scenario_runner \
  --run-id belier-20260417-qa \
  --channel-url https://vqnol.channel.io
  
uv run python -m tools.scoring_agent \
  --run-id belier-20260417-qa
```

**효과:**
- Phase 1-2 건너뜀 (시나리오 재사용)
- Phase 3-6만 실행
- 소요 시간 단축 (~40분)

### 6-2. 새 시나리오로 재측정

```
<고객사> QA 돌려줘
```

완전히 새로 시작 (권장: ALF 대규모 변경 시)

---

## 트러블슈팅

### 문제 1: "ANTHROPIC_API_KEY not set" 오류

**증상:**
```
[runner] ANTHROPIC_API_KEY not set in env
```

**해결:**
```bash
# .env 파일 확인
cat ~/qa-agent/.env

# 없으면 생성
echo "ANTHROPIC_API_KEY=sk-ant-xxxxx" > ~/qa-agent/.env
```

### 문제 2: Playwright 브라우저 오류

**증상:**
```
playwright._impl._errors.Error: Executable doesn't exist
```

**해결:**
```bash
cd ~/qa-agent
uv run playwright install chromium
```

### 문제 3: Phase 3 실행이 멈춤

**증상:**
```
[3/25] product_003 (vague)
```
30초 이상 진행 없음

**원인:**
- ALF 응답 timeout (60초)
- 채널 로딩 이슈

**해결:**
1. Ctrl+C로 중단
2. 재실행:
   ```
   같은 run_id로 Phase 3 재실행해줘
   ```

### 문제 4: 커버리지가 너무 낮음 (<60%)

**증상:**
```
[Phase 2] 25 scenarios covering 48.3% of traffic
Continue? (yes/no)
```

**해결:**
- `no` 입력
- 시나리오 수 늘리기:
  ```
  시나리오 35개로 다시 생성해줘
  ```

### 문제 5: sop-agent 필수 파일 없음

**증상:**
```
[Phase 1] metadata.json not found
```

**해결:**
- sop-agent 먼저 실행
- 또는 경로 확인:
  ```bash
  ls ~/sop-agent/results/<고객사>/03_sop/
  ```

### 문제 6: ALF가 응답하지 않음

**증상:**
```
[1/25] product_001 → timeout (no reply)
```

**원인:**
- 채널 URL 오류
- ALF 미세팅
- 채널 비공개 상태

**해결:**
1. 브라우저에서 직접 접속
2. ALF 위젯 뜨는지 확인
3. 직접 메시지 보내서 응답 확인

---

## 고급 사용법

### 특정 시나리오만 실행

```bash
cd ~/qa-agent
uv run python -m tools.scenario_runner \
  --run-id belier-20260417-qa \
  --channel-url https://vqnol.channel.io \
  --scenario-id product_001
```

### 브라우저 보면서 실행 (디버깅)

```bash
uv run python -m tools.scenario_runner \
  --run-id belier-20260417-qa \
  --channel-url https://vqnol.channel.io \
  --headed
```

### 채점만 재실행

```bash
uv run python -m tools.scoring_agent \
  --run-id belier-20260417-qa
```

### 드라이런 (채점 대상만 확인)

```bash
uv run python -m tools.scoring_agent \
  --run-id belier-20260417-qa \
  --dry-run
```

---

## 체크리스트

### 시작 전 체크리스트

- [ ] Claude Code 설치됨
- [ ] qa-agent 레포 클론 완료
- [ ] `make setup` 실행 완료
- [ ] `.env` 파일에 API 키 설정
- [ ] sop-agent 분석 결과 존재 (`~/sop-agent/results/<고객사>/`)
- [ ] ALF 테스트 채널 준비 완료
- [ ] 테스트 채널 URL 확인

### 실행 중 체크리스트

- [ ] Phase 2: 시나리오 커버리지 70% 이상 확인
- [ ] Phase 3: 진행 상황 모니터링 (30~60분)
- [ ] Phase 5: 채점 완료, 오류 없음

### 완료 후 체크리스트

- [ ] `report_client.html` 브라우저에서 열림
- [ ] Phase 1/2 관여율 수치 확인
- [ ] 대화 예시 슬라이드 확인
- [ ] 고객사 담당자에게 리포트 공유

---

## 다음 단계

### 여러 고객사 관리

각 고객사별로 독립적인 run_id가 생성됩니다:

```bash
storage/runs/
├── belier-20260417-qa/
├── yusim-20260418-qa/
└── bodyfried-20260419-qa/
```

### 정기 QA

주기적으로 QA를 실행하여 ALF 품질 모니터링:

```
월 1회: 전체 시나리오 재생성 (Phase 1-6)
주 1회: 같은 시나리오로 재측정 (Phase 3-6)
```

### 팀 공유

리포트 공유 방법:

1. **HTML 슬라이드** (고객사용):
   ```
   report_client.html → 브라우저로 열기 → PDF 저장 또는 공유
   ```

2. **상세 리포트** (내부용):
   ```
   report.md → Notion에 붙여넣기
   ```

3. **Raw 데이터** (분석용):
   ```
   scores.json → 데이터 분석 도구로 로드
   ```

---

## 자주 묻는 질문 (FAQ)

### Q1. Phase 3가 왜 이렇게 오래 걸리나요?

A: Playwright가 실제 브라우저를 띄워서 ALF와 대화하기 때문입니다.
- 시나리오당 1~2분 (ALF 응답 대기 시간 포함)
- 25개 시나리오 = 25~50분
- 백그라운드 실행 가능 (다른 작업 가능)

### Q2. 여러 고객사 QA를 동시에 실행할 수 있나요?

A: 불가능합니다. Playwright는 한 번에 한 세션만 실행 가능합니다.
- 권장: 순차 실행
- 또는 별도 머신에서 실행

### Q3. API 키 없이 사용할 수 있나요?

A: 불가능합니다. 페르소나 생성과 채점에 LLM이 필수입니다.
- ANTHROPIC_API_KEY 또는 UPSTAGE_API_KEY 필요
- AX팀 리드에게 요청

### Q4. sop-agent 없이 사용할 수 있나요?

A: 불가능합니다. sop-agent 분석 결과가 qa-agent의 입력입니다.
- 필수: metadata.json, faq.json, patterns.json
- sop-agent를 먼저 실행하세요

### Q5. 결과를 다시 보고 싶어요

```
storage/runs/ 아래 run_id 리스트 보여줘
```
또는
```bash
ls ~/qa-agent/storage/runs/
open ~/qa-agent/storage/runs/<run_id>/report_client.html
```

---

## 지원

- **문서**: `~/qa-agent/README.md`, `~/qa-agent/docs/`
- **Slack**: AX팀 채널
- **GitHub Issues**: https://github.com/Eren-ax/qa-agent/issues

---

## 요약: 한눈에 보는 전체 과정

```
1. 레포 클론
   └─> git clone https://github.com/Eren-ax/qa-agent.git

2. 환경 셋업
   ├─> make setup (Python + Playwright)
   └─> .env 파일 생성 (API 키)

3. 사전 준비
   ├─> sop-agent 결과 확인
   └─> ALF 테스트 채널 준비

4. QA 실행 (Claude Code)
   └─> "<고객사> QA 돌려줘"
       ├─> Phase 1: Normalize (~1분)
       ├─> Phase 2: Generate (~2분)
       ├─> Phase 3: Execute (~40분) ⏱️
       ├─> Phase 4: Summarize (즉시)
       ├─> Phase 5: Score (~5분)
       └─> Phase 6: Report (~3분)

5. 결과 확인
   └─> report_client.html 열기

6. (필요시) 재실행
   └─> 같은 시나리오 or 새 시나리오
```

**첫 실행 총 소요 시간: ~50분**

시작하세요! 🚀

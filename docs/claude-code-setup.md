# Claude Code로 qa-agent 시작하기

Claude Code에서 qa-agent를 처음 설정하고 실행하는 단계별 가이드입니다.

## Step 1: 레포 Clone

### Claude에게 요청

```
~/qa-agent 경로에 https://github.com/Eren-ax/qa-agent 레포지토리를 클론해줘
```

**Claude가 자동으로 수행:**
```bash
cd ~
git clone https://github.com/Eren-ax/qa-agent.git
cd qa-agent
```

### 확인

```
qa-agent 디렉토리 구조 보여줘
```

다음과 같은 구조가 보여야 합니다:
```
qa-agent/
├── tools/           # 핵심 실행 스크립트
├── prompts/         # LLM 프롬프트
├── skills/          # Claude Code 스킬
├── storage/         # QA 결과 저장 (자동 생성)
├── .env             # 환경변수 (생성 필요)
├── pyproject.toml   # Python 의존성
└── README.md
```

---

## Step 2: 초기 셋업

### Claude에게 요청

```
qa-agent 셋업해줘
```

**Claude가 자동으로 수행:**
```bash
cd ~/qa-agent
make setup
```

이 명령은 다음을 실행합니다:
1. `uv sync` — Python 의존성 설치 (uv가 없으면 자동 설치)
2. `uv run playwright install chromium` — Playwright 브라우저 설치

### 수동 실행이 필요한 경우

만약 `make setup`이 실패하면:

```bash
# uv 설치 (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 의존성 설치
cd ~/qa-agent
uv sync

# Playwright 설치
uv run playwright install chromium
```

---

## Step 3: 환경변수 설정

### Claude에게 요청

```
~/qa-agent/.env 파일을 만들어줘. ANTHROPIC_API_KEY는 [발급받은 키]로 설정해줘
```

**또는 수동으로:**

`~/qa-agent/.env` 파일 생성:
```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx  # Prism Gateway API 키
```

### API 키 발급 방법

1. AX팀 리드에게 Prism Gateway 키 요청
2. 또는 Anthropic API 키 사용 (직접 계정 필요)

### 추가 환경변수 (선택)

```bash
# LLM 설정 커스터마이징 (기본값 사용 권장)
LLM_BASE_URL=https://prism.ch.dev              # Prism Gateway (기본값)
PERSONA_MODEL=anthropic/claude-sonnet-4-6      # 페르소나 생성 모델 (기본값)
JUDGE_MODEL=anthropic/claude-sonnet-4-6        # 채점 모델 (기본값)
```

---

## Step 4: 첫 QA 실행

### 사전 준비 확인

실행 전 다음이 준비되어 있어야 합니다:

1. **sop-agent 분석 완료**
   ```
   ~/sop-agent/results/<고객사>/ 디렉토리가 존재하는지 확인해줘
   ```

2. **테스트 채널 URL**
   - 형식: `https://<channelId>.channel.io`
   - ALF가 세팅된 채널이어야 함

### Claude에게 요청

```
<고객사> QA 돌려줘
```

**Claude가 물어보는 질문:**

1. **채널 URL?**
   ```
   https://vqnol.channel.io
   ```

2. **sop-agent 결과 경로?**
   ```
   ~/sop-agent/results/<고객사>/
   ```

3. **경쟁사 봇이 작동 중인 고객사인가요?**
   - Yes → 기존 챗봇(GL 등)이 있는 경우
   - No → 신규 도입

4. **ALF 태스크 JSON 있으세요?**
   - No (보통) → `04_tasks/*.md` 자동 파싱
   - Yes → JSON 파일 경로 입력

5. **시나리오 수?**
   - 25 (기본값, 권장)

### 실행 진행

Claude가 자동으로 Phase 1-6을 순차 실행합니다:

```
[Phase 1] Normalizing sop-agent results...
[Phase 2] Generating scenarios...
          → 25 scenarios covering 72.3% of actual conversations
          Continue? (yes/no)
> yes

[Phase 3] Executing scenarios with Playwright...
          [1/25] product_001 (persona=polite_clear) → completed
          [2/25] product_002 (persona=vague) → completed
          ...
          [25/25] oos_002 (persona=adversarial) → completed

[Phase 4] Summarizing execution results...
[Phase 5] Scoring with AI Judge...
          [1/25] product_001 → pass (3/3 criteria)
          [2/25] product_002 → pass (3/3 criteria)
          ...

[Phase 6] Generating client report...
          → report_client.html
```

**소요 시간:**
- Phase 1-2: ~3분
- Phase 3: **30~60분** (가장 오래 걸림)
- Phase 4-6: ~8분

---

## Step 5: 결과 확인

### Claude에게 요청

```
<고객사> QA 리포트 열어줘
```

**또는 수동으로:**
```bash
open ~/qa-agent/storage/runs/<run_id>/report_client.html
```

### 리포트 내용

HTML 슬라이드가 브라우저에서 열립니다:

1. **Slide 1: 커버**
   - 고객사명 + Run ID

2. **Slide 2: 전체 결과**
   - Phase 1/2 관여율
   - 테스트 시나리오 수

3. **Slide 3: 대화 예시**
   - ChannelTalk 위젯 UI
   - 실제 테스트 대화 전문

4. **Slide 4: 결론**
   - 권장 진행 방식

**네비게이션:**
- 키보드 화살표 (← →)
- 화면 좌우 버튼 클릭

---

## 자주 묻는 질문 (FAQ)

### Q1. "qa-agent 스킬을 찾을 수 없습니다" 오류

**원인:** Claude Code가 `~/qa-agent/skills/qa-agent/SKILL.md`를 인식하지 못함

**해결:**
```
qa-agent 스킬 다시 로드해줘
```

### Q2. Phase 3 실행이 매우 느림

**원인:** Playwright가 ALF 응답을 기다림 (timeout 60초)

**정상:** 시나리오당 1~2분 소요는 정상입니다.
- ALF 응답 대기 시간 포함
- 페르소나 LLM 호출 시간 포함

**비정상:** 5분 이상 멈춰있으면 중단 후 재실행
```
Ctrl+C로 중단 후 재실행해줘
```

### Q3. 브라우저 창이 보이지 않음

**정상:** 기본 모드는 headless (백그라운드 실행)

**브라우저 보려면:**
```
--headed 모드로 실행해줘
```

### Q4. 여러 고객사 QA를 동시에 실행할 수 있나요?

**불가:** Playwright는 동시에 한 세션만 실행 가능

**권장:**
- 순차 실행
- 또는 별도 머신에서 실행

### Q5. 결과를 다시 확인하고 싶어요

```
storage/runs/ 아래 최근 run_id 리스트 보여줘
```

```
<run_id> 리포트 다시 열어줘
```

---

## 다음 단계

### 정기 QA 실행

고객사 ALF 세팅을 변경한 후:

```
<고객사> QA 재실행해줘
```

기존 시나리오를 재사용하여 Phase 3-6만 실행합니다.

### 여러 고객사 관리

```
~/qa-agent/projects/<고객사>/config.yaml 생성해줘
```

고객사별 설정을 저장하여 재사용할 수 있습니다.

### 상세 분석

```
<run_id> 상세 리포트(report.md) 보여줘
```

시나리오별 pass/fail 상세 내역을 확인할 수 있습니다.

---

## 트러블슈팅 체크리스트

실행 전 확인:

- [ ] `~/qa-agent/.env` 파일 존재
- [ ] `ANTHROPIC_API_KEY` 설정됨
- [ ] `uv sync` 완료
- [ ] `playwright install chromium` 완료
- [ ] sop-agent 결과 경로 존재
- [ ] 테스트 채널 URL 접속 가능
- [ ] 테스트 채널에 ALF 세팅 완료

실행 중 오류 시:

1. **API 키 오류**
   ```
   .env 파일 확인해줘
   ```

2. **Playwright 오류**
   ```bash
   cd ~/qa-agent
   uv run playwright install chromium
   ```

3. **시나리오 생성 실패**
   ```
   sop-agent 결과 경로에 필수 파일이 있는지 확인해줘:
   - 03_sop/metadata.json
   - 02_extraction/faq.json
   - 02_extraction/patterns.json
   ```

4. **실행 중단**
   ```
   같은 run_id로 Phase 3부터 재실행해줘
   ```

---

## 지원

- **Slack**: AX팀 채널
- **GitHub Issues**: https://github.com/Eren-ax/qa-agent/issues
- **문서**: `~/qa-agent/README.md`, `~/qa-agent/docs/`

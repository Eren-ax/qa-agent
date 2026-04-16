# QA-Agent 고도화 컨텍스트: GL 고객사 전환 대응

## 1. 조직 배경

### AX팀 GL 대응 전략 변경 (2026-04)
- **이전**: GL 사용 고객사 80개를 병렬 대응
- **현재**: "하나씩 확실한 것부터" GL 독립시키는 순차 전략으로 전환
- **우선순위 기준**: GL 만족도 낮은 곳 + 채널 지원 앱 함수 ∩ 고객사 admin 서비스 교집합이 큰 곳
- **목표 속도**: 1주에 1인당 1개 고객사 전환
- **세팅 주체**: AX팀이 직접 전담 세팅 (고객사 CS팀 공수 없음, GL 고객사 밀착 케어)

### 전환 파이프라인 구조
```
sop-agent (상담 데이터 → SOP/규칙/지식/Task 설계)
    ↓ 산출물을 qa-agent 입력으로
qa-agent (ALF 세팅 검증 → 커버리지 수치 산출 → 고객사 보고서)
    ↓ 수치 기반
고객사 설득: "GL off + ALF on 하면 즉시 이만큼, 추가하면 이만큼"
```

### 기술 스택 전제
- 고객사 대부분: **카페24 (쇼핑몰) + 이지어드민 플러스 (WMS)** 기반
- 이지어드민: API 키 불필요, 도메인 + ID + PW만 사용 (개발팀 확인)
- 카페24: 앱 함수 인증 정보 (mall_id, client_id, etc.) 는 고객사에서 수령

---

## 2. 벨리에 (1호 전환 사례) 에서 검증된 사실

### GL봇 실측 데이터
- GL봇 개입률: 68.8% (1,864/2,711건)
- 매니저 에스컬레이션률: 88.1%
- 실질 해결률 (매니저 없이 종료): 3.5%
- **Read Task (조회) 수행**: 2.79% (52/1,864건) — 주문조회 24, 배송추적 11, 반품/환불 13, 쿠폰/적립금 13
- **Write Task (상태 변경) 수행**: 1건 (배송지 변경만). 취소/반품접수/교환접수: 0건
- **결론**: GL봇은 대부분 조회+에스컬레이션 중심. Write Task는 사실상 미수행.

### ALF 예상 효과 (sop-agent 분석 기반)
- Phase 1 (RAG + Task 즉시): ~70% 자동화 (636건/월)
- Phase 2 (추가 세팅, 1-2개월): ~85% 자동화 (772건/월)
- ROI: Phase 1 55.7%, Phase 2 67.6%

### qa-agent 벨리에 실측 결과 (r-20260414-belier25)
- 31 시나리오 실행
- 커버리지: 34.4% (관여율 43.4% × 해결률 79.3%)
- 해결률: happy 86.7%, unhappy 87.5%, edge 100%
- 실패 분포: rag_miss 4건, error 1건

### sop-agent → qa-agent 연결 산출물
- `patterns.json` (GL봇 분석 포함: gl_bot_read_task_execution, gl_bot_write_task_execution)
- `automation_analysis.md` (4-Layer 모델: RAG / Task / Hybrid / Human)
- `03_sop/*.sop.md` (11개 SOP, GL봇 vs ALF 비교 섹션 포함)
- `04_tasks/TASK1~7.md` (7개 Task 스펙, TASK7은 상담사 승인노드 기반 AS접수)
- `07_deployment/deployment_qa_set.md` (37개 QA 세트)

---

## 3. qa-agent 고도화가 필요한 이유

### 현재 qa-agent가 산출하는 것
- "ALF가 현재 세팅 기준으로 얼마나 작동하는가" (단일 score)
- 관여율 × 해결률 = 커버리지 (3-tier)

### GL 전환 맥락에서 필요한 것
- **"GL에서 ALF로 전환하면 즉시 이만큼 작동한다"** (Phase 1 score)
- **"이런 추가 세팅을 하면 이만큼 더 작동할 것이다"** (Phase 2 예측)
- **GL봇 baseline 대비 몇 배 나은지** (경쟁사 프레이밍)

### 핵심 차이
- 단일 score → Phase 1 / Phase 2 분리 score
- ALF 절대 수치 → GL봇 baseline 대비 상대 수치
- "작동 여부" → "전환 시 기대 효과" (설득력 있는 비즈니스 보고)

---

## 4. 고도화 방향 (수정 포인트 3가지)

### Gap 1: 시나리오 생성에 GL봇 baseline 태깅

**현재**: 시나리오에 intent, difficulty, persona만 있음
**필요**: 각 시나리오에 `gl_bot_baseline` 필드 추가

```json
{
  "id": "ht_order_cancel_return.happy.1",
  "gl_bot_baseline": {
    "can_handle": false,
    "gl_behavior": "에스컬레이션 (주문조회 Read만 간헐 수행, 취소 Write 0건)",
    "gl_resolution": 0.0
  }
}
```

**소스**: sop-agent의 `patterns.json` → `analysis_context.gl_bot_read_task_execution` / `gl_bot_write_task_execution`
**효과**: report에서 "GL봇은 이 시나리오를 0% 해결 → ALF는 86.7% 해결 = ∞배 개선" 자동 산출

### Gap 2: Phase 1 / Phase 2 분리 scoring

**현재**: ALF에 세팅된 것 전체로 단일 score
**필요**: 시나리오를 Phase로 태깅하여 분리 집계

```
Phase 1 시나리오 = RAG 기반 응답만으로 해결 가능한 것 (정보 문의, FAQ)
Phase 2 시나리오 = Task API 호출이 필요한 것 (주문조회, 취소, 반품, 교환)
```

**방안 A (시나리오 레벨 태깅)**:
- `generate_scenarios.md`에서 시나리오 생성 시 `phase` 필드 추가
- scoring_agent.py에서 phase별 분리 집계

**방안 B (2-pass 실행)**:
- 1차: RAG+Rules만 on, Task off → Phase 1 score 측정
- 2차: RAG+Rules+Task on → Phase 2 score 측정
- 더 정확하지만 실행 시간 2배

**방안 C (시뮬레이션)**:
- 실행은 1회 (Full 세팅), scoring 시 task_called 시나리오를 Phase 2로 분류
- Phase 1 score = task_called 시나리오 제외한 나머지의 score
- Phase 2 score = 전체 score
- 가장 효율적, 약간 부정확

**소스**: sop-agent의 `automation_analysis.md` → 4-Layer 모델 (RAG / Task / Hybrid / Human)

### Gap 3: "추가 세팅 시 기대 효과" 예측 리포트

**현재**: report_client.md에 Phase roadmap 있으나 범용 프레이밍
**필요**: sop-agent 분석 결과를 report_client.md에 자동 주입

주입 데이터:
- 4-Layer 모델의 Layer별 건수/비중
- Task별 커버 건수 (TASK1~7)
- GL봇 baseline 대비 개선 배율
- ROI 수치 (Phase 1/2)

**효과**: report가 "현재 34.4% → Phase 1 RAG만으로 ~55% → Phase 2 Task 포함 ~70%" 자동 서술

---

## 5. 관련 파일 참조

### qa-agent 코드
- 시나리오 생성: `/Users/eren/qa-agent/prompts/generate_scenarios.md` (486줄, Rules 1-9)
- Scoring: `/Users/eren/qa-agent/tools/scoring_agent.py` (685줄, 3-tier metrics)
- Client report: `/Users/eren/qa-agent/prompts/generate_client_report.md` (240줄)
- Judge prompt: `/Users/eren/qa-agent/prompts/judge_scenario.md` (73줄)
- Normalize: `/Users/eren/qa-agent/prompts/normalize_sop.md` (442줄)
- Schema: `/Users/eren/qa-agent/tools/result_store.py` (401줄)
- Orchestration: `/Users/eren/qa-agent/skills/qa-agent/SKILL.md` (516줄)

### 벨리에 산출물 (1호 전환 사례, 참고용)
- GL봇 분석 데이터: `/Users/eren/sop-agent/results/벨리에v2/02_extraction/patterns.json`
- 자동화 분석: `/Users/eren/sop-agent/results/벨리에v2/05_sales_report/analysis/automation_analysis.md`
- Task 스펙: `/Users/eren/sop-agent/results/벨리에v2/04_tasks/TASK1~7.md`
- 벨리에 실행 결과: `/Users/eren/qa-agent/storage/runs/r-20260414-belier25/`

### 방법론 지침
- 금칙 설정 작성 지침 (5원칙): `/Users/eren/Documents/Obsidian Vault/main/caution/금칙 설정 작성 지침.md`
- 상담사 승인노드 스펙: `/Users/eren/ax-workspace/docs/approval-node-spec.md`

---

## 6. 고도화 우선순위 (Eren 판단 기준: 고도화 수준 > 자동화 수준)

1. **Gap 2 (Phase 1/2 분리 scoring)** — 고객사 설득의 핵심 ("즉시 이만큼, 추가하면 이만큼")
2. **Gap 1 (GL봇 baseline 태깅)** — 경쟁사 대비 프레이밍 자동화 ("GL은 0%, ALF는 X%")
3. **Gap 3 (예측 리포트)** — sop-agent 분석을 qa-agent report에 자동 연결

---

## 7. 제약 사항

- qa-agent는 **파트타이머/인턴이 일관 품질로 운영 가능**해야 함 (zip 배포 모델)
- 1주 1고객사 속도를 위해 **Phase 3 실행 시간** (현재 ~45분/31시나리오)이 병목
- 고객사별 가변 요소: 채널 URL, sop-agent 산출물 경로, 앱 함수 리스트, GL봇 personId
- 벨리에 외 고객사에서도 GL봇 데이터 구조 (personType=bot, personId) 동일한지 확인 필요

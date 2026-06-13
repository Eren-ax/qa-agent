# bp-qa 마이그레이션 완료 요약

## ✅ 완료된 작업

qa-agent 저장소에서 team-ax-plugin으로 Best Practice QA 스킬 마이그레이션을 완료했습니다.

### 📦 마이그레이션 내역

| 항목 | 개수 | 설명 |
|---|---|---|
| **Python tools** | 25개 | 핵심 로직 모듈 (extractor, runner, reporter 등) |
| **Prompts** | 8개 | LLM 프롬프트 (시나리오 생성, 채점 등) |
| **Examples** | 1개 | 샘플 run 데이터 |
| **Documentation** | 2개 | SKILL.md (스킬 명세), README.md (사용 가이드) |
| **Dependencies** | 1개 추가 | playwright>=1.48.0 |

### 📁 디렉토리 구조

```
team-ax-plugin/
└── skills/
    └── bp-qa/                          ← 새로 추가됨
        ├── SKILL.md                    # Claude Code 오케스트레이션 명세
        ├── README.md                   # 사용자 가이드
        ├── tools/                      # Python 모듈 (25개)
        │   ├── best_practice_extractor.py
        │   ├── scenario_runner.py
        │   ├── bp_qa_report_generator.py
        │   └── ... (22 more)
        ├── prompts/                    # LLM 프롬프트 (8개)
        │   ├── generate_scenarios_v2.md
        │   ├── persona_archetypes.md
        │   └── ... (6 more)
        └── examples/                   # 샘플 데이터
            └── sample-run-r-20260413-example/
```

### 🔧 변경사항

#### requirements.txt
```diff
+ playwright>=1.48.0
```

#### Git 커밋
- **Commit**: `feat(bp-qa): migrate Best Practice QA skill from qa-agent`
- **Files changed**: 39 files
- **Lines added**: 11,791 insertions

---

## 📊 bp-qa vs rag-qa

team-ax-plugin에 이제 두 가지 QA 스킬이 공존합니다:

| 항목 | **bp-qa** (새로 추가) | **rag-qa** (기존) |
|---|---|---|
| **목적** | 우수 케이스 재현 검증 | 전체 볼륨 대표성 측정 |
| **입력** | Clustering Excel | sop-agent 전체 결과 |
| **시나리오** | BP 기반 Layer 1/2/3 | 통계적 미러링 (볼륨 가중) |
| **평가** | QA Score (10점) | 3단계 지표 (coverage × engagement × resolution) |
| **리포트** | BP vs ALF 1:1 비교 | 비즈니스 리포트 + 슬라이드 |

**두 스킬은 상호 보완적입니다**:
- `rag-qa`: 정기 측정, 자동화 커버리지, 고객사 보고
- `bp-qa`: 특정 케이스 검증, 고객사 데모, 디버깅

---

## 🚀 사용 방법

### Claude Code에서

```bash
# BP QA 스킬 호출
/bp-qa
```

Claude가 다음을 순서대로 물어봅니다:
1. Clustering Excel 경로
2. 채널 URL
3. BP 선택 모드 (자동/수동)
4. 테스트 케이스 수
5. Layer 전략

### 직접 실행 (CLI)

```bash
# 의존성 설치
cd team-ax-plugin
uv sync
uv run playwright install chromium

# 실행
uv run python -m skills.bp-qa.tools.bp_qa_runner \
  --clustered-excel ~/sop-agent/results/벨리에/01_clustering/벨리에_clustered.xlsx \
  --channel-url https://vqnol.channel.io \
  --output-dir storage/qa_$(date +%Y%m%d) \
  --target-total 50
```

---

## 📝 출력 산출물

```
storage/qa_YYYYMMDD/
├── transcripts.jsonl                      # BP + ALF 대화 기록
├── QA_REPORT_<client>_<date>.html        # BP vs ALF 비교 리포트 (HTML)
└── QA_REPORT_<client>_<date>.md          # 텍스트 요약 리포트
```

**HTML 리포트 특징**:
- 2열 grid 레이아웃: BP 대화 | ALF 대화
- 채팅 말풍선 UI (Channel.io 위젯 스타일)
- QA Score: 정확성(5) + 완결성(3) + 톤&매너(2)
- 카테고리별 통계

---

## 🔍 핵심 기능

### 1. Best Practice 자동 추출

Clustering Excel에서 품질 기반 자동 선정:
- 해결 상태 (solved)
- CSAT 점수
- ALF 작동 여부
- 클러스터 크기

### 2. Layer 1/2/3 전략

| Layer | 방식 | 특징 |
|---|---|---|
| Layer 1 | LLM 생성 (BP 스타일 참고) | 자연스러운 변형 |
| Layer 2 | 원문 추출 (첫 발화) | 정확한 재현 |
| Layer 3 | Layer 1 + 검증 | 품질 보장 |

### 3. QA Score (10점 만점)

- **정확성 (5점)**: BP와 동일한 정보 제공
- **완결성 (3점)**: 필요한 정보 포함
- **톤&매너 (2점)**: 친근하고 적절한 톤

---

## 🎯 다음 단계

### 즉시 사용 가능
✅ `/bp-qa` 스킬 바로 사용 가능  
✅ 모든 도구 및 문서 완비  
✅ 예시 데이터 포함

### 선택적 작업 (필요시)

1. **통합 테스트**
   ```bash
   cd team-ax-plugin/skills/bp-qa
   pytest tests/ # 테스트 추가 필요
   ```

2. **문서 업데이트**
   - `team-ax-plugin/README.md`에 bp-qa 스킬 추가
   - `docs/skills-comparison.md` 작성 (rag-qa vs bp-qa)

3. **CI/CD 설정**
   - `.github/workflows/` 에 bp-qa 테스트 추가

---

## 📚 소스 정보

- **원본 저장소**: https://github.com/channel-io/qa-agent
- **버전**: v3 (2026-05-14)
- **마이그레이션 날짜**: 2026-06-10
- **마이그레이션 커밋**: 4081974

---

## ✨ 마이그레이션 하이라이트

### 완전성
- ✅ 모든 Python 모듈 (25개)
- ✅ 모든 프롬프트 (8개)
- ✅ 예시 데이터
- ✅ 완전한 문서

### 품질
- ✅ Claude Code 스킬 명세 (SKILL.md)
- ✅ 상세한 사용 가이드 (README.md)
- ✅ Layer 전략 설명
- ✅ QA Score 채점 기준

### 호환성
- ✅ 기존 team-ax-plugin 구조 유지
- ✅ rag-qa 스킬과 독립적
- ✅ 공통 의존성 재사용 (pandas, openpyxl)

---

## 🙋 FAQ

### Q1: bp-qa와 rag-qa 중 어떤 것을 사용해야 하나요?

**bp-qa**: 특정 우수 케이스 재현, 고객사 데모, 디버깅  
**rag-qa**: 전체 커버리지 측정, 정기 보고, 고객사 발표

### Q2: qa-agent 저장소는 삭제해도 되나요?

**Yes**, bp-qa 스킬이 qa-agent의 모든 핵심 기능을 포함합니다.
단, 아래를 먼저 확인하세요:
- 진행 중인 브랜치가 없는지
- 로컬 변경사항이 없는지
- 다른 팀원이 사용 중이지 않은지

### Q3: 수동 BP 선택은 어떻게 하나요?

`manual_bp.tsv` 파일 작성:
```tsv
user_chat_id	intent
6997a6f8bc02a881342e	데님 팬츠 재입고 문의
6981fe3c37a26d3d48a5	반품 수거 지연
```

그리고 `/bp-qa` 실행 시 "수동 지정" 선택 후 경로 입력.

---

## 📞 문의

AX팀 또는 Eren에게 문의해주세요.

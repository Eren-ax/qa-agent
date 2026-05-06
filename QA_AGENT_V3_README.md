# qa-agent v3: Userchat Replay Mode

**목표**: 실제 user-chat 대화를 ALF에 재생하여 응답 일관성을 측정

---

## 개요

### v2 vs v3 차이점

| 측면 | v2 (시나리오 기반) | v3 (실제 대화 재생) |
|---|---|---|
| **입력** | sop-agent 분석 결과 | 실제 user-chat 링크 |
| **발화 생성** | LLM 페르소나 (5종) | 원본 유저 발화 그대로 |
| **채점 기준** | success_criteria 충족 | 원본 응답 vs 재생 응답 유사도 |
| **목적** | 새 ALF 성능 측정 | 기존 ALF 응답 재현성 측정 |

---

## 파이프라인

```
실제 user-chat 링크
    │
    ▼
1. Extract ──────── Langfuse trace → 구조화된 대화
    │                (userchat_extractor.py)
    ▼
2. Replay ───────── 원본 발화를 ALF에 재전송
    │                (replay_runner.py)
    ▼
3. Judge ────────── 응답 유사도 채점
                     (similarity_judge.py)
```

---

## 사용 방법

### Step 1: User-chat 추출

```bash
# Langfuse MCP로 trace 가져오기
mcp__langfuse__fetch_traces \
  --session-id <alf_session_id> \
  --age 1440 \
  --include-observations true \
  --output-mode full_json_file

# 구조화된 대화로 변환
uv run python -m tools.userchat_extractor \
  --langfuse-json /tmp/langfuse_traces.json \
  --output /tmp/extracted_userchat.json
```

**출력 예시**:
```json
{
  "userChatId": "69f209716b807bddf86a",
  "alfSessionId": "17d5f164-5258-4caf-8cf9-45dfda5a5562",
  "channelId": "236373",
  "turns": [
    {
      "turn": 1,
      "user": "리프팅 레이저 샷수 추천 받을 수 있어요?",
      "alf": "안녕하세요 에피소드의원입니다...",
      "timestamp": "2026-04-29T13:36:56..."
    }
  ]
}
```

### Step 2: Replay 실행

**Mode 1: Exact replay (원본 발화 그대로)**
```bash
uv run python -m tools.replay_runner \
  --userchat-json /tmp/extracted_userchat.json \
  --channel-url https://test.channel.io \
  --output /tmp/replay_result.json \
  --headed \
  --timeout 120 \
  --max-turns 1  # 첫 턴만 (권장)
```

**Mode 2: Adaptive replay (LLM이 맥락에 맞게 조정)**
```bash
uv run python -m tools.replay_runner \
  --userchat-json /tmp/extracted_userchat.json \
  --channel-url https://test.channel.io \
  --output /tmp/replay_result.json \
  --adaptive \
  --max-turns 5 \
  --headed \
  --timeout 120
```

**Adaptive 모드 특징**:
- **유저 말투 모방**: 해당 user-chat의 실제 유저 발화 스타일 분석 & 복제
- **목적 달성 감지**: ALF가 목적을 달성하거나 상담사 연결하면 자동 종료
- **자연스러운 끝말**: "..." 끊김 방지, 자연스러운 어미로 종료
- **모델**: Opus 4.7 (ADAPTIVE_MODEL 환경변수로 변경 가능)
- **Temperature**: 0.2 (일관성 우선)

**출력 예시**:
```json
{
  "originalUserChatId": "69f209716b807bddf86a",
  "replayTurns": [
    {
      "turn": 1,
      "userMessage": "리프팅 레이저 샷수 추천 받을 수 있어요?",
      "alfMessages": ["안녕하세요 에피소드의원입니다..."],
      "replyLatencyS": 8.5
    }
  ]
}
```

### Step 3: 유사도 채점

```bash
uv run python -m tools.similarity_judge \
  --original /tmp/extracted_userchat.json \
  --replay /tmp/replay_result.json \
  --output /tmp/similarity_scores.json
```

**채점 지표**:
1. **Semantic Similarity** (0.0-1.0)
   - LLM Judge 사용
   - 같은 정보를 제공하는지, 같은 의도인지
   
2. **Structural Similarity** (0.0-1.0)
   - Rule-based
   - 길이 비율, URL 유무, 포맷 (마크다운, 불릿 등)

3. **Overall Score** (0.0-1.0)
   - `0.7 × semantic + 0.3 × structural`

**출력 예시**:
```json
{
  "turnScores": [
    {
      "turn": 1,
      "semanticScore": 0.85,
      "structuralScore": 0.90,
      "overallScore": 0.865,
      "notes": "Both responses provide same pricing info..."
    }
  ],
  "avgSemantic": 0.85,
  "avgStructural": 0.90,
  "avgOverall": 0.865
}
```

---

## 유스케이스

### 1. ALF 설정 변경 전후 비교
- 규칙/지식 수정 후 기존 응답이 유지되는지 확인
- 동일한 user-chat 링크로 재생 → 응답 유사도 측정

### 2. 프롬프트 튜닝 검증
- 시스템 프롬프트 변경 후 실제 대화 재생
- 의도하지 않은 응답 변화 감지

### 3. 모델 업그레이드 영향 분석
- Claude 4.6 → 4.7 등 모델 변경 시
- 실제 대화로 회귀 테스트

---

## 구현 파일

| 파일 | 역할 |
|---|---|
| `tools/userchat_extractor.py` | Langfuse trace → 구조화된 대화 |
| `tools/replay_runner.py` | 원본 발화 재생 실행 (exact/adaptive 모드) |
| `tools/similarity_judge.py` | 응답 유사도 채점 |
| `tools/user_style_analyzer.py` | 유저 발화 스타일 분석 (adaptive용) |
| `tools/intent_tracker.py` | 대화 목적 추출 & 달성 감지 (adaptive용) |
| `tools/message_formatter.py` | LLM 출력 후처리 (자연스러운 끝말) |
| `prompts/adaptive_user_replay.md` | Adaptive 모드 프롬프트 |

---

## 제한사항

1. **Langfuse에 trace가 있어야 함**
   - ALF 세션이 없는 대화는 추출 불가
   - 상담사 전용 대화는 불가 (ALF 응답 없음)

2. **채널 설정이 동일해야 함**
   - 규칙/지식/태스크가 원본과 다르면 응답이 달라질 수 있음
   - 테스트 채널에서 동일한 설정 복제 필요

3. **Context 의존성**
   - 원본 대화의 context (페이지 URL, 시간 등)가 재생 시 다를 수 있음
   - 일부 응답은 context에 따라 달라질 수 있음

---

## 향후 개선

- [ ] 대량 user-chat 링크 배치 처리
- [ ] HTML 리포트 생성 (v2처럼)
- [ ] Context 재현 (페이지 URL, 시간 등)
- [ ] Task 호출 여부 비교 (구조적 유사도 강화)

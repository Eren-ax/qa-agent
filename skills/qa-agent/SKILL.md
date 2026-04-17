---
name: qa-agent
description: End-to-end ALF QA pipeline — sop-agent 분석 → 통계적 미러링 시나리오 생성 → ALF 테스트 → 3단계 투명 지표 채점 → 클라이언트 리포트(md + 슬라이드 HTML) 산출. storage/runs/<run_id>/에 전체 아티팩트 적재.
---

# qa-agent — Orchestration Spec (v2: Statistical Mirroring)

You are the **qa-agent orchestrator**. Your job is to take a test channel URL
and a sop-agent results directory, then produce a complete v0-schema run
under `storage/runs/<run_id>/`.

**v2 핵심 개선 (2026-04-16)**:
1. **통계적 미러링 (Statistical Mirroring)**: 시나리오가 실제 90일 상담 데이터의 정확한 통계적 복제
2. **3단계 투명 지표**: scenario_coverage × alf_engagement_rate × alf_resolution_rate = actual_coverage
3. **즉시 에스컬레이션 버그 수정**: engaged=False를 관여율에서 제외하여 과대 계상 방지

You compose four prompts and three Python tools. Do not improvise the
pipeline shape — follow phases 1-4 below in order. Each phase has a
deterministic output that the next phase consumes.

---

## When to invoke this skill

A user asks for any of:
- "QA 돌려줘 / QA 실행해줘"
- "ALF 자동화 측정해줘"
- "이 채널 시나리오 테스트해줘"
- Provides a test channel URL + sop-agent results path

Out of scope (route to a different tool):
- Running a single ad-hoc conversation: use `tools.cli --record` directly.
- Re-scoring an existing run: that's `scoring-agent` (separate skill).
- Generating an ALF task spec doc: that's `alf-task-doc` skill.

---

## Required inputs (gather before starting)

| Input | How to obtain |
|---|---|
| `channel_url` | ask the user; example: `https://vqnol.channel.io` |
| `sop_results_dir` | ask the user; example: `~/sop-agent/results/<client>/` (sop-agent v2 format) |
| `is_competitor_bot` | ask: "현재 경쟁사 봇(GL 등)이 작동 중인 고객사인가요?" — GL baseline 비교 리포트 생성 여부 결정 |
| `coverage_mode` | ask: "어떤 범위를 테스트할까요?" — **`channel_only`** (지식+승인노드, 기본값) / `rag_only` (지식만, Task 세팅 전) / `full` (지식+Task 전체). Default: **`channel_only`** |
| `alf_task_json_path` | optional; ask "ALF 태스크 JSON 있으세요?" — if present, use `<sop_results_dir>/04_tasks_json/*.json` (v2 primary); fallback to `04_tasks/*.md` |
| `target_total` | optional; default **25** |
| `headed` | optional; default **false** (headless). Use `true` only for debugging. |

**sop-agent v2 changes**:
- Task JSON: `04_tasks_json/*.json` (primary) → `04_tasks/*.md` (fallback)
- automation_analysis: `05_sales_report/analysis/automation_analysis.md` (moved to subdirectory)
- response_strategies.json: **removed** (escalation_triggers now in patterns.json)

If any required input is missing or the path doesn't exist, **stop and ask
the user** before proceeding. Do not invent paths.

---

## Output contract

On success, you produce a directory:

```
storage/runs/<run_id>/
├── canonical_input.yaml      # phase 1 output (kept for replay)
├── config_snapshot.json      # phase 2.1 output
├── scenarios.json            # phase 2.2 output (matches v0 ScenarioSet)
├── transcripts.jsonl         # phase 3 output, one line per scenario
├── scores.json               # phase 5 output (scoring_agent)
├── report.md                 # phase 5 output (내부 상세 리포트)
├── report_client.md          # phase 6 output (클라이언트 비즈니스 리포트)
└── report_slides.html        # phase 6 output (슬라이드 발표 자료)
```

Where `<run_id>` comes from `tools.result_store.new_run_id()`.

After completion, return to the user:
- The run_id
- The output directory path
- 핵심 수치 요약:
  - **Phase 1 (RAG만)**: 즉시 도입 시 커버리지 (rag_only mode)
  - **Phase 2 (전체)**: Task 연동 후 커버리지 (full mode)
  - **경쟁사 봇 대비 개선**: GL 해결률 vs ALF 해결률 (×N배)
  - 관여율, 해결률
- `report.md` 경로 (상세 분석)
- `report_slides.html` 경로 (브라우저에서 바로 열 수 있음)

---

## Implementation status

All six phases are implementable today.

| Phase | Implementation |
|---|---|
| 1. Normalize | apply `prompts/normalize_sop.md`, persist YAML |
| 2. Snapshot + generate | apply `prompts/generate_scenarios.md`, write via `tools.result_store` |
| 3. Execute | invoke `tools.scenario_runner` (Anthropic SDK + PlaywrightDriver) |
| 4. Summarize | read via `tools.result_store.read_transcripts` |
| 5. Score | invoke `tools.scoring_agent` → scores.json + report.md |
| 6. Client report | apply `prompts/generate_client_report.md` → report_client.md + report_slides.html |

For an interactive single-conversation sanity check (no persona automation,
human plays customer), use `tools.cli --record --run-id <run_id>` instead.

---

## Pipeline

### Phase 1 — Normalize sop-agent output

**Reads**: `sop_results_dir` (+ optional `alf_task_json_path`)
**Writes**: `storage/runs/<run_id>/canonical_input.yaml`
**Prompt**: `prompts/normalize_sop.md`

Steps:
1. Generate `run_id` via `tools.result_store.new_run_id()`.
2. Create the run directory via `tools.result_store.run_dir(run_id)`.
3. **File access pattern**: pass **paths** (not contents) to the prompt
   for files >5 KB or binary; pass **contents inline** for small JSON/MD
   files. Always pass `sop_results_dir` as a path so the prompt can fill
   `generation_metadata.normalized_from`. The prompt itself can request
   additional reads if needed.
4. Apply the normalize prompt to produce canonical YAML.
5. Persist raw to `storage/runs/<run_id>/canonical_input.yaml`.
6. Validate parseability: the YAML must load cleanly and contain the
   top-level keys `schema_version`, `client`, `intents`, `tasks`,
   `out_of_scope_hints`, `generation_metadata`. **Stop and abort** if
   parsing fails or required keys are absent.

### Phase 2 — Snapshot config + generate scenarios

**Phase 2.1 — config_snapshot.json**

**Writes**: `storage/runs/<run_id>/config_snapshot.json`
**Tool**: `tools.result_store.write_config_snapshot()`

Construct a `ConfigSnapshot` from the canonical input:

```python
ConfigSnapshot(
    schema_version=SCHEMA_VERSION,
    run_id=run_id,
    captured_at=utcnow_iso(),
    channel_url=channel_url,
    knowledge_summary=[
        {"id": i["id"], "label": i["label"], "records": i["records"],
         "automation_ready": i["automation_ready"]}
        for i in canonical["intents"]
    ],
    rules_summary=[],   # v0: not yet sourced — leave empty, document gap in extra
    tasks_summary=[
        {"id": t["id"], "name": t["name"],
         "external_admin_required": t["external_admin_required"]}
        for t in canonical["tasks"]
    ],
    sop_result_ref=str(sop_results_dir),
    extra={
        "client_name": canonical["client"]["name"],
        "is_competitor_bot": is_competitor_bot,
        "alf_task_json": alf_task_json_path,
        "target_total": target_total,
        "rules_source_gap": "v0: rule extraction not implemented; rules_summary intentionally empty",
    },
)
```

**Phase 2.2 — scenarios.json (통계적 미러링)**

**Writes**: `storage/runs/<run_id>/scenarios.json`
**Prompt**: `prompts/generate_scenarios.md`
**Tool**: `tools.result_store.write_scenarios()`

**v2 핵심 원칙**:
- **인텐트 비율 = 실제 상담 비율**: 각 인텐트의 estimated_records를 기반으로 정확히 할당
- **난이도 비율 = 실제 유효 비율**: OOS 제외한 실제 데이터에서 Happy/Edge/Unhappy 비율 계산
- **액션 중심 평가**: task_called (API 호출 정확도) + llm_judge (특정 정책 안내)

Steps:
1. **통계 추출** (canonical YAML에서):
   ```python
   # 인텐트별 비중 계산
   total_records = sum(i["records"] for i in canonical["intents"])
   intent_allocation = {
       i["id"]: round(i["records"] / total_records * target_total)
       for i in canonical["intents"]
   }
   
   # 난이도 비율 계산 (patterns.json 또는 metadata.json에서)
   # Happy: 정형화된 프로세스 (재입고, 멤버십 등)
   # Edge: 복잡/경계 (Context Switching, 파라미터 오류)
   # Unhappy: 감정적 불만 (AS, 불량 신고 등)
   ```

2. Apply `generate_scenarios.md` with explicit context:
   - `canonical`: full canonical YAML from Phase 1
   - `personas`: persona archetype catalog table
   - `target_total`: integer
   - **NEW**: `intent_allocation`: 인텐트별 정확한 시나리오 개수
   - **NEW**: `difficulty_distribution`: 전체 난이도 비율 (Happy/Edge/Unhappy)

3. **검증 규칙**:
   - 인텐트별 할당 개수가 정확히 일치하는가?
   - 난이도 비율이 ±10% 이내인가?
   - 모든 시나리오가 v0 스키마를 만족하는가?
   - success_criteria 타입이 올바른가? (RAG → llm_judge, Task → task_called)

4. **If validation fails**, re-invoke the prompt once with the validation
   error appended as feedback. If it fails twice, stop and report.

5. Persist via `write_scenarios(run_id, scenario_set)`.

Display the coverage summary (from `generation_note`) to the user before
proceeding to Phase 3.

### Phase 3 — Execute scenarios

**Reads**: `scenarios.json`
**Writes**: `storage/runs/<run_id>/transcripts.jsonl` (append per scenario)
**Tool**: `tools.scenario_runner` (wraps `PlaywrightDriver` and the
Anthropic SDK)
**Prompt context**: `prompts/persona_archetypes.md`

Invoke as a subprocess from the skill:

```bash
uv run python -m tools.scenario_runner \
  --run-id <run_id> \
  --channel-url <channel_url> \
  [--scenario-id <id>] \
  [--headed] \
  [--timeout 60]
```

The runner consumes `storage/runs/<run_id>/scenarios.json`, drives each
scenario end-to-end, and appends transcripts as it goes. Stream the
runner's stdout to the user so they see per-scenario progress live.

**Implementation contract** (mirrored in `tools/scenario_runner.py`):

1. **Open a fresh session**:
   ```python
   driver = PlaywrightDriver(headless=not headed)
   welcome = await driver.open(channel_url)
   ```
2. **Send turn 0** (the seeded `initial_message`, persona is **not**
   invoked here):
   ```python
   user_ts = time.time()
   await driver.send(scenario.initial_message)
   replies = await driver.wait_reply(timeout=60)
   ```
   Record this as `Turn(turn_index=0, ...)`.
3. **Loop turns 1..max_turns** as the persona:

   For each turn `i` until terminated:

   a. Build the persona invocation context per the contract in
      `prompts/persona_archetypes.md` "What the qa-agent skill provides
      each turn":
      - `archetype` = scenario.persona_ref (look up the archetype block in
        the persona prompt and use it as the persona's system prompt for
        this turn)
      - `scenario.intent`, `scenario.success_criteria_summary` (extract
        only the `description` strings from each criterion)
      - `scenario.max_turns`, `turns_remaining = scenario.max_turns - i`
      - `client.tone` from canonical
      - `history` = full conversation so far

   b. Generate the persona's next user message. Apply the hard rules in
      the persona prompt. The output is a single string ≤ length cap.

   c. Check stop conditions **before sending**:
      - If the persona's output is a closer (per Hard rule 5/6) AND ALF's
        last reply satisfies a success criterion → terminate as
        `completed`. (Persona inference cost is acceptable here — running
        one extra inference per scenario is much cheaper than a wasted
        full turn round-trip.)
      - If the persona's output is a closer because `turns_remaining ≤ 1`
        → terminate as `max_turns`.
      - **Before invoking the persona**, scan ALF's last reply for an
        explicit handoff phrase (see "Termination decision" below). If
        matched, terminate as `escalated` immediately — skips persona
        inference entirely.

   d. Otherwise send + wait:
      ```python
      user_ts = time.time()
      await driver.send(persona_message)
      try:
          replies = await driver.wait_reply(timeout=60)
      except TimeoutError:
          terminated_reason = "timeout"
          break
      ```
      Record `Turn(turn_index=i, user_message=persona_message,
      user_ts=user_ts, alf_messages=replies, reply_latency_s=...)`.

   e. If reached `i == max_turns` and not terminated → terminate as
      `max_turns`.

4. **Close** the driver and **persist** the transcript:
   ```python
   await driver.close()
   transcript = Transcript(
       schema_version=SCHEMA_VERSION,
       run_id=run_id,
       scenario_id=scenario.id,
       started_at=...,
       ended_at=utcnow_iso(),
       terminated_reason=...,
       turns=turns,
       notes=f"welcome_messages={len(welcome)}",
   )
   append_transcript(run_id, transcript)
   ```

5. Brief progress log to the user every 5 scenarios:
   `"[N/total] scenario.id → terminated_reason"`.

### Phase 4 — Summarize

After all scenarios complete:

1. Re-read `transcripts.jsonl` via `tools.result_store.read_transcripts()`.
2. Compute and report:
   - Total scenarios executed: `<n>`
   - Distribution of `terminated_reason` (count per reason)
   - Average turns per scenario
   - Average `reply_latency_s` per turn (excluding nulls)
3. Tell the user the next step: "scoring-agent을 돌리려면 run_id
   `<run_id>`를 사용하세요" (scoring-agent is a separate skill).

### Phase 5 — Score (3단계 투명 지표)

**Reads**: `scenarios.json`, `transcripts.jsonl`, `config_snapshot.json`
**Writes**: `scores.json`, `report.md`
**Tool**: `tools.scoring_agent`

**v2 핵심 개선**:
- ❌ **기존 버그**: engaged=False(즉시 에스컬레이션)도 관여율에 포함 → 과대 계상
- ✅ **수정**: engaged=True만 계산 → 정확한 측정
- ✅ **3단계 분리**: scenario_coverage × alf_engagement_rate × alf_resolution_rate

Steps:
1. Ensure `config_snapshot.json`에 아래 필드가 있는지 확인:
   - `extra.total_records` — sop-agent pipeline_summary 또는 patterns.json에서 추출
   - `extra.noise_rate` — OOS 비율 (기본값: 0.1284 for 벨리에)
   - `extra.intent_pattern_coverage` — 각 intent의 패턴별 볼륨 가중 커버리지 비율
   
   이 필드들이 없으면 직접 산출하여 config_snapshot에 추가:
   
   ```
   noise_rate 산출:
   - patterns.json metadata.noise_clusters 개수 / total_clusters
   
   intent_pattern_coverage 산출:
   1. patterns.json에서 각 클러스터의 패턴 frequency × cluster_size = projected volume
   2. 클러스터를 canonical intent에 매핑
   3. 각 intent 내에서: 시나리오가 커버하는 패턴의 projected volume 합 / 전체 projected volume 합
   ```

2. Invoke scoring_agent:
   ```bash
   uv run python -m tools.scoring_agent --run-id <run_id>
   ```

3. 산출물 확인:
   - `scores.json` — per-scenario 판정 + run-level aggregate (**3단계 지표 포함**)
   - `report.md` — 내부 상세 리포트 (시나리오별 criterion pass/fail + 3단계 지표 표)

4. **3단계 지표 핵심 수치**를 사용자에게 보고:
   ```
   1️⃣ scenario_coverage (시나리오 커버리지):
      = Σ(effective_weight) / (1 - noise_rate)
      → 이 시나리오 세트가 실제 상담의 몇 %를 대변하는가?
   
   2️⃣ alf_engagement_rate (ALF 실질 관여율):
      = Σ(engaged=True의 effective_weight) / Σ(effective_weight)
      → 대변하는 상담 중 ALF가 실질적 답변을 시도한 비율 (즉시 에스컬레이션 제외)
   
   3️⃣ alf_resolution_rate (ALF 해결률):
      = Σ(resolved=True의 effective_weight) / Σ(engaged=True의 effective_weight)
      → 답변을 시도한 것 중 성공 기준을 통과한 비율
   
   ✅ actual_coverage (최종 자동화 커버리지):
      = scenario_coverage × alf_engagement_rate × alf_resolution_rate
      → 실제 월간 자동화 가능 비율
   ```

5. **추가 인사이트**:
   - **Phase 1/2 split**: Phase 1 (RAG 즉시) vs Phase 2 (Task 배포 후) 커버리지 분리 측정
   - **경쟁사 봇 대비 비교** (gl_bot_baseline 있는 경우):
     - 경쟁사 봇 해결률 (gl_resolution) vs ALF 해결률 → ×N배 개선 지표
   - **인텐트별 상세**: 각 인텐트의 engagement_rate, resolution_rate, actual_coverage
   - **난이도별 해결률**: Happy/Edge/Unhappy 각각의 해결률
   - **failure_mode 분포**: not_engaged, judge_fail, timeout 등

6. **월간 예측** (config_snapshot.extra.total_records 기반):
   ```
   총 월간 상담:           837건 (예시)
   유효 상담 (OOS 제외):   729건
   시나리오 커버 범위:     729건 (scenario_coverage = 100%)
   ALF 답변 시도:          621건 (alf_engagement_rate = 85%)
   ✅ ALF 자동 해결:       440건 (alf_resolution_rate = 71%)
   ⏭️  매니저 에스컬레이션: 397건
   ```

### Phase 6 — Client report

**Reads**: Phase 5 산출물 + sop-agent implementation guide
**Writes**: `report_client.md`, `report_slides.html`
**Prompt**: `prompts/generate_client_report.md`

Steps:
1. 경쟁사 봇 baseline 산출 (`is_competitor_bot=true`인 경우):

   **1차 소스**: `<sop_results_dir>/*_alf_implementation_guide.md`가 있으면
   여기서 경쟁사 봇 이름, 실질 해결률, 사전 예측치 추출.
   
   **2차 소스 (implementation guide 없을 때)**: sop-agent 데이터에서 직접 산출.
   경쟁사 봇(GL 등)은 상담 데이터에 "일반 봇 자동응답"으로 나타남:
   
   ```
   경쟁사 봇 baseline 산출 방법:
   
   a. patterns.json → response_flow 확인 (e.g. "bot(자동응답) → manager")
      → "bot" 단계가 존재하면 경쟁사 봇 작동 중으로 판단
   
   b. 클러스터 중 category="CS_자동응답" 또는 label에 "담당자 연결 대기",
      "자동응답" 포함된 클러스터 = 봇이 해결 못하고 상담사로 넘긴 건
   
   c. 경쟁사 봇 해결률 추정:
      - 전체 상담 중 봇이 "실질적으로 해결"한 비율
      - 일반적으로 GL 같은 rule-based 봇은 단순 FAQ 매칭만 수행
      - 추정 공식: (CS_자동응답 클러스터 중 봇이 최종 응답한 건수)
                   / 전체 상담 건수
      - 보수적 추정: 대부분 10~15% 범위 (봇이 인사 + 라우팅만 하고
        실질 해결은 거의 못 함)
   
   d. pipeline_summary.md에서 월간 추정 건수 추출
   ```
   
   `is_competitor_bot=false`면: 경쟁사 비교 섹션 전체 생략.
   "신규 ALF 도입" 프레이밍으로 리포트 작성 (×N배 대신 절대 수치 중심).

2. `prompts/generate_client_report.md`를 따라 report_client.md 생성:
   - 경쟁사 대비 비교 (×N배) — 첫 번째로 보이는 수치
   - 현재 처리 영역 + 실제 대화 사례
   - 개선 포인트 (rag_miss 기반)
   - Phase별 로드맵 + 예측 수치
   - 모든 % 수치는 월간 건수로도 환산

3. report_slides.html 생성:
   - 다크 테마, 10장 슬라이드, 좌우 화살표 네비게이션
   - `prompts/generate_client_report.md`의 "슬라이드 구조" 섹션 준수
   - 대화 예시: transcripts.jsonl에서 unhappy + completed + resolved 시나리오 1건 발췌
   - "ALF 도입 즉시" 표현 사용 (not "ALF 현재")

4. 사용자에게 report_slides.html 경로 안내 (브라우저에서 바로 열기).

---

## Termination decision (Phase 3 step 3.c)

Centralized rules — keep these consistent across scenarios for the run to
be comparable.

| Condition | terminated_reason |
|---|---|
| Success criterion satisfied AND persona acknowledges close | `completed` |
| `turns_remaining ≤ 1` AND no resolution | `max_turns` |
| `wait_reply` raised TimeoutError | `timeout` |
| ALF reply contains explicit handoff phrase | `escalated` |
| Driver raised any other exception | `error` |
| User Ctrl+C'd or skill aborted mid-scenario | `user_ended` |

**Handoff phrase detection** — look in the **last** ALF message only
(not the full turn) for **co-occurrence** of these tokens within ~30 chars
of each other:
- `"상담사"` + (`"연결"` OR `"전환"` OR `"바꿔"`)
- `"담당자"` + (`"전달"` OR `"연결"` OR `"확인 후"`)
- `"운영시간"` + (`"메시지"` AND ALF's reply also acknowledges the
  customer's request was *not* fulfilled — this guards against the false
  positive of standard sign-offs that mention business hours)

Avoid matching on `"상담사"` alone — many channels include it in welcome
or closing text without escalating. This is a heuristic; scoring-agent
will re-examine and may flip the label.

**Success criterion satisfaction** — for each criterion in the scenario,
check if it appears satisfied in ALF's recent replies:
- `llm_judge`: do a quick semantic match — does ALF's last 1-2 messages
  cover the criterion's `description`?
- `task_called`: check if any of `args.expected_signals` appears verbatim
  in ALF's recent replies.
- `regex_match` / `exact_match`: apply directly.

The orchestrator's termination check is intentionally lenient — false
positives end conversations early but final scoring happens in
scoring-agent. Better to over-terminate (and let scoring downgrade) than
to spin to max_turns on every scenario.

---

## Error handling

| Failure | Action |
|---|---|
| `chat_driver.open()` fails (page won't load, no contact button) | Mark scenario `error`, persist what you have, continue with next scenario |
| `wait_reply()` timeout | Per rules above: `terminated_reason: timeout` |
| Persona output > char cap | Truncate at cap, append `…`; do not retry |
| Persona output contains markdown / multiple messages separated by blank lines | Take the first non-blank line stripped of markdown markers (`-`, `*`, `#`, code fences); do not retry |
| Persona output is empty or only whitespace | Retry once with same context. If still empty, terminate scenario as `error` with note `"persona produced empty output twice"` |
| Persona output is meta commentary ("As a test customer…") | Retry once with explicit reminder of Hard rule 1. If still meta, terminate as `error` |
| ALF banned / rate-limited (we observe blocking patterns) | Stop the entire run; persist transcripts so far; tell user |
| Disk write fails | Retry once; if still fails, abort run with diagnostic |

Do not silently swallow errors. Every per-scenario failure must appear in
the transcript's `notes` field.

---

## Replay mode (lightweight)

If the user invokes the skill with an existing `run_id`, **skip Phase 1
and 2** and re-run only Phase 3-4 by invoking `tools.scenario_runner`
against the existing `scenarios.json`.

Output handling for replay:
- Default: write to a sibling file `transcripts.<replay_ts>.jsonl` so the
  original `transcripts.jsonl` is preserved. (The runner currently appends
  to the canonical `transcripts.jsonl`; for replay, rename the existing
  file before re-running.)
- If the user explicitly opts to overwrite, delete the old file first
  and confirm.

Replay is the canonical way to compare "same scenarios, different ALF
settings" — preserves Rule-7 (scenario ID stability) and Rule-3
(reproducible OOS messages) from `prompts/generate_scenarios.md`.

---

## What this skill does **not** do

- Does not generate sop-agent results. That is `sop-agent` (external repo).
- Does not modify the ALF channel settings. Read-only consumer.
- Does not run scenarios in parallel. v0 is sequential — parallelism is a
  v1 concern that requires per-scenario `BrowserContext` isolation (the
  driver supports it, but the orchestrator does not exploit it yet).
- Does not delete or overwrite previous runs. Each run gets its own
  `run_id` directory.
- Does not fabricate or inflate client report 수치 — scores.json 실측 기반만 사용.

---

## Python dependencies (in pyproject.toml)

| Package | Purpose |
|---|---|
| `playwright` | browser automation in `chat_driver` |
| `anthropic` | Claude API for persona inference in `scenario_runner` |
| `python-dotenv` | load `ANTHROPIC_API_KEY` from repo-root `.env` |
| `pyyaml` | parse `canonical_input.yaml` in Phases 2-3 |
| `pydantic-settings` | future config loader (not yet used) |
| `python-json-logger` | structured logging (not yet wired) |

`ANTHROPIC_API_KEY` must be set in the user's environment or a `.env` file
at the repo root. Each part-timer using the skill needs their own key
(typically the company-issued Prism Gateway key).

LLM access defaults to Channel.io's Prism Gateway (`https://prism.ch.dev`).
Override via `LLM_BASE_URL` env var if pointing at direct Anthropic.
Model defaults to `anthropic/claude-sonnet-4-6`; override via `PERSONA_MODEL`.

---

## Quick reference — Python tools used

| Tool | Purpose |
|---|---|
| `tools.result_store.new_run_id()` | generate run_id |
| `tools.result_store.run_dir(run_id)` | create run directory |
| `tools.result_store.write_config_snapshot()` | persist phase 2.1 |
| `tools.result_store.write_scenarios()` | persist phase 2.2 |
| `tools.result_store.append_transcript()` | persist each transcript in phase 3 |
| `tools.result_store.read_transcripts()` | for phase 4 summary |
| `tools.chat_driver.PlaywrightDriver` | open / send / wait_reply / close |
| `tools.chat_driver.AlfMessage` | shape of ALF message returned by driver |
| `tools.scenario_runner` (CLI) | Phase 3 execution; invoke as subprocess |
| `tools.scoring_agent` (CLI) | Phase 5 scoring; invoke as subprocess |
| `prompts/generate_client_report.md` | Phase 6 client report generation instructions |

All other tools live outside this skill. Do not invent new tool calls.

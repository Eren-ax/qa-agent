---
name: qa-agent
description: Generate QA scenarios from sop-agent analysis + current channel settings, drive turn-by-turn dialogue with ALF on a test channel, and persist v0-schema run artifacts (config_snapshot.json, scenarios.json, transcripts.jsonl) under storage/runs/<run_id>/ for downstream scoring.
---

# qa-agent — Orchestration Spec

You are the **qa-agent orchestrator**. Your job is to take a test channel URL
and a sop-agent results directory, then produce a complete v0-schema run
under `storage/runs/<run_id>/`.

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
| `sop_results_dir` | ask the user; example: `~/sop-agent/results/<client>/` |
| `alf_task_json_path` | optional; ask "ALF 태스크 JSON 있으세요?" — if not, fallback to `<sop_results_dir>/04_tasks/*.md` |
| `target_total` | optional; default **25** |
| `headed` | optional; default **false** (headless). Use `true` only for debugging. |

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
└── transcripts.jsonl         # phase 3 output, one line per scenario
```

Where `<run_id>` comes from `tools.result_store.new_run_id()`.

After completion, return to the user:
- The run_id
- The output directory path
- A 3-line summary (count of scenarios executed, average turns, distribution
  of `terminated_reason`)

---

## Implementation status

All four phases are implementable today.

| Phase | Implementation |
|---|---|
| 1. Normalize | apply `prompts/normalize_sop.md`, persist YAML |
| 2. Snapshot + generate | apply `prompts/generate_scenarios.md`, write via `tools.result_store` |
| 3. Execute | invoke `tools.scenario_runner` (Anthropic SDK + PlaywrightDriver) |
| 4. Summarize | read via `tools.result_store.read_transcripts` |

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
        "alf_task_json": alf_task_json_path,
        "target_total": target_total,
        "rules_source_gap": "v0: rule extraction not implemented; rules_summary intentionally empty",
    },
)
```

**Phase 2.2 — scenarios.json**

**Writes**: `storage/runs/<run_id>/scenarios.json`
**Prompt**: `prompts/generate_scenarios.md`
**Tool**: `tools.result_store.write_scenarios()`

Steps:
1. Apply `generate_scenarios.md` with three explicit context blocks:
   - `canonical`: the full canonical YAML from Phase 1.
   - `personas`: the **persona archetype catalog table** (the markdown
     table near the top of `persona_archetypes.md` listing
     `persona_ref / one-liner / recommended share`). This is sufficient —
     do not pass full archetype bodies, the prompt only needs names +
     shares for distribution rules.
   - `target_total`: the integer.
2. The prompt emits raw JSON. Parse and validate against `ScenarioSet`
   dataclass: every scenario must satisfy the v0 schema (all required
   fields, valid persona_ref ∈ five-archetype pool, success_criteria
   non-empty, IDs unique).
3. **If validation fails**, re-invoke the prompt once with the validation
   error appended as feedback. If it fails twice, stop and report.
4. Persist via `write_scenarios(run_id, scenario_set)`.

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

Do **not** attempt to score in this skill. Phases 1-4 produce raw
artifacts only.

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

- Does not score or label transcripts. That is `scoring-agent`.
- Does not generate sop-agent results. That is `sop-agent` (external repo).
- Does not modify the ALF channel settings. Read-only consumer.
- Does not run scenarios in parallel. v0 is sequential — parallelism is a
  v1 concern that requires per-scenario `BrowserContext` isolation (the
  driver supports it, but the orchestrator does not exploit it yet).
- Does not delete or overwrite previous runs. Each run gets its own
  `run_id` directory.

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

All other tools live outside this skill. Do not invent new tool calls.

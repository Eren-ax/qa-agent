# Prompt: Normalize sop-agent Output → qa-agent Canonical Input

You are the **input normalizer** for qa-agent. Your job is to take a sop-agent
results directory (+ optionally a Channel.io ALF task JSON file) and produce
a single canonical YAML document that downstream prompts (scenario generation,
judging) will consume.

Do this and nothing else. Do not invent facts. Do not add scenarios.

---

## Inputs you receive

The caller will give you **paths to one or more of the following**. Some may
be missing — handle gracefully.

| Input | Required | Purpose |
|---|---|---|
| `<sop_results_dir>/pipeline_summary.md` | recommended | overall volume + automation priorities |
| `<sop_results_dir>/03_sop/metadata.json` | **required** | list of SOPs with topic + records count |
| `<sop_results_dir>/02_extraction/faq.json` | **required** | topic-grouped Q/A seeds |
| `<sop_results_dir>/02_extraction/patterns.json` | **required** | clusters, company_tone, escalation hints, **GL bot baseline (Gap 1)**, escalation_triggers |
| `<sop_results_dir>/02_extraction/keywords.json` | optional | taxonomy for intent naming |
| `<sop_results_dir>/05_sales_report/analysis/automation_analysis.md` | recommended | **4-Layer model (Gap 2)** — RAG/Task/Hybrid/Human breakdown |
| `<sop_results_dir>/04_tasks_json/TASK*.json` | **recommended** | ALF Task JSON (채널톡 업로드 가능 형식) |
| `<sop_results_dir>/04_tasks/TASK*.md` | fallback | Mermaid flowcharts if task JSON unavailable |

**Task source priority**: `04_tasks_json/*.json` (primary) → `04_tasks/*.md` (fallback).
The JSON files are production-ready and match the ALF upload format exactly.

**Breaking change (sop-agent v2)**: `response_strategies.json` is **removed**.
Escalation triggers are now embedded in `patterns.json → clusters[].patterns[].escalation_triggers`.

---

## Output: canonical YAML

Emit a single YAML document with the top-level keys below. Use Korean strings
verbatim where the source is Korean. Do **not** paraphrase customer utterances
from FAQ — they are scenario seeds and must stay authentic.

```yaml
schema_version: v0

client:
  name: <string>                    # from pipeline_summary or metadata
  industry: <string>                # from metadata.industry if present, else ""
  tone:
    greeting: <string>              # patterns.company_tone.greeting
    closing: <string>               # patterns.company_tone.closing
    empathy_expressions: [<string>]
    response_flow: <string>         # e.g. "bot → manager → manager"
    brand_identity: <string>
  stats:
    total_records: <int>            # source of truth for volume_weight math
    extraction_date: <string>
  gl_bot_context:                   # from patterns.json → metadata.analysis_context (Gap 1)
    competitor: <string | null>     # e.g. "GL"
    gl_bot_status: <string | null>  # e.g. "active (personId=632346)"
    gl_bot_involvement: <string | null>       # e.g. "68.8% of chats (1864/2711)"
    gl_bot_escalation_rate: <string | null>   # e.g. "88.1%"
    gl_bot_real_resolution_rate: <string | null> # e.g. "3.5% (95/2711 chats)"
    gl_bot_read_task_execution: <string | null>  # e.g. "2.79% (52/1864 GL-involved chats)"
    gl_bot_write_task_execution: <string | null> # e.g. "1건 (배송지 변경 only)"
    gl_bot_behavior: <string | null>  # e.g. "greeting → info collection → manager escalation"

intents:                            # ONE entry per SOP topic in metadata.json
                                    # Order: ascending by `sop_file` filename for determinism.
  - id: <snake_case>                # primary: lowercased FAQ key (HT_FOO → ht_foo). See rules below.
    label: <string>                 # Korean topic label, e.g. "주문 취소 및 반품 처리"
    sop_file: <filename>            # HT_구매결제_주문취소및반품.sop.md
    sop_type: HT | TS               # from filename or metadata
    records: <int>                  # metadata.sop_files[i].records
    volume_weight: <float>          # records / client.stats.total_records (rounded to 3 decimals)
    automation_ready: <bool>        # uppercase(id) ∈ metadata.coverage.automation_ready
    phase_hint: <string>            # "rag" | "task" | "hybrid" | "human" — from automation_analysis.md (Gap 2)
    faqs:                           # from faq.json[faq_by_topic][<MATCHING_KEY>], may be []
      - q: <string>                 # verbatim
        a: <string>                 # verbatim
    patterns:                       # from patterns.json clusters matched to this intent
      - name: <string>              # pattern name, e.g. "재입고 일정 문의"
        type: <string>              # 정보_요청 | 프로세스_문의 | 문제_신고
        frequency: <int>            # sample frequency from extraction (relative within cluster)
        common_phrases: [<string>]  # verbatim customer utterances — scenario seed candidates
    escalation_triggers: [<string>] # **removed in sop-agent v2** — set to [] unless legacy response_strategies.json present
    automation_opportunity: <string> # **removed in sop-agent v2** — set to "" unless legacy response_strategies.json present
    key_info: [<string>]            # **removed in sop-agent v2** — set to [] unless legacy response_strategies.json present

tasks:                              # from ALF task JSON (primary) OR 04_tasks/*.md (fallback)
  - id: <string>                    # from JSON `id` field, or filename stem for MD fallback
    name: <string>                  # human-readable name
    triggers: [<string>]            # example user utterances that should fire the task
    external_admin_required: <bool> # true iff the task calls external APIs (카페24, EZ어드민, etc.)
    branches:                       # expected decision points
      - label: <string>             # e.g. "사유=단순 변심"
        outcome: resolves_in_alf | escalates_to_human | errors_out
    intents_linked: [<intent_id>]   # which canonical intents this task serves (best-effort match)
    source: alf_task_json | markdown_flowchart

out_of_scope_hints:                 # used to seed OOS scenarios (10-20% of total)
  noise_cluster_examples: [<string>]  # from pipeline_summary or patterns noise_clusters, if described
  common_sense_traps: [<string>]      # optional: distractor questions to test refusal behavior

generation_metadata:
  normalized_from:
    sop_results_dir: <string | null>
    alf_task_json: <string | null>
    fallback_task_md_dir: <string | null>
  normalized_at: <ISO8601 UTC>
  notes: [<string>]                 # list of warnings/decisions, one per item, may be []
```

### YAML safety
- Quote any string that contains `:`, `#`, `[`, `]`, `{`, `}`, `&`, `*`,
  `?`, `|`, `>`, `!`, `%`, `@`, leading/trailing whitespace, or could be
  parsed as bool/null/number (e.g. `"yes"`, `"1234"`).
- Korean Q/A from FAQ frequently contains `:` — when in doubt, double-quote.
- For multi-line text, prefer YAML block scalars (`|` for literal,
  `>-` for folded-stripped) over `\n` escapes.

---

## Normalization rules (how to derive each field)

### `intents[].id` (deterministic — no LLM judgment)
- **Primary source**: `faq.json[faq_by_topic]` keys are already English
  snake_case-shaped (e.g. `HT_ORDER_CANCEL_RETURN`). Lowercase them →
  `ht_order_cancel_return`. Use this as `id`.
- **Fallback** (no FAQ key for this SOP): use the SOP filename stem with
  Korean preserved, lowercased, dots/underscores normalized
  (e.g. `HT_구매결제_주문취소및반품.sop.md` → `ht_구매결제_주문취소및반품`).
- **Stable ordering**: process SOPs in ascending order by `sop_file`
  filename before assigning IDs. This guarantees collision suffixes are
  reproducible across runs.
- **IDs must be unique.** On collision, append `_2`, `_3`, … to the *later*
  occurrence in the sorted order (the first occurrence keeps the bare ID).
  Add an entry to `notes` for every collision.

### `intents[].automation_ready`
- Set `true` iff `uppercase(intents[].id)` exactly matches an item in
  `metadata.coverage.automation_ready`.
- If `metadata.coverage.automation_ready` is missing or empty, set all
  intents to `false` and add a single note: `"automation_ready: source field
  missing, defaulting all to false"`.

### `intents[].volume_weight`
- Compute as `records / client.stats.total_records` to 3 decimals, where
  `total_records` is the **raw** total from `pipeline_summary.md` /
  `metadata.json` (noise included).
- Sum across all intents will be < 1.0 by approximately the noise rate
  (e.g. ~0.94 if noise = 6%). This is expected and intentional — the gap
  represents traffic that should *not* be tested (spam, blank messages).
  Do not normalize the weights to sum to 1.

### `intents[].faqs` (deterministic match first)
- **Step 1 — exact key match**: For each SOP in `metadata.sop_files`, derive
  the expected FAQ key by uppercasing the intent id (e.g.
  `ht_order_cancel_return` → `HT_ORDER_CANCEL_RETURN`) and look it up in
  `faq.json.faq_by_topic`. If found, copy all Q/A pairs **verbatim**.
- **Step 2 — fuzzy fallback**: Only if exact match fails, attempt semantic
  matching against unused FAQ keys. Tie-breaker rules in order:
  (a) prefer the key sharing the same `HT_`/`TS_` prefix as the SOP type;
  (b) prefer the key with the highest token overlap against the SOP topic
      label (`metadata.sop_files[i].topic`);
  (c) if still tied, pick the alphabetically first remaining key.
  Always record the chosen key + reasoning in `notes`. **An FAQ key may be
  used by at most one intent** — once consumed, remove it from the pool.
- **Step 3 — no match**: Emit `faqs: []` for that intent and add an
  explicit warning in `notes` (e.g. `"intent ht_xxx: no FAQ pairs found"`).
  Scenario generation will treat empty-FAQ intents as low-confidence.
- **Never paraphrase Q/A.** Customer utterances are scenario seeds and must
  preserve original phrasing, typos, casual tone, and formatting.

### `intents[].patterns` (from patterns.json clusters)
- **Matching logic**: each cluster in `patterns.json.clusters` maps to an
  intent. Use the same key-matching strategy as FAQ: cluster `category` +
  `label` → intent `id` / `label`. Multiple clusters can map to one intent
  (e.g. "데님 팬츠 문의" and "재입고 문의" both map to the same intent if the
  SOP groups them). Merge patterns from all matched clusters.
- **Fields**: copy each pattern's `name`, `type`, `frequency`, and
  `common_phrases` verbatim. Do not paraphrase `common_phrases` — they are
  real customer utterances and serve as scenario seeds.
- **Ordering**: sort patterns by `frequency` descending within each intent.
- **Missing clusters**: if no cluster matches an intent, set `patterns: []`
  and add a note.
- **Noise clusters** (listed in `patterns.json.metadata.noise_clusters`):
  skip entirely — they do not map to intents. Their content feeds
  `out_of_scope_hints` instead.

### `intents[].phase_hint` (Gap 2: Phase 1/2 분리 scoring)
- **Source (sop-agent v2)**: `05_sales_report/analysis/automation_analysis.md` 4-Layer 모델
- **Layer mapping**:
  - **Layer 1 (RAG)** → `"rag"`: FAQ/정보 요청만으로 해결 (외부 API 불필요)
  - **Layer 2 (Task)** → `"task"`: API 연동 기반 프로세스 (주문조회/취소/반품)
  - **Layer 3 (Hybrid)** → `"hybrid"`: RAG+Task 복합 (정보 안내 후 API 호출)
  - **Layer 4 (Human)** → `"human"`: Manager escalation 필수
- **추출 방법**:
  1. Read `05_sales_report/analysis/automation_analysis.md`
  2. Parse each Layer's "대상 문의 유형" + table (SOP 토픽 리스트)
  3. Match current intent's `label` or `sop_file` against Layer items
  4. Multiple Layer 분류 시 (예: 재입고 Layer 1 90% + Layer 3 10%):
     - Select Layer with highest weight as `phase_hint`
     - Add note: `"intent <id>: phase_hint=rag (90%), but 10% classified as hybrid"`
  5. No match → default `"rag"` + note: `"intent <id>: phase_hint not found, defaulting to rag"`
- **Missing file**: All intents get `phase_hint: null` + single note: `"automation_analysis.md not found, phase_hint unavailable for all intents"`

### `client.gl_bot_context` (Gap 1: GL baseline 비교)
- **Source**: `patterns.json → metadata.analysis_context`
- **필드 추출**: 아래 키를 verbatim 복사 (누락 시 `null`):
  - `competitor` — 경쟁 봇 이름 (e.g. "GL")
  - `gl_bot_status` — 상태 (e.g. "active (personId=632346)")
  - `gl_bot_involvement` — 개입률 (e.g. "68.8% of chats (1864/2711)")
  - `gl_bot_escalation_rate` — 에스컬레이션률 (e.g. "88.1%")
  - `gl_bot_real_resolution_rate` — 실질 해결률 (e.g. "3.5% (95/2711 chats)")
  - `gl_bot_read_task_execution` — Read Task 수행률 (e.g. "2.79% (52/1864 GL-involved chats)")
  - `gl_bot_write_task_execution` — Write Task 수행률 (e.g. "1건 (배송지 변경 only)")
  - `gl_bot_behavior` — 행동 패턴 (e.g. "greeting → info collection → manager escalation")
- **Missing `analysis_context`**: `gl_bot_context`의 모든 필드를 `null`로 설정
- **None 허용**: GL 고객사가 아닌 경우 모든 필드 `null`은 정상

### `intents[].escalation_triggers` / `automation_opportunity` / `key_info` (legacy fields)
**Breaking change (sop-agent v2)**: These fields are **no longer generated** by sop-agent.
They existed in `response_strategies.json` which has been removed.

**Action**:
- Set all three fields to empty (`[]` for lists, `""` for strings) by default.
- **Legacy fallback (sop-agent v1)**: If `response_strategies.json` exists in the input directory,
  copy from `strategies_by_topic[<matching_topic>]`.
  - `escalation_triggers`: list of strings
  - `automation_opportunity`: single string
  - `key_info`: list of strings
  - Topic key matches the FAQ key (uppercase form).
- Add a single note if legacy file is present: `"escalation_triggers/automation_opportunity/key_info: sourced from legacy response_strategies.json (sop-agent v1)"`
- Add no note if all fields are empty (v2 is the new default).

### Task JSON shape

**Primary source (sop-agent v2)**: `04_tasks_json/TASK*.json` — production-ready ALF Task JSON.
These files match the exact Channel.io ALF upload format.

**Shape (sop-agent v2)**:
```json
{
  "task": {
    "name": "<string>",           // e.g. "벨리에 - 주문조회"
    "trigger": "<string>",        // multi-line prompt with [역할] + [트리거 조건] + examples
    "memorySchema": [...],        // ALF memory variables
    "nodes": [                    // ALF workflow nodes
      {
        "id": "node-N",
        "key": "A|B|C...",
        "name": "<node name>",
        "type": "agent | userChatInlineAction | appFunction | branch",
        "instruction": "<markdown instruction>",  // for type=agent
        "next": { "type": "goto|branch|end", "to": "node-X" | "conditions": [...] }
      }
    ]
  }
}
```

**Canonical extraction (sop-agent v2)**:
| Canonical field | JSON path | Notes |
|---|---|---|
| `id` | filename stem (e.g. `TASK1_주문조회.json` → `task1_주문조회`) | Derive from filename, lowercase |
| `name` | `task.name` | |
| `triggers` | Parse from `task.trigger` field — extract example utterances from the "문의 예시:" section | Split by `- ` lines |
| `external_admin_required` | Search `task.nodes[]` for any `type: "appFunction"` | `true` if found, else `false` |
| `branches` | Parse `task.nodes[]` for nodes with `type: "branch"` | Extract `conditions[].filter` logic → label + outcome |

**Legacy fallback (sop-agent v1 or user-supplied JSON)**: If JSON shape doesn't match above,
fall back to best-effort extraction using the field mappings from the old spec:
| Canonical field | Common JSON field names to look for |
|---|---|
| `id` | `id`, `task_id`, `slug`, or filename |
| `name` | `name`, `title`, `label` |
| `triggers` | `triggers`, `trigger_phrases`, `examples`, `utterances` |
| `external_admin_required` | `api`, `requires_api`, `external`, `admin_api` (truthy if any external system call is described) |
| `branches` | `branches`, `flow`, `decisions`, `cases`, or any list of conditional outcomes |

If a required field cannot be found, drop only that field. If `id` and
`name` are both missing, skip the task entirely and warn in `notes`.

**Empty triggers**: if `triggers` resolves to an empty list, the task cannot
seed scenarios. Keep the task entry (other tools may still use it) but add
a per-task warning to `notes`: `"task <id>: no triggers found, scenario
generation will skip task-coverage for it"`.

**Empty branches**: if `branches` resolves to empty, set `branches: []` and
add a per-task note. Scenario generation will only emit a single happy-path
scenario for that task.

### `tasks[].intents_linked`
- Best-effort match using trigger phrases + task name against
  `intents[].label` and `intents[].faqs[].q`.
- If ambiguous, include multiple; never silently drop.

### Task JSON examples (shape variation reference)

These are **fictional dummy tasks** for a fictional brand "샘플몰". They
illustrate two common shape variants the user-supplied JSON may take.
**Do not match field names by exact equality** to these examples — use them
to recognize shape patterns, then apply the field-mapping table above.

#### Example A — flat / shallow

Input JSON:
```json
{
  "id": "task_refund",
  "name": "반품 접수",
  "triggers": ["반품하고 싶어요", "환불 받고 싶어요"],
  "api": {"system": "샘플ERP", "endpoint": "/orders/return"},
  "branches": [
    {"label": "사유=단순 변심", "outcome": "complete"},
    {"label": "사유=불량",      "outcome": "escalate"},
    {"label": "API 오류",       "outcome": "error"}
  ]
}
```

Canonical output:
```yaml
- id: task_refund
  name: 반품 접수
  triggers: ["반품하고 싶어요", "환불 받고 싶어요"]
  external_admin_required: true
  branches:
    - label: "사유=단순 변심"
      outcome: resolves_in_alf
    - label: "사유=불량"
      outcome: escalates_to_human
    - label: "API 오류"
      outcome: errors_out
  intents_linked: [order_cancel_return]   # best-effort match
  source: alf_task_json
```

Mapping notes:
- `api` is non-empty → `external_admin_required: true`
- Outcome vocabulary mapping: `complete → resolves_in_alf`,
  `escalate → escalates_to_human`, `error → errors_out`

#### Example B — nested / verbose, different keys

Input JSON:
```json
{
  "task_id": "refund_v2",
  "title": "반품 처리 (개선)",
  "meta": {
    "user_inputs": {
      "examples": ["반품해주세요", "환불 가능한가요?"]
    },
    "requires_external_api": true
  },
  "decisions": [
    {"condition": "reason == 'change_of_mind'", "next": "process_refund"},
    {"condition": "reason == 'defect'",         "next": "handoff_human"}
  ]
}
```

Canonical output:
```yaml
- id: refund_v2
  name: 반품 처리 (개선)
  triggers: ["반품해주세요", "환불 가능한가요?"]
  external_admin_required: true
  branches:
    - label: "reason == 'change_of_mind'"
      outcome: resolves_in_alf
    - label: "reason == 'defect'"
      outcome: escalates_to_human
  intents_linked: [order_cancel_return]
  source: alf_task_json
```

Mapping notes:
- `task_id` → `id`, `title` → `name`
- `meta.user_inputs.examples` (deeply nested) → `triggers`
- `meta.requires_external_api` → `external_admin_required`
- `decisions[].next` is mapped to outcome by keyword:
  `process_refund / complete_xxx / fulfill_xxx → resolves_in_alf`,
  `handoff_human / escalate_xxx / transfer_xxx → escalates_to_human`,
  `error / fail / abort → errors_out`
- When the next-step name is unfamiliar, classify as `resolves_in_alf` and
  add a per-branch warning to `notes`.

### `tasks[].branches` (for Markdown fallback only)
- Parse the Mermaid flowchart's diamond/decision nodes.
- For each terminal node, classify:
  - If the node contains `상담사 연결` or synonymous text → `escalates_to_human`
  - If the node indicates successful completion (e.g. `완료 안내`, `종료`) → `resolves_in_alf`
  - Otherwise → `errors_out`
- Fall back to `resolves_in_alf` only when confident.

### `out_of_scope_hints` (when source data is sparse)
- `noise_cluster_examples`: prefer literal example phrases from
  `pipeline_summary.md` insights or `patterns.json` cluster descriptions.
  If neither contains usable example utterances, leave the list empty and
  add a note: `"out_of_scope_hints.noise_cluster_examples: source data did
  not surface concrete example phrases; scenario generation may add OOS
  seeds from its own knowledge"`.
- `common_sense_traps`: optional and almost never present in source. Leave
  empty by default; scenario generation owns this entirely.
- The whole `out_of_scope_hints` block is a **hint**, not a constraint —
  empty lists are acceptable.

### Missing inputs
- If `metadata.json` or `faq.json` is missing, **stop and report** instead of
  proceeding with partial data. Scenario generation with incomplete intents
  will silently under-cover.
- If only task MD (no JSON) is provided, set `source: markdown_flowchart` and
  add a `notes` warning that task definitions may be stale.
- If neither task JSON nor task MD is available, emit `tasks: []` and warn
  loudly in `notes` — scenario generation will skip task-coverage rules.

---

## Output constraints

- Emit **YAML only** — no surrounding prose, no code fence when invoked by the
  skill (the caller will persist raw to `storage/runs/<run_id>/canonical_input.yaml`).
- UTF-8. Do not escape Korean characters.
- Comments are allowed but keep them terse.
- If anything in the source is ambiguous, prefer **dropping the ambiguous
  field** over guessing. Guesses propagate into scoring errors.

---

## Dummy example (shape only, not content)

```yaml
schema_version: v0
client:
  name: 샘플몰
  industry: 잡화
  tone:
    greeting: "안녕하세요, 샘플몰입니다."
    closing: "감사합니다."
    empathy_expressions: ["불편드려 죄송합니다"]
    response_flow: "bot → manager"
    brand_identity: "샘플 브랜드 아이덴티티"
  stats:
    total_records: 1000
    extraction_date: "2026-04-01"

intents:
  - id: order_cancel_return
    label: "주문 취소 및 반품"
    sop_file: HT_주문취소및반품.sop.md
    sop_type: HT
    records: 200
    volume_weight: 0.200
    automation_ready: true
    faqs:
      - q: "반품하고 싶어요"
        a: "반품 신청 도와드리겠습니다. 주문번호 알려주세요."
    patterns:
      - name: 반품 진행 상태 확인
        type: 프로세스_문의
        frequency: 6
        common_phrases:
          - "반품완료 언제 되나요?"
          - "환불처리 되나요?"
      - name: 반품 수거 요청
        type: 프로세스_문의
        frequency: 5
        common_phrases:
          - "택배 회수접수 해주실수있을까요?"
          - "반품 회수가 안되어 재요청"
      - name: 반품 부분 취소/철회
        type: 프로세스_문의
        frequency: 3
        common_phrases:
          - "셋다 반품을 걸어버렸어요 하나만 반품취소 해주세요"
    escalation_triggers:
      - "불량 사유로 반품 요청"
    automation_opportunity: "주문번호 기반 반품 API 연동"
    key_info:
      - "수령 후 7일 이내, 미착용 조건"

tasks:
  - id: task_refund
    name: 반품 접수
    triggers: ["반품하고 싶어요", "환불 받고 싶어요"]
    external_admin_required: true
    branches:
      - label: "사유=단순 변심"
        outcome: resolves_in_alf
      - label: "사유=불량"
        outcome: escalates_to_human
    intents_linked: [order_cancel_return]
    source: alf_task_json

out_of_scope_hints:
  noise_cluster_examples:
    - "감사합니다"
    - "수고하세요"
  common_sense_traps:
    - "아프리카 코끼리 평균 수명은?"

generation_metadata:
  normalized_from:
    sop_results_dir: /path/to/sop-results
    alf_task_json: /path/to/tasks.json
    fallback_task_md_dir: null
  normalized_at: "2026-04-13T07:30:00+00:00"
  notes:
    - "all topics matched cleanly; no ambiguity"
```

---

## What this normalizer does **not** do

- Does not invent scenarios. Scenario generation is a separate prompt.
- Does not assign personas. Personas are separate.
- Does not filter OOS entries — it only surfaces hints that later prompts use.
- Does not judge anything. All semantic/quality judgments belong to
  scoring-agent.

Keep this step mechanical. If it is ever tempted to be creative, stop —
ambiguity should be surfaced in `notes`, not papered over.

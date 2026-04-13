# Prompt: Generate QA Scenarios from Canonical Input

You are the **scenario generator** for qa-agent. You take the canonical YAML
produced by `prompts/normalize_sop.md` (plus the fixed persona pool from
`prompts/persona_archetypes.md`) and produce a **scenario set** that
covers the channel's settings systematically.

The scenario set drives every subsequent step: drivers execute it, scoring
labels it, reports aggregate it. **Coverage gaps here cause silent
under-measurement everywhere downstream.** This is the single most
consequential prompt in qa-agent.

---

## Inputs

| Input | Source |
|---|---|
| `canonical` | YAML output of `prompts/normalize_sop.md` |
| `personas` | the fixed pool from `prompts/persona_archetypes.md` |
| `target_total` | integer; total scenario count target (default: 25) |

---

## Output

A JSON document matching the `ScenarioSet` shape used by
`tools/result_store.py`. The qa-agent skill persists it as
`storage/runs/<run_id>/scenarios.json`.

```json
{
  "schema_version": "v0",
  "run_id": "<provided by skill>",
  "scenarios": [
    {
      "id": "<intent_id>.<kind>.<seq>",
      "intent": "<Korean label from canonical.intents[].label>",
      "persona_ref": "<one of the five archetypes>",
      "initial_message": "<verbatim FAQ Q, OOS seed, or task trigger>",
      "success_criteria": [
        {
          "description": "<human-readable assertion>",
          "type": "llm_judge | regex_match | exact_match | task_called",
          "args": {}
        }
      ],
      "max_turns": <int>,
      "weight": <float>,
      "source": "sop-agent | manual | oos"
    }
  ],
  "generated_at": "<ISO8601 UTC>",
  "generation_note": "<prompt version + canonical hash + coverage summary>"
}
```

Emit **JSON only**, no prose. The skill writes the raw output to disk.

---

## Scenario taxonomy

Every scenario belongs to one **kind** (encoded in `id`):

| `kind` | When to emit | Typical max_turns |
|---|---|---|
| `happy` | the intent's most common path resolves cleanly via FAQ knowledge | 6 |
| `edge` | branch where automation_ready is `true` but the ask is harder (multi-product, ambiguous identifier, partial cancellation) | 8 |
| `escalation` | a branch in `tasks[].branches` whose `outcome: escalates_to_human` — ALF is **expected** to hand off | 4 |
| `oos` | out-of-scope question; ALF is **expected** to refuse politely | 3 |

`escalation` and `oos` are positive scenarios — passing means ALF correctly
escalated/refused. Do not treat them as failure cases.

---

## Coverage rules (mandatory)

These are the rules the self-verification step (below) checks against.
**Failing any of these means regenerate, do not ship.**

### Rule 1 — Volume-proportional intent coverage
- For each intent in `canonical.intents`, emit at least
  `max(2, round(volume_weight × target_total))` scenarios.
- Intents with `volume_weight ≥ 0.10` get ≥ 1 `happy` and ≥ 1 `edge`.
- Intents with `volume_weight < 0.10` may have only `happy` scenarios.
- **Empty-FAQ intents** (per canonical `notes`) emit exactly 1 placeholder
  `happy` scenario with `initial_message = canonical.intents[].label`
  used **literally as a statement** (no question rephrasing). E.g. label
  "주문 취소 및 반품 처리" → initial_message verbatim. Add a per-scenario
  entry in `generation_note`: `"<scenario.id>: empty-FAQ placeholder, label
  used as initial_message"`.

### Rule 2 — Task branch coverage
- For each task in `canonical.tasks` with non-empty `triggers`:
  - Emit 1 `happy` scenario seeded from the task's first trigger.
  - For each branch with `outcome: escalates_to_human`, emit 1 `escalation`
    scenario whose `initial_message` is constructed per Rule 5 (synthetic
    allowance applies).
- **Branches with `outcome: errors_out` are skipped.** They represent
  internal API/system failures that the customer cannot induce from the
  chat interface — there is no user utterance that reliably triggers them.
  Testing them requires driver-level fault injection, which is out of scope
  for v0.

### Rule 3 — OOS share
- OOS scenarios must be **10-20% of `target_total`**, rounded.
- Sources for OOS `initial_message` (use in this priority):
  1. `canonical.out_of_scope_hints.common_sense_traps` (preferred when
     present).
  2. `canonical.out_of_scope_hints.noise_cluster_examples` (if usable as
     full questions).
  3. Generic distractors you generate (general knowledge, current events,
     wholly unrelated tasks). When you generate, prefer **plausible-sounding
     domain-adjacent traps** ("이거 다른 회사에서 산 건데 환불돼요?") over
     obvious nonsense.
- **Reproducibility for generated OOS**: every synthetic OOS message must
  be listed in `generation_note` as `"oos.<seq>: synthetic — '<message>'"`.
  This is the human-readable seed list scoring/replay can re-use; on a
  rerun with the same canonical input, prefer reusing exact messages from
  the prior run's `generation_note` if available.

### Rule 4 — Persona distribution
- The ±10pp distribution check applies to the **non-pinned scenario subset
  only** — i.e. all `happy` and `edge` scenarios. Pinned subsets (OOS,
  escalation) follow their own pin rules below and do not contribute to the
  distribution comparison.
- For the non-pinned subset: match persona_archetypes recommended shares
  within **±10 percentage points** per archetype.
- **Pin (OOS)**: every `oos` scenario uses `polite_clear` (per persona
  prompt rule).
- **Pin (escalation)**: among `escalation` scenarios, `adversarial` +
  `impatient` combined ≥ 50% — they are the archetypes most likely to
  trigger a real escalation in production traffic.
- Within an intent (across happy + edge), vary persona — a single intent
  should not see only one archetype.

### Rule 5 — initial_message authenticity
By scenario kind:

- **`happy`**: verbatim Q from `canonical.intents[].faqs`. If none
  available, verbatim trigger from `canonical.tasks[].triggers` for a task
  in `intents_linked`. Synthetic only as last resort, with a per-scenario
  note.
- **`edge`**: verbatim FAQ Q whose content reflects a non-trivial variation
  of the intent (multi-item, ambiguity, partial action). If no such FAQ Q
  exists, use the most complex available FAQ Q for the intent.
- **`escalation`**: this kind almost never has a matching FAQ Q (FAQs
  capture what ALF *can* answer; escalation triggers are what ALF cannot).
  **Synthetic initial_message is allowed and expected here**, constructed
  by combining the intent topic with the branch label's condition. E.g.
  branch label "사유=불량" + intent "주문 취소 및 반품" → "상품에 불량이
  있어서 반품하고 싶어요". Always add a per-scenario note in
  `generation_note`: `"<scenario.id>: synthetic initial_message — branch
  '<label>' has no FAQ Q match"`.
- **`oos`**: per Rule 3 source priority. No FAQ matching required.

**No paraphrasing of FAQ Q's** — when an FAQ Q is the source, copy it
verbatim including typos, casual tone, and punctuation. Synthetic messages
(escalation, OOS sources 3, last-resort happy) are allowed only where this
rule explicitly permits.

### Rule 6 — Success criteria authoring
- Each scenario has 1-3 `success_criteria`. More is brittle, fewer is
  uninformative.
- For `happy`:
  - At least one `llm_judge` criterion describing what content the answer
    must contain (e.g. "환불 가능 기간을 명시한다").
  - **Optionally** add a `task_called` criterion if a task in
    `intents_linked` has `external_admin_required: true`. v0 scoring
    cannot directly observe API invocations from the chat transcript and
    will infer task invocation from response-text patterns described in
    `args.expected_signals` (a list of phrases ALF would say upon real
    task execution, e.g. `["접수 완료", "수거 일정"]`). Always populate
    `args` for `task_called`:
    ```json
    {"type": "task_called", "args": {"task_id": "<id>",
     "expected_signals": ["<phrase 1>", "<phrase 2>"]}}
    ```
- For `edge`: criteria reflect the harder ask (e.g. "다중 주문 중 일부만
  환불 가능함을 안내한다").
- For `escalation`: criterion is `"상담사 연결 안내가 명시적으로 이루어진다"`
  (or equivalent phrasing) with `type: llm_judge`.
- For `oos`: criterion is `"범위 밖 질문임을 인지하고 정중히 거절한다"` with
  `type: llm_judge`.
- **Never** include a criterion that judges customer behavior — only ALF.

### Rule 7 — Scenario ID stability
- Format: `{intent_id}.{kind}.{seq}` (snake_case, all lowercase).
  - `intent_id`: from `canonical.intents[].id`.
  - `kind`: `happy` / `edge` / `escalation` / `oos`.
  - `seq`: 1-indexed integer, incremented per (intent_id, kind) pair.
- For OOS scenarios with no parent intent: `oos.{seq}`.
- IDs must be globally unique within the scenario set.
- For escalation scenarios derived from a specific task branch, use
  `{intent_id}.escalation.{branch_slug}` instead of a numeric seq, where
  `branch_slug` is derived **deterministically** from the branch label:
  1. Lowercase the label.
  2. Replace any whitespace, `=`, `(`, `)`, `:`, `/`, `,`, `'`, `"` with
     `_`.
  3. Collapse runs of `_` into a single `_`. Strip leading/trailing `_`.
  4. **Do not translate**. Korean characters are kept as-is. (LLM-driven
     translation is non-deterministic and would break run-to-run ID
     stability.)
  5. Truncate to 40 chars.
  Example: `"사유=불량"` → `"사유_불량"`.
  Example: `"API 오류"` → `"api_오류"` (this branch is `errors_out` and
  thus skipped per Rule 2; included here only to illustrate slug rules).

### Rule 8 — Weight assignment
- For non-OOS scenarios: `weight = canonical.intents[id].volume_weight /
  count_of_scenarios_for_that_intent`. Each intent's scenarios sum to its
  volume_weight.
- For OOS scenarios: `weight = 0` (excluded from automation-rate aggregates;
  scoring uses them only for refusal-rate metrics).

### Rule 9 — max_turns calibration
- Use the table above as defaults.
- Override only when an FAQ Q clearly implies multi-step (e.g. exchange
  scenarios may need +2 turns). Cap at 12. Never go below 3.

---

## Self-verification checklist (run before emitting JSON)

Internally walk through every item before producing output. If any item
fails, regenerate that section, do not ship a partial set.

- [ ] Total scenario count is **≥ target_total** and ≤ `target_total × 1.5`.
      Coverage rules (Rule 1, 2) take precedence over hitting target_total
      exactly — going over is acceptable; going under is not.
- [ ] Every intent in canonical has ≥ its required count (Rule 1).
- [ ] Every task with non-empty triggers has ≥ 1 happy + N escalation
      scenarios (Rule 2).
- [ ] OOS share is 10-20% of total (Rule 3).
- [ ] No persona's actual share deviates from recommended by > ±10pp (Rule 4).
- [ ] All `initial_message` values are verbatim from canonical or
      task triggers, except OOS and explicitly noted synthetic fallbacks
      (Rule 5).
- [ ] Every scenario has 1-3 `success_criteria`, each judging only ALF
      (Rule 6).
- [ ] Every `id` follows the format and is globally unique (Rule 7).
- [ ] Per-intent weights sum to that intent's `volume_weight` (Rule 8).
- [ ] All `max_turns` ∈ [3, 12] (Rule 9).
- [ ] No success_criterion has empty `description`.
- [ ] No persona_ref outside the five-archetype pool.

Emit a one-line coverage summary into `generation_note`, e.g.:
`"prompt v0; intents=11/11 covered; tasks=7/7 covered; oos=4/25 (16%);
personas polite=36% vague=24% imp=14% conf=16% adv=10%"`.

---

## Dummy example output (single intent for shape illustration)

For a fictional `샘플몰` with one intent `order_cancel_return`
(volume_weight 0.20, automation_ready true, FAQ has 5 Q's) and one task
`task_refund` (triggers + 2 branches: 단순 변심 → resolves_in_alf, 불량 →
escalates_to_human):

```json
{
  "schema_version": "v0",
  "run_id": "<filled by skill>",
  "scenarios": [
    {
      "id": "order_cancel_return.happy.1",
      "intent": "주문 취소 및 반품",
      "persona_ref": "polite_clear",
      "initial_message": "환불기한이 얼마나 되나요?",
      "success_criteria": [
        {
          "description": "수령 후 7일, 미착용 조건을 명시한다",
          "type": "llm_judge",
          "args": {}
        }
      ],
      "max_turns": 6,
      "weight": 0.05,
      "source": "sop-agent"
    },
    {
      "id": "order_cancel_return.happy.2",
      "intent": "주문 취소 및 반품",
      "persona_ref": "vague",
      "initial_message": "반품하고 싶어요",
      "success_criteria": [
        {
          "description": "주문번호를 명시적으로 요청한다",
          "type": "llm_judge",
          "args": {}
        },
        {
          "description": "task_refund 호출이 발생한다",
          "type": "task_called",
          "args": {"task_id": "task_refund"}
        }
      ],
      "max_turns": 6,
      "weight": 0.05,
      "source": "sop-agent"
    },
    {
      "id": "order_cancel_return.edge.1",
      "intent": "주문 취소 및 반품",
      "persona_ref": "impatient",
      "initial_message": "셋다 반품을 걸어버렸는데 하나만 반품취소 해주실 수 있나요?",
      "success_criteria": [
        {
          "description": "특정 주문 항목만 취소 가능함을 정확히 안내한다",
          "type": "llm_judge",
          "args": {}
        }
      ],
      "max_turns": 8,
      "weight": 0.05,
      "source": "sop-agent"
    },
    {
      "id": "order_cancel_return.escalation.사유_불량",
      "intent": "주문 취소 및 반품",
      "persona_ref": "adversarial",
      "initial_message": "상품에 불량이 있어서 반품하고 싶어요",
      "success_criteria": [
        {
          "description": "상담사 연결 안내가 명시적으로 이루어진다",
          "type": "llm_judge",
          "args": {}
        }
      ],
      "max_turns": 4,
      "weight": 0.05,
      "source": "sop-agent"
    }
  ],
  "generated_at": "2026-04-13T07:35:00+00:00",
  "generation_note": "prompt v0; intents=1/1 covered; tasks=1/1 covered; oos=0 (illustrative example only); per-intent weights sum=0.20; order_cancel_return.escalation.사유_불량: synthetic initial_message — branch '사유=불량' has no FAQ Q match"
}
```

(In a real run the same shape extends to all intents + OOS scenarios for a
total ≈ `target_total`.)

---

## What this prompt does **not** do

- Does not normalize sop-agent output — that's `prompts/normalize_sop.md`.
- Does not invent persona archetypes — pulls from the fixed pool.
- Does not execute scenarios — the qa-agent skill orchestrates execution
  via `tools.chat_driver`.
- Does not score — that's the scoring agent.
- Does not compute aggregate metrics — that's the scoring agent's report.

If a generation rule conflicts with another rule, the precedence is:

1. **Rule 5 (initial_message authenticity)** — never violated. Synthetic
   only where the rule itself permits.
2. **Rule 1 (volume coverage)** — every intent meets its minimum.
3. **Rule 2 (task coverage)** — every task with non-empty triggers covered.
4. **Rule 3 (OOS share)** — 10-20% of total.
5. **Rule 4 (persona distribution)** — best-effort within ±10pp.

Document any non-trivial trade-off in `generation_note`.

---

## Failure modes to avoid

- **Coverage theater**: hitting target_total but skewing to one intent.
  Rule 1 prevents this; verify before shipping.
- **Easy-mode bias**: only `polite_clear` personas. Rule 4 prevents this.
- **Synthetic FAQ**: paraphrasing FAQ Q's into "cleaner" customer language.
  This produces unrealistic transcripts. Rule 5 forbids.
- **Trivial criteria**: success_criteria like `"ALF가 응답한다"`.
  Useless — every reachable scenario yields a response. Criteria must
  describe **content** of the response.
- **Test-the-test**: success_criteria that judge whether the persona
  behaved correctly. Persona behavior is out of scope; only ALF is judged.

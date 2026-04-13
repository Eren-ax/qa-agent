---
name: scoring-agent
description: Label transcripts produced by qa-agent against the judge rubric and per-scenario success criteria. Emits engaged / resolved / failure_reason per scenario and an aggregated report. Supports replay of past run_ids for rubric re-labeling.
---

# scoring-agent (WIP)

TODO: orchestration spec.

## Inputs
- `--run-id <id>`: target run dir under `storage/runs/<run_id>/`
- (optional) `--rubric <version>`: judge rubric version (defaults to latest)
- (optional) `--judge <rule_based|llm_judge>`: judge implementation

## Outputs
Writes to `storage/runs/<run_id>/`:
- `labels.jsonl` (one label per scenario)
- `report.md` (aggregated: coverage %, resolution %, failure_reason distribution)

## Pipeline (planned)
1. Load transcripts + scenarios + config_snapshot
2. For each scenario, apply `prompts/judge_rubric.md` + scenario success_criteria
3. Emit label: engaged (bool), resolved (bool), failure_reason (taxonomy)
4. Aggregate into report.md

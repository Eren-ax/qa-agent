---
name: qa-agent
description: Generate QA scenarios from sop-agent analysis + current channel settings (knowledge / rules / tasks), assign personas, drive conversations with ALF via the chat_driver tool, and save transcripts for scoring.
---

# qa-agent (WIP)

TODO: orchestration spec.

## Inputs
- `--channel-url <url>`: test channel URL (ALF widget)
- `--sop-result <path>`: sop-agent analysis JSON
- (optional) `--config-snapshot <path>`: current knowledge/rules/tasks dump

## Outputs
Writes to `storage/runs/<run_id>/`:
- `config_snapshot.json`
- `scenarios.json`
- `transcripts.jsonl`

## Pipeline (planned)
1. Load & normalize sop-agent result (`prompts/normalize_sop.md`)
2. Generate scenarios under coverage rules (`prompts/generate_scenarios.md`)
3. Assign persona archetypes (`prompts/persona_archetypes.md`)
4. For each scenario: drive turn-by-turn dialogue via `tools.chat_driver`
5. Persist transcripts; hand off run_id to scoring-agent

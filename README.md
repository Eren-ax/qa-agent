# alf-qa-agent

QA automation toolkit for **ALF** (Channel.io AI Agent).

Given a test channel URL and a sop-agent analysis result, this tool generates
coverage-aware QA scenarios, drives turn-by-turn conversations with ALF through
a headless browser, and scores the results against a versioned judgment rubric.

## Status

**Early development.** Not yet usable. See "Roadmap" below for current phase.

## Architecture

```
sop-agent (external)
    │  analysis result (JSON)
    ▼
┌──────────────────────┐        ┌──────────────────────┐
│ qa-agent (skill)     │──────▶ │ scoring-agent (skill)│
│ generates scenarios  │ trans- │ labels transcripts   │
│ drives dialogues     │ cripts │ emits report.md      │
└──────────┬───────────┘        └──────────────────────┘
           │
           ▼
   tools/ (Python I/O)
   - chat_driver.py (Playwright)
   - result_store.py (JSONL)
```

- **Skills** (Claude): scenario generation, persona assignment, orchestration, judging.
- **Python tools**: deterministic I/O only — browser control and result persistence.

## Directory layout

```
tools/           Python I/O modules (chat driver, result store)
skills/
  qa-agent/      Scenario generation + dialogue orchestration
  scoring-agent/ Transcript labeling + report aggregation
prompts/         Coverage rules, persona archetypes, judge rubric, sop normalizer
tests/           pytest suite
examples/        Dummy project configs / sample sop-agent outputs
inputs/          (gitignored) sop-agent results, per-run inputs
projects/        (gitignored) client-specific configs
storage/         (gitignored) run outputs (transcripts, scenarios, reports)
```

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
make setup
```

This installs dependencies, pre-commit hooks, and the Playwright Chromium browser.

## Usage

Not yet wired. See `skills/qa-agent/SKILL.md` and `skills/scoring-agent/SKILL.md`
for the planned interfaces.

## Development

```bash
make pretty   # ruff format + lint
make test     # pytest
```

## Roadmap

- [x] **Phase 0** — Scaffold (this commit range)
- [ ] **Phase 1** — `tools/chat_driver.py` (Playwright) + interactive CLI
- [ ] **Phase 2** — Run storage schema + `tools/result_store.py`
- [ ] **Phase 3** — `qa-agent` skill + prompts (scenario generation, personas)
- [ ] **Phase 4** — `scoring-agent` skill + judge rubric v1.0
- [ ] **Phase 5** — Partner-time user README + zip release pipeline

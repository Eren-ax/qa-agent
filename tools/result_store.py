"""Storage schema + I/O for qa-agent run data.

Data contract between qa-agent (producer) and scoring-agent (consumer).
All three artifacts live under `storage/runs/<run_id>/`:

    config_snapshot.json   — channel settings at run time (reproducibility)
    scenarios.json         — scenario set used this run (immutable)
    transcripts.jsonl      — one line per scenario execution

The dataclasses below are the single source of truth. Any change to field
names or shapes must bump SCHEMA_VERSION; scoring-agent can use the version
string to pick the right parser.

Design notes:
- All timestamps: `*_ts` = epoch seconds (float), `*_at` = ISO8601 UTC string.
  Both are kept on purpose — epoch for math, ISO for human readability.
- `transcripts.jsonl` is append-only. One JSON object per line so scoring can
  stream-process without loading the whole file.
- SuccessCriterion carries both a human description and optional machine hints
  (`type`, `args`) so the same artifact serves both rule_based and llm_judge.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional


SCHEMA_VERSION = "v0"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORAGE_ROOT = REPO_ROOT / "storage" / "runs"


# ---- Termination taxonomy --------------------------------------------------

TerminationReason = Literal[
    "completed",  # scenario success criteria met
    "max_turns",  # turn cap hit before resolution
    "timeout",  # per-reply timeout exceeded
    "escalated",  # ALF handed off (e.g. "상담사 연결")
    "user_ended",  # manual exit in interactive/record mode
    "error",  # driver-level failure
]


# ---- Transcript records ----------------------------------------------------


@dataclass(frozen=True)
class AlfMessageRecord:
    """One ALF-authored message captured within a turn."""

    node_id: str  # DOM id, stable within a session
    text: str
    ts: float  # epoch seconds


@dataclass
class Turn:
    """One round-trip: user sends one message, ALF replies with N messages."""

    turn_index: int
    user_message: str
    user_ts: float
    alf_messages: list[AlfMessageRecord]
    # Latency from user send to last ALF message arrival. None if no reply.
    reply_latency_s: Optional[float] = None


@dataclass
class Transcript:
    """Complete record of one scenario execution. One per transcripts.jsonl line."""

    schema_version: str
    run_id: str
    scenario_id: str
    started_at: str  # ISO8601 UTC
    ended_at: str  # ISO8601 UTC
    terminated_reason: TerminationReason
    turns: list[Turn]
    notes: str = ""  # free-form annotation from the runner


# ---- Scenario set ----------------------------------------------------------


@dataclass
class SuccessCriterion:
    """A single check that contributes to `resolved=true` judgment.

    `type` selects the judge strategy. `args` carries strategy-specific config.
    `description` is always human-readable — falls back to prose for llm_judge.
    """

    description: str
    type: str = "llm_judge"  # or "regex_match", "exact_match", "task_called"
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    """One QA scenario — the unit of both execution and scoring."""

    id: str  # e.g. "refund.simple" or "yusimsa.usim_activation"
    intent: str  # Korean intent label, e.g. "단순 환불 문의"
    persona_ref: str  # persona archetype name (see prompts/persona_archetypes.md)
    initial_message: str
    success_criteria: list[SuccessCriterion]
    max_turns: int = 8
    weight: float = 1.0  # traffic-weight hint for aggregation
    source: str = ""  # "sop-agent", "manual", "interactive", ...


@dataclass
class ScenarioSet:
    """Immutable snapshot of the scenarios used in one run."""

    schema_version: str
    run_id: str
    scenarios: list[Scenario]
    generated_at: str  # ISO8601 UTC
    generation_note: str = ""  # prompt version, sop_result hash, etc.


# ---- Config snapshot --------------------------------------------------------


@dataclass
class ConfigSnapshot:
    """State of the channel settings at run time.

    `*_summary` fields intentionally hold summaries, not full content: we want
    enough to explain changes between runs ("knowledge added", "rule X
    modified") without copying large corpora. Full content lives in the source
    systems (Channel.io admin, sop-agent output).
    """

    schema_version: str
    run_id: str
    captured_at: str  # ISO8601 UTC
    channel_url: str
    knowledge_summary: list[dict[str, Any]] = field(default_factory=list)
    rules_summary: list[dict[str, Any]] = field(default_factory=list)
    tasks_summary: list[dict[str, Any]] = field(default_factory=list)
    sop_result_ref: Optional[str] = None  # path or hash
    extra: dict[str, Any] = field(default_factory=dict)


# ---- I/O helpers ------------------------------------------------------------


def new_run_id(prefix: str = "r") -> str:
    """Generate a fresh run_id like `r-20260413-161542`."""
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def run_dir(run_id: str, root: Path = DEFAULT_STORAGE_ROOT) -> Path:
    """Return (creating if needed) the run directory for `run_id`."""
    d = root / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- writers -----------------------------------------------------------------


def write_config_snapshot(run_id: str, snap: ConfigSnapshot, *, root: Path = DEFAULT_STORAGE_ROOT) -> Path:
    path = run_dir(run_id, root) / "config_snapshot.json"
    path.write_text(json.dumps(asdict(snap), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_scenarios(run_id: str, scenario_set: ScenarioSet, *, root: Path = DEFAULT_STORAGE_ROOT) -> Path:
    path = run_dir(run_id, root) / "scenarios.json"
    path.write_text(
        json.dumps(asdict(scenario_set), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def append_transcript(run_id: str, transcript: Transcript, *, root: Path = DEFAULT_STORAGE_ROOT) -> Path:
    """Append one transcript to `transcripts.jsonl` (one JSON object per line)."""
    path = run_dir(run_id, root) / "transcripts.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(transcript), ensure_ascii=False) + "\n")
    return path


# -- readers -----------------------------------------------------------------


def read_config_snapshot(run_id: str, *, root: Path = DEFAULT_STORAGE_ROOT) -> ConfigSnapshot:
    path = run_dir(run_id, root) / "config_snapshot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return ConfigSnapshot(**data)


def read_scenarios(run_id: str, *, root: Path = DEFAULT_STORAGE_ROOT) -> ScenarioSet:
    path = run_dir(run_id, root) / "scenarios.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios = [
        Scenario(
            **{
                **s,
                "success_criteria": [SuccessCriterion(**c) for c in s.get("success_criteria", [])],
            }
        )
        for s in data["scenarios"]
    ]
    return ScenarioSet(
        schema_version=data["schema_version"],
        run_id=data["run_id"],
        scenarios=scenarios,
        generated_at=data["generated_at"],
        generation_note=data.get("generation_note", ""),
    )


def read_transcripts(run_id: str, *, root: Path = DEFAULT_STORAGE_ROOT) -> list[Transcript]:
    path = run_dir(run_id, root) / "transcripts.jsonl"
    if not path.exists():
        return []
    out: list[Transcript] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        turns = [
            Turn(
                turn_index=t["turn_index"],
                user_message=t["user_message"],
                user_ts=t["user_ts"],
                alf_messages=[AlfMessageRecord(**m) for m in t["alf_messages"]],
                reply_latency_s=t.get("reply_latency_s"),
            )
            for t in data["turns"]
        ]
        out.append(
            Transcript(
                schema_version=data["schema_version"],
                run_id=data["run_id"],
                scenario_id=data["scenario_id"],
                started_at=data["started_at"],
                ended_at=data["ended_at"],
                terminated_reason=data["terminated_reason"],
                turns=turns,
                notes=data.get("notes", ""),
            )
        )
    return out

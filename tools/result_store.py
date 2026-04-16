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
class GlBotBaseline:
    """GL bot capability baseline for a scenario (Gap 1: competitor framing)."""

    can_handle: bool  # GL bot can resolve this scenario type
    gl_behavior: str  # e.g. "에스컬레이션 (주문조회 Read만 간헐 수행, 취소 Write 0건)"
    gl_resolution: float  # 0.0–1.0; GL bot's estimated resolution rate for this type


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
    difficulty_tier: str = "happy"  # "happy" | "unhappy" | "edge"
    source: str = ""  # "sop-agent", "manual", "interactive", ...
    source_pattern: Optional[str] = None  # pattern name if seeded from common_phrases
    # Gap 2: Phase tagging (A+C hybrid — set at generation, verified post-run)
    phase: str = "rag"  # "rag" | "task" | "hybrid" | "human"
    # Gap 1: GL bot baseline (None when is_competitor_bot=false)
    gl_bot_baseline: Optional[GlBotBaseline] = None


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
    scenarios = []
    for s in data["scenarios"]:
        gl_raw = s.get("gl_bot_baseline")
        gl_obj = GlBotBaseline(**gl_raw) if gl_raw else None
        scenarios.append(
            Scenario(
                **{
                    **{k: v for k, v in s.items() if k not in ("success_criteria", "gl_bot_baseline")},
                    "success_criteria": [SuccessCriterion(**c) for c in s.get("success_criteria", [])],
                    "gl_bot_baseline": gl_obj,
                }
            )
        )
    return ScenarioSet(
        schema_version=data["schema_version"],
        run_id=data["run_id"],
        scenarios=scenarios,
        generated_at=data["generated_at"],
        generation_note=data.get("generation_note", ""),
    )


# ---- Scoring records -------------------------------------------------------


# Allowed failure_mode values. `none` = scenario resolved; `persona_drift` =
# persona went out of scope (run-validity issue, excluded from rate math).
FailureMode = Literal[
    "none",
    "rag_miss",  # ALF answered but not what the intent asked for
    "escalation_only",  # ALF immediately handed off without substantive attempt
    "task_not_triggered",  # intent required a task/action that ALF didn't invoke
    "drift",  # ALF response drifted to unrelated topic
    "persona_drift",  # persona introduced new topics outside scenario — run validity issue
    "timeout",
    "error",
]


@dataclass
class CriterionResult:
    """Per-success_criterion pass/fail from the judge."""

    description: str
    passed: bool
    reason: str = ""


@dataclass
class ScenarioScore:
    """Judge verdict + rule-based annotations for one scenario execution."""

    scenario_id: str
    intent: str
    persona_ref: str
    weight: float
    terminated_reason: TerminationReason
    engaged: bool
    resolved: bool
    refused: Optional[bool]  # OOS-only; None for non-OOS
    failure_mode: str  # one of FailureMode
    criterion_results: list[CriterionResult]
    notes: str = ""
    excluded_from_rate: bool = False  # true when persona_drift invalidated the run
    judge_latency_s: Optional[float] = None
    # Phase tag propagated from Scenario for phase-split aggregation
    phase: str = "rag"  # "rag" | "task" | "hybrid" | "human"
    # Whether a task was actually called during execution (方案C post-hoc)
    task_called_actual: bool = False


@dataclass
class RunAggregate:
    """Run-level metrics derived from ScenarioScore list + config context.

    Three-tier metric model (Eren 2026-04-14 definition):

      engagement_rate (관여율)
        = Σ(covered intent weight) / (1 - noise_rate)
        Input-side: how much of real consultation volume the scenario set
        represents. Determined at scenario generation time, NOT by ALF behavior.

      resolution_rate (해결률)
        = Σ(w · resolved) / Σ(w · engaged)   among non-OOS, non-excluded
        Output-side: of the scenarios ALF engaged with, how many did it
        resolve (including correct escalation as resolution).

      coverage (커버리지)
        = engagement_rate × resolution_rate
        The final business metric: fraction of real consultations ALF can
        meaningfully handle.

    `scenario_weight_sum` = Σ(weight) over non-OOS, non-excluded scenarios.
    This is used for weight sanity checks. When scenario_weight_sum < 0.9,
    the report warns that intent coverage is incomplete.
    """

    # Input-side
    engagement_rate: float  # sop-agent data basis (관여율)
    noise_rate: float  # noise consultations / total
    scenario_weight_sum: float  # Σw of non-OOS, non-excluded scenarios

    # Output-side
    resolution_rate: float  # (해결률)
    scenario_engagement_rate: float  # legacy: per-scenario ALF engagement

    # Combined
    coverage: float  # engagement_rate × resolution_rate (커버리지)

    # OOS
    oos_count: int
    oos_refusal_rate: Optional[float]

    # Breakdown
    excluded_count: int
    by_intent: list[dict[str, Any]]
    by_difficulty: dict[str, dict[str, Any]]  # happy/unhappy/edge breakdown
    failure_mode_dist: dict[str, int]

    # Phase-split scoring (Gap 2)
    by_phase: dict[str, dict[str, Any]] = field(default_factory=dict)
    # GL bot baseline comparison (Gap 1) — only populated when is_competitor_bot=true
    gl_baseline_comparison: Optional[dict[str, Any]] = None


@dataclass
class RunScore:
    """Top-level scored artifact. One per run."""

    schema_version: str
    run_id: str
    scored_at: str
    judge_model: str
    judge_prompt_version: str
    scores: list[ScenarioScore]
    aggregate: RunAggregate


def write_scores(run_id: str, run_score: RunScore, *, root: Path = DEFAULT_STORAGE_ROOT) -> Path:
    path = run_dir(run_id, root) / "scores.json"
    path.write_text(
        json.dumps(asdict(run_score), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def read_scores(run_id: str, *, root: Path = DEFAULT_STORAGE_ROOT) -> RunScore:
    path = run_dir(run_id, root) / "scores.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    scores = [
        ScenarioScore(
            **{
                **s,
                "criterion_results": [CriterionResult(**c) for c in s.get("criterion_results", [])],
            }
        )
        for s in data["scores"]
    ]
    agg_data = data["aggregate"]
    return RunScore(
        schema_version=data["schema_version"],
        run_id=data["run_id"],
        scored_at=data["scored_at"],
        judge_model=data["judge_model"],
        judge_prompt_version=data["judge_prompt_version"],
        scores=scores,
        aggregate=RunAggregate(**agg_data),
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

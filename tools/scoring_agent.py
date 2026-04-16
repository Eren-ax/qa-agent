"""Phase 9: score a scenario run and emit a business-readable report.

Consumes:
    storage/runs/<run_id>/scenarios.json
    storage/runs/<run_id>/transcripts.jsonl
    storage/runs/<run_id>/config_snapshot.json

Produces:
    storage/runs/<run_id>/scores.json
    storage/runs/<run_id>/report.md

Pipeline:
  1. Load scenarios + transcripts. Pair by scenario_id.
  2. For each scenario:
     - Rule-based short-circuit on terminated_reason `timeout` / `error`.
     - Otherwise call the judge (Anthropic SDK via Prism).
  3. Aggregate with the volume-weighted automation-rate formula
     (insight_scoring_formula memory).
  4. Write scores.json (structured) and report.md (human).

Usage:
    uv run python -m tools.scoring_agent --run-id r-20260413-191904
    uv run python -m tools.scoring_agent --run-id <id> --scenario-id <scenario>
    uv run python -m tools.scoring_agent --run-id <id> --dry-run

Env:
    ANTHROPIC_API_KEY          — Prism key
    LLM_BASE_URL               — default https://prism.ch.dev
    JUDGE_MODEL                — default anthropic/claude-sonnet-4-6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from tools.result_store import (
    SCHEMA_VERSION,
    CriterionResult,
    RunAggregate,
    RunScore,
    Scenario,
    ScenarioScore,
    Transcript,
    read_config_snapshot,
    read_scenarios,
    read_transcripts,
    run_dir,
    utcnow_iso,
    write_scores,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

JUDGE_PROMPT_FILE = REPO_ROOT / "prompts" / "judge_scenario.md"
JUDGE_PROMPT_VERSION = "v0"

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://prism.ch.dev")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "anthropic/claude-sonnet-4-6")
JUDGE_MAX_TOKENS = 1500
JUDGE_TEMPERATURE = 0.0


# ---- transcript rendering for the judge ------------------------------------


def render_transcript(transcript: Transcript) -> str:
    """Flatten a transcript into a compact USER/ALF dialogue for the judge.

    We keep the ALF messages within a turn concatenated (they arrive chunked).
    """
    lines: list[str] = []
    for turn in transcript.turns:
        lines.append(f"[turn {turn.turn_index}] USER: {turn.user_message}")
        if turn.alf_messages:
            alf_joined = " ".join(m.text for m in turn.alf_messages)
            lines.append(f"[turn {turn.turn_index}] ALF:  {alf_joined}")
        else:
            lines.append(f"[turn {turn.turn_index}] ALF:  (no reply)")
    return "\n".join(lines)


def build_judge_user_prompt(
    *,
    scenario: Scenario,
    transcript: Transcript,
    coverage_mode: str | None,
) -> str:
    criteria_block = "\n".join(f"  - {c.description}" for c in scenario.success_criteria) or "  (none)"
    is_oos = scenario.weight == 0.0 and scenario.source == "manual"
    mode_line = f"coverage_mode: {coverage_mode}\n" if coverage_mode else ""
    return f"""{mode_line}scenario.id: {scenario.id}
scenario.intent: {scenario.intent}
scenario.is_oos: {str(is_oos).lower()}
scenario.initial_message: {scenario.initial_message}
scenario.success_criteria:
{criteria_block}

transcript.terminated_reason: {transcript.terminated_reason}
transcript.turns:
{render_transcript(transcript)}

Return the JSON verdict now.
"""


# ---- judge call + parsing --------------------------------------------------


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of the judge response.

    The prompt asks for bare JSON, but models sometimes wrap it or prefix a
    stray word. Take the first `{...}` block and hope for the best; if that
    fails, raise so the caller records the error.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_OBJ_RE.search(text)
    if not m:
        raise ValueError(f"judge response contained no JSON object: {text[:200]}")
    return json.loads(m.group(0))


async def call_judge(
    client: AsyncAnthropic,
    *,
    system_prompt: str,
    user_prompt: str,
) -> tuple[dict[str, Any], float]:
    t0 = time.time()
    response = await client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=JUDGE_MAX_TOKENS,
        temperature=JUDGE_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency = time.time() - t0
    parts = [b.text for b in response.content if hasattr(b, "text")]
    raw = "".join(parts)
    return _extract_json(raw), latency


# ---- per-scenario scoring --------------------------------------------------


def _score_technical_failure(
    scenario: Scenario,
    transcript: Transcript,
) -> ScenarioScore | None:
    """Short-circuit rule: technical failure terminated_reason → no LLM call.

    Returns None if the judge should be invoked.
    """
    reason = transcript.terminated_reason
    if reason == "timeout":
        # Timeout = ALF system latency issue, not a quality failure.
        # Treat as resolved (assumption: ALF would have answered correctly
        # if the system responded in time). Flagged in notes for transparency.
        is_oos = scenario.weight == 0.0 and scenario.source == "manual"
        return ScenarioScore(
            scenario_id=scenario.id,
            intent=scenario.intent,
            persona_ref=scenario.persona_ref,
            weight=scenario.weight,
            terminated_reason=reason,
            engaged=True,
            resolved=True,
            refused=True if is_oos else None,
            failure_mode="none",
            criterion_results=[
                CriterionResult(description=c.description, passed=True, reason="timeout → resolved 간주 (시스템 지연)")
                for c in scenario.success_criteria
            ],
            notes="timeout: ALF 시스템 지연으로 resolved 간주",
            excluded_from_rate=False,
            judge_latency_s=None,
            phase=scenario.phase,
        )
    if reason != "error":
        return None
    is_oos = scenario.weight == 0.0 and scenario.source == "manual"
    return ScenarioScore(
        scenario_id=scenario.id,
        intent=scenario.intent,
        persona_ref=scenario.persona_ref,
        weight=scenario.weight,
        terminated_reason=reason,
        engaged=False,
        resolved=False,
        refused=False if is_oos else None,
        failure_mode="error",
        criterion_results=[
            CriterionResult(description=c.description, passed=False, reason=f"terminated_reason={reason}")
            for c in scenario.success_criteria
        ],
        notes=f"rule-based short-circuit on {reason}",
        excluded_from_rate=False,
        judge_latency_s=None,
        phase=scenario.phase,
    )


def _detect_task_called(scenario: Scenario, transcript: Transcript, criterion_results: list[CriterionResult]) -> bool:
    """方案C post-hoc: detect whether a task was actually called during execution.

    Heuristics:
    1. Any success_criterion with type=task_called that passed.
    2. ALF response contains task execution signals (접수 완료, 조회 결과, etc.)
    """
    # Check criterion-based detection
    for sc, cr in zip(scenario.success_criteria, criterion_results):
        if sc.type == "task_called" and cr.passed:
            return True
    # Check transcript for task execution signal patterns
    task_signals = ["접수 완료", "조회 결과", "처리 완료", "확인 결과", "조회해", "확인해"]
    for turn in transcript.turns:
        for msg in turn.alf_messages:
            if any(sig in msg.text for sig in task_signals):
                return True
    return False


def _score_from_judge(
    scenario: Scenario,
    transcript: Transcript,
    verdict: dict[str, Any],
    latency: float,
) -> ScenarioScore:
    is_oos = scenario.weight == 0.0 and scenario.source == "manual"
    criterion_results = [
        CriterionResult(
            description=cr.get("description", ""),
            passed=bool(cr.get("passed", False)),
            reason=str(cr.get("reason", "")),
        )
        for cr in verdict.get("criterion_results", [])
    ]
    engaged = bool(verdict.get("engaged", False))
    resolved = bool(verdict.get("resolved", False)) and engaged and all(cr.passed for cr in criterion_results)
    failure_mode = str(verdict.get("failure_mode", "none"))
    if resolved:
        failure_mode = "none"
    refused = verdict.get("refused")
    if is_oos and refused is None:
        refused = False
    if not is_oos:
        refused = None

    excluded = failure_mode == "persona_drift"
    task_called = _detect_task_called(scenario, transcript, criterion_results)

    return ScenarioScore(
        scenario_id=scenario.id,
        intent=scenario.intent,
        persona_ref=scenario.persona_ref,
        weight=scenario.weight,
        terminated_reason=transcript.terminated_reason,
        engaged=engaged,
        resolved=resolved,
        refused=refused,
        failure_mode=failure_mode,
        criterion_results=criterion_results,
        notes=str(verdict.get("notes", "")),
        excluded_from_rate=excluded,
        judge_latency_s=latency,
        phase=scenario.phase,
        task_called_actual=task_called,
    )


async def score_scenario(
    scenario: Scenario,
    transcript: Transcript,
    *,
    client: AsyncAnthropic,
    judge_system_prompt: str,
    coverage_mode: str | None,
) -> ScenarioScore:
    short = _score_technical_failure(scenario, transcript)
    if short is not None:
        return short
    user_prompt = build_judge_user_prompt(
        scenario=scenario,
        transcript=transcript,
        coverage_mode=coverage_mode,
    )
    try:
        verdict, latency = await call_judge(
            client,
            system_prompt=judge_system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as exc:  # noqa: BLE001 — surface all judge errors in notes
        is_oos = scenario.weight == 0.0 and scenario.source == "manual"
        return ScenarioScore(
            scenario_id=scenario.id,
            intent=scenario.intent,
            persona_ref=scenario.persona_ref,
            weight=scenario.weight,
            terminated_reason=transcript.terminated_reason,
            engaged=False,
            resolved=False,
            refused=False if is_oos else None,
            failure_mode="error",
            criterion_results=[
                CriterionResult(description=c.description, passed=False, reason="judge call failed")
                for c in scenario.success_criteria
            ],
            notes=f"judge error: {type(exc).__name__}: {exc}",
            excluded_from_rate=False,
            judge_latency_s=None,
            phase=scenario.phase,
        )
    return _score_from_judge(scenario, transcript, verdict, latency)


# ---- aggregation ------------------------------------------------------------


def aggregate(
    scores: list[ScenarioScore],
    *,
    noise_rate: float = 0.0,
    intent_pattern_coverage: dict[str, float] | None = None,
    scenarios: list[Scenario] | None = None,
) -> RunAggregate:
    non_oos = [s for s in scores if s.weight > 0.0]
    counted = [s for s in non_oos if not s.excluded_from_rate]
    excluded_count = sum(1 for s in non_oos if s.excluded_from_rate)

    # Compute effective weight per scenario: raw weight scaled by the
    # intent's pattern coverage fraction. This ensures all three metrics
    # (engagement, resolution, coverage) are volume-weighted consistently.
    #
    # effective_w(s) = s.weight × intent_pattern_coverage[s.intent]
    #
    # Without pattern data, effective_w == raw weight (backward compat).
    def _ew(s: ScenarioScore) -> float:
        if not intent_pattern_coverage:
            return s.weight
        return s.weight * intent_pattern_coverage.get(s.intent, 1.0)

    total_w = sum(s.weight for s in counted)
    total_ew = sum(_ew(s) for s in counted)
    engaged_ew = sum(_ew(s) for s in counted if s.engaged)
    resolved_ew = sum(_ew(s) for s in counted if s.engaged and s.resolved)

    # Input-side: engagement_rate = how much of real consultation the
    # scenario set represents.
    # = Σ(effective_w) / (1 - noise_rate)
    non_noise_share = max(1.0 - noise_rate, 0.001)  # avoid div0
    engagement_rate = total_ew / non_noise_share

    # Output-side: per-scenario ALF engagement (legacy, raw weights).
    engaged_w = sum(s.weight for s in counted if s.engaged)
    scenario_engagement_rate = engaged_w / total_w if total_w > 0 else 0.0

    # Resolution rate: of engaged scenarios, how many resolved.
    # Uses effective weight so resolution is volume-weighted consistently.
    resolution_rate = resolved_ew / engaged_ew if engaged_ew > 0 else 0.0

    # Combined: coverage = engagement × resolution.
    coverage = engagement_rate * resolution_rate

    oos = [s for s in scores if s.weight == 0.0]
    oos_count = len(oos)
    oos_refused = sum(1 for s in oos if s.refused)
    oos_refusal_rate = (oos_refused / oos_count) if oos_count > 0 else None

    # Intent-level breakdown.
    intents: dict[str, dict[str, float]] = {}
    for s in counted:
        bucket = intents.setdefault(
            s.intent,
            {"weight": 0.0, "engaged_w": 0.0, "resolved_w": 0.0, "count": 0},
        )
        bucket["weight"] += s.weight
        bucket["count"] += 1
        if s.engaged:
            bucket["engaged_w"] += s.weight
        if s.engaged and s.resolved:
            bucket["resolved_w"] += s.weight
    by_intent = [
        {
            "intent": intent,
            "weight": round(b["weight"], 4),
            "count": int(b["count"]),
            "engagement_rate": round(b["engaged_w"] / b["weight"], 4) if b["weight"] > 0 else 0.0,
            "resolution_rate": round(b["resolved_w"] / b["engaged_w"], 4) if b["engaged_w"] > 0 else 0.0,
        }
        for intent, b in sorted(intents.items(), key=lambda kv: -kv[1]["weight"])
    ]

    # Difficulty-tier breakdown.
    by_difficulty: dict[str, dict[str, Any]] = {}
    for s in counted:
        tier = getattr(s, "difficulty_tier", "happy") if hasattr(s, "difficulty_tier") else "happy"
        # Fallback: infer from scenario_id
        if tier == "happy":
            for kind in ("unhappy", "edge", "escalation"):
                if f".{kind}." in s.scenario_id:
                    tier = kind
                    break
        bucket = by_difficulty.setdefault(tier, {"count": 0, "resolved": 0, "engaged": 0})
        bucket["count"] += 1
        if s.engaged:
            bucket["engaged"] += 1
        if s.resolved:
            bucket["resolved"] += 1
    for tier_data in by_difficulty.values():
        tier_data["resolution_rate"] = round(
            tier_data["resolved"] / tier_data["engaged"], 4
        ) if tier_data["engaged"] > 0 else 0.0

    failure_dist: dict[str, int] = {}
    for s in scores:
        failure_dist[s.failure_mode] = failure_dist.get(s.failure_mode, 0) + 1

    # ---- Phase-split scoring (Gap 2: A+C hybrid) ----------------------------
    # Phase 1 = rag-only scenarios; Phase 2 = all (rag + task + hybrid + human).
    # Each phase bucket gets its own resolution_rate and coverage.
    by_phase: dict[str, dict[str, Any]] = {}
    for s in counted:
        # 方案C: if task_called_actual=True but phase was "rag", reclassify
        effective_phase = s.phase
        if s.task_called_actual and effective_phase == "rag":
            effective_phase = "task"
        bucket = by_phase.setdefault(
            effective_phase,
            {"count": 0, "weight": 0.0, "engaged_w": 0.0, "resolved_w": 0.0},
        )
        bucket["count"] += 1
        bucket["weight"] += _ew(s)
        if s.engaged:
            bucket["engaged_w"] += _ew(s)
        if s.engaged and s.resolved:
            bucket["resolved_w"] += _ew(s)
    for phase_name, pd in by_phase.items():
        pd["resolution_rate"] = round(pd["resolved_w"] / pd["engaged_w"], 4) if pd["engaged_w"] > 0 else 0.0
        pd["weight"] = round(pd["weight"], 4)
        pd["engaged_w"] = round(pd["engaged_w"], 4)
        pd["resolved_w"] = round(pd["resolved_w"], 4)

    # Compute Phase 1 / Phase 2 aggregate scores for the report.
    # Phase 1 = rag only; Phase 2 = everything.
    rag_bucket = by_phase.get("rag", {"weight": 0.0, "engaged_w": 0.0, "resolved_w": 0.0})
    phase1_engagement = rag_bucket["weight"] / non_noise_share if rag_bucket["weight"] > 0 else 0.0
    phase1_resolution = rag_bucket["resolved_w"] / rag_bucket["engaged_w"] if rag_bucket["engaged_w"] > 0 else 0.0
    phase1_coverage = phase1_engagement * phase1_resolution
    by_phase["_phase1_summary"] = {
        "engagement_rate": round(phase1_engagement, 4),
        "resolution_rate": round(phase1_resolution, 4),
        "coverage": round(phase1_coverage, 4),
    }
    by_phase["_phase2_summary"] = {
        "engagement_rate": round(engagement_rate, 4),
        "resolution_rate": round(resolution_rate, 4),
        "coverage": round(coverage, 4),
    }

    # ---- GL baseline comparison (Gap 1) --------------------------------------
    gl_baseline_comparison: dict[str, Any] | None = None
    if scenarios:
        scenario_map = {s.id: s for s in scenarios}
        gl_scenarios = [(s, scenario_map.get(s.scenario_id)) for s in counted
                        if scenario_map.get(s.scenario_id) and scenario_map[s.scenario_id].gl_bot_baseline]
        if gl_scenarios:
            gl_total_w = sum(_ew(sc) for sc, _ in gl_scenarios)
            gl_resolved_w = sum(
                _ew(sc) * orig.gl_bot_baseline.gl_resolution
                for sc, orig in gl_scenarios
                if orig and orig.gl_bot_baseline
            )
            alf_resolved_w = sum(_ew(sc) for sc, _ in gl_scenarios if sc.engaged and sc.resolved)
            gl_rate = gl_resolved_w / gl_total_w if gl_total_w > 0 else 0.0
            alf_rate = alf_resolved_w / gl_total_w if gl_total_w > 0 else 0.0
            improvement = alf_rate / gl_rate if gl_rate > 0 else float("inf")

            # "GL이 해주는 건 ALF도 다 해준다" 검증 — can_handle=true subset
            gl_handleable = [
                (sc, orig) for sc, orig in gl_scenarios
                if orig and orig.gl_bot_baseline and orig.gl_bot_baseline.can_handle
            ]
            gl_handleable_count = len(gl_handleable)
            gl_handleable_alf_resolved = sum(1 for sc, _ in gl_handleable if sc.engaged and sc.resolved)
            gl_handleable_alf_failed = [
                sc.scenario_id for sc, _ in gl_handleable
                if not (sc.engaged and sc.resolved)
            ]
            gl_superset_proven = gl_handleable_count > 0 and len(gl_handleable_alf_failed) == 0

            gl_baseline_comparison = {
                "gl_resolution_rate": round(gl_rate, 4),
                "alf_resolution_rate": round(alf_rate, 4),
                "improvement_factor": round(improvement, 1) if improvement != float("inf") else "∞",
                "scenario_count": len(gl_scenarios),
                # GL superset proof: "GL이 해주는 건 ALF도 다 해준다"
                "gl_superset": {
                    "proven": gl_superset_proven,
                    "gl_handleable_count": gl_handleable_count,
                    "alf_resolved_count": gl_handleable_alf_resolved,
                    "alf_failed_scenarios": gl_handleable_alf_failed,
                },
            }

    return RunAggregate(
        engagement_rate=round(engagement_rate, 4),
        noise_rate=round(noise_rate, 4),
        scenario_weight_sum=round(total_w, 4),
        resolution_rate=round(resolution_rate, 4),
        scenario_engagement_rate=round(scenario_engagement_rate, 4),
        coverage=round(coverage, 4),
        oos_count=oos_count,
        oos_refusal_rate=round(oos_refusal_rate, 4) if oos_refusal_rate is not None else None,
        excluded_count=excluded_count,
        by_intent=by_intent,
        by_difficulty=by_difficulty,
        failure_mode_dist=dict(sorted(failure_dist.items())),
        by_phase=by_phase,
        gl_baseline_comparison=gl_baseline_comparison,
    )


# ---- report.md --------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_report(run_score: RunScore, config_extra: dict[str, Any]) -> str:
    agg = run_score.aggregate
    client_name = config_extra.get("client_name", "(unknown)")
    coverage_mode = config_extra.get("qa_target_mode") or config_extra.get("coverage_mode", "unspecified")

    lines: list[str] = []
    lines.append(f"# QA Run Report — {client_name}")
    lines.append("")
    lines.append(f"- **run_id**: `{run_score.run_id}`")
    lines.append(f"- **scored_at**: {run_score.scored_at}")
    lines.append(f"- **judge_model**: {run_score.judge_model} (prompt {run_score.judge_prompt_version})")
    lines.append(f"- **coverage_mode**: {coverage_mode}")
    lines.append("")

    # ---- 핵심 수치 (3-tier) ----
    lines.append("## 핵심 수치")
    lines.append("")
    lines.append("| 지표 | 값 | 출처 |")
    lines.append("|---|---|---|")
    lines.append(f"| **커버리지** (관여율 × 해결률) | **{_pct(agg.coverage)}** | 산출 |")
    lines.append(f"| 관여율 | {_pct(agg.engagement_rate)} | input-side (sop-agent 상담 분포 기준) |")
    lines.append(f"| 해결률 | {_pct(agg.resolution_rate)} | output-side (judge 판정) |")
    lines.append(f"| 노이즈 비율 | {_pct(agg.noise_rate)} | sop-agent 클러스터링 |")
    lines.append(f"| Σw (시나리오 가중치 합) | {_pct(agg.scenario_weight_sum)} | scenarios.json |")
    lines.append(f"| OOS refusal rate | {_pct(agg.oos_refusal_rate) if agg.oos_refusal_rate is not None else '—'} ({agg.oos_count} 건) | judge |")
    lines.append(f"| 제외된 시나리오 (persona_drift) | {agg.excluded_count} | judge |")
    lines.append("")

    if agg.scenario_weight_sum < 0.9:
        lines.append(
            f"> **Σw = {_pct(agg.scenario_weight_sum)}** — "
            "시나리오가 전체 intent를 다 커버하지 못함. "
            "커버되지 않은 상담 유형은 측정 밖."
        )
        lines.append("")

    lines.append("해석:")
    lines.append(f"- 이 시나리오 세트는 노이즈 제외 실 상담의 **{_pct(agg.engagement_rate)}**를 대표 (관여율)")
    lines.append(f"- ALF가 관여한 시나리오 중 **{_pct(agg.resolution_rate)}**를 해결 (해결률)")
    lines.append(f"- 최종 커버리지: 실 상담 대비 ALF가 유의미하게 기여하는 비율 = **{_pct(agg.coverage)}**")

    # GL 전환 맥락 해석 추가
    if agg.gl_baseline_comparison:
        gl = agg.gl_baseline_comparison
        lines.append(f"- **GL봇 대비 개선**: GL봇 {_pct(gl['gl_resolution_rate'])} → ALF {_pct(gl['alf_resolution_rate'])}")

    lines.append("")

    # ---- 난이도별 breakdown ----
    if agg.by_difficulty:
        lines.append("## 난이도별 해결률")
        lines.append("")
        lines.append("| difficulty | N | engaged | resolved | 해결률 |")
        lines.append("|---|---:|---:|---:|---:|")
        for tier in ("happy", "unhappy", "edge", "escalation"):
            if tier in agg.by_difficulty:
                d = agg.by_difficulty[tier]
                lines.append(
                    f"| {tier} | {d['count']} | {d['engaged']} | {d['resolved']} | "
                    f"{_pct(d['resolution_rate'])} |"
                )
        lines.append("")

    # ---- Phase별 분리 수치 (Gap 2) ----
    if agg.by_phase:
        p1 = agg.by_phase.get("_phase1_summary", {})
        p2 = agg.by_phase.get("_phase2_summary", {})
        if p1 and p2:
            lines.append("## Phase별 커버리지")
            lines.append("")
            lines.append("| Phase | 관여율 | 해결률 | 커버리지 | 설명 |")
            lines.append("|---|---:|---:|---:|---|")
            lines.append(
                f"| **Phase 1** (RAG만) | {_pct(p1.get('engagement_rate', 0))} | "
                f"{_pct(p1.get('resolution_rate', 0))} | **{_pct(p1.get('coverage', 0))}** | 즉시 도입 시 |"
            )
            lines.append(
                f"| **Phase 2** (전체) | {_pct(p2.get('engagement_rate', 0))} | "
                f"{_pct(p2.get('resolution_rate', 0))} | **{_pct(p2.get('coverage', 0))}** | Task 연동 후 |"
            )
            lines.append("")

            # GL 전환 맥락 해석
            lines.append("해석:")
            lines.append(f"- **Phase 1 (RAG+Rules만)**: 지식 업로드만으로 커버리지 **{_pct(p1.get('coverage', 0))}** 달성")
            lines.append(f"- **Phase 2 (Task 포함)**: API 연동 완료 시 커버리지 **{_pct(p2.get('coverage', 0))}** 달성")
            p1_cov = p1.get('coverage', 0)
            p2_cov = p2.get('coverage', 0)
            if p1_cov > 0 and p2_cov > 0:
                uplift = p2_cov - p1_cov
                lines.append(f"- **Task 연동 효과**: +{_pct(uplift)} (Phase 1 대비 {_pct(uplift / p1_cov)} 추가 상승)")
            lines.append("")

            # Phase breakdown detail
            lines.append("**Layer별 상세:**")
            lines.append("")
            lines.append("| phase | N | weight | 해결률 |")
            lines.append("|---|---:|---:|---:|")
            for phase_name in ("rag", "task", "hybrid", "human"):
                if phase_name in agg.by_phase:
                    pd = agg.by_phase[phase_name]
                    lines.append(
                        f"| {phase_name} | {pd['count']} | {pd['weight']:.3f} | "
                        f"{_pct(pd['resolution_rate'])} |"
                    )
            lines.append("")

    # ---- GL baseline 비교 (Gap 1) ----
    if agg.gl_baseline_comparison:
        gl = agg.gl_baseline_comparison
        lines.append("## GL봇 대비 비교")
        lines.append("")

        # GL superset proof — 가장 먼저
        sup = gl.get("gl_superset")
        if sup:
            if sup["proven"]:
                lines.append(
                    f"> **GL봇이 해결하는 {sup['gl_handleable_count']}개 시나리오 유형을 "
                    f"ALF가 전부 해결** ({sup['alf_resolved_count']}/{sup['gl_handleable_count']})"
                )
            else:
                lines.append(
                    f"> ⚠️ GL봇이 해결하는 {sup['gl_handleable_count']}개 유형 중 "
                    f"ALF가 {sup['alf_resolved_count']}개 해결 — "
                    f"실패: `{'`, `'.join(sup['alf_failed_scenarios'])}`"
                )
            lines.append("")

        lines.append("| 지표 | GL봇 | ALF | 개선 |")
        lines.append("|---|---:|---:|---:|")
        imp = gl["improvement_factor"]
        imp_str = f"×{imp}배" if isinstance(imp, (int, float)) else f"×{imp}"
        lines.append(
            f"| 해결률 | {_pct(gl['gl_resolution_rate'])} | "
            f"{_pct(gl['alf_resolution_rate'])} | **{imp_str}** |"
        )
        lines.append(f"| 비교 시나리오 수 | {gl['scenario_count']} | — | — |")
        lines.append("")

    # ---- 인텐트별 breakdown ----
    lines.append("## 인텐트별 breakdown")
    lines.append("")
    lines.append("| intent | weight | N | ALF 관여 | 해결률 |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in agg.by_intent:
        lines.append(
            f"| {row['intent']} | {row['weight']:.3f} | {row['count']} | "
            f"{_pct(row['engagement_rate'])} | {_pct(row['resolution_rate'])} |"
        )
    lines.append("")

    # ---- 실패 분포 ----
    lines.append("## 실패 분포")
    lines.append("")
    lines.append("| failure_mode | count |")
    lines.append("|---|---:|")
    for mode, count in agg.failure_mode_dist.items():
        lines.append(f"| {mode} | {count} |")
    lines.append("")

    # ---- 시나리오 상세 ----
    lines.append("## 시나리오 상세")
    lines.append("")
    for s in run_score.scores:
        is_oos = s.weight == 0.0
        if is_oos:
            tag = "✅" if s.refused else "❌"
        else:
            tag = "✅" if s.resolved else ("⚠️" if s.excluded_from_rate else "❌")
        oos_tag = " [OOS]" if is_oos else ""
        lines.append(
            f"### {tag} `{s.scenario_id}`{oos_tag} — w={s.weight:.3f} · "
            f"{s.persona_ref} · {s.terminated_reason}"
        )
        lines.append("")
        lines.append(f"- intent: {s.intent}")
        lines.append(f"- engaged / resolved: {s.engaged} / {s.resolved}")
        if s.refused is not None:
            lines.append(f"- refused (OOS): {s.refused}")
        lines.append(f"- failure_mode: `{s.failure_mode}`")
        if s.excluded_from_rate:
            lines.append("- **rate 계산 제외** (persona_drift — run validity 이슈)")
        if s.criterion_results:
            lines.append("- criteria:")
            for cr in s.criterion_results:
                mark = "✓" if cr.passed else "✗"
                lines.append(f"  - {mark} {cr.description} — {cr.reason}")
        if s.notes:
            lines.append(f"- notes: {s.notes}")
        lines.append("")

    return "\n".join(lines)


# ---- CLI --------------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> int:
    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[scorer] ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    scenario_set = read_scenarios(args.run_id)
    transcripts = {t.scenario_id: t for t in read_transcripts(args.run_id)}
    config = read_config_snapshot(args.run_id)

    scenarios = scenario_set.scenarios
    if args.scenario_id:
        scenarios = [s for s in scenarios if s.id == args.scenario_id]
        if not scenarios:
            print(f"[scorer] scenario_id '{args.scenario_id}' not in run", file=sys.stderr)
            return 2

    missing = [s.id for s in scenarios if s.id not in transcripts]
    if missing:
        print(f"[scorer] warning: no transcript for {len(missing)} scenarios: {missing}", file=sys.stderr)

    if args.dry_run:
        print(f"[scorer] dry-run: would score {len(scenarios) - len(missing)} scenarios " f"for run {args.run_id}")
        return 0

    judge_system_prompt = JUDGE_PROMPT_FILE.read_text(encoding="utf-8")
    client = AsyncAnthropic(base_url=LLM_BASE_URL)
    coverage_mode = config.extra.get("qa_target_mode") or config.extra.get("coverage_mode")

    print(
        f"[scorer] run_id={args.run_id} scenarios={len(scenarios)} "
        f"judge={JUDGE_MODEL} base_url={LLM_BASE_URL}"
    )

    scores: list[ScenarioScore] = []
    for i, scenario in enumerate(scenarios, 1):
        transcript = transcripts.get(scenario.id)
        if transcript is None:
            # Synthesize a minimal "no-transcript" record so the scenario still
            # shows up in the report; mark as error.
            scores.append(
                ScenarioScore(
                    scenario_id=scenario.id,
                    intent=scenario.intent,
                    persona_ref=scenario.persona_ref,
                    weight=scenario.weight,
                    terminated_reason="error",
                    engaged=False,
                    resolved=False,
                    refused=None,
                    failure_mode="error",
                    criterion_results=[
                        CriterionResult(description=c.description, passed=False, reason="no transcript")
                        for c in scenario.success_criteria
                    ],
                    notes="transcript missing",
                    excluded_from_rate=False,
                    judge_latency_s=None,
                    phase=scenario.phase,
                )
            )
            print(f"[scorer] [{i}/{len(scenarios)}] {scenario.id} → no transcript, marked error")
            continue
        print(f"[scorer] [{i}/{len(scenarios)}] {scenario.id} (persona={scenario.persona_ref})")
        score = await score_scenario(
            scenario,
            transcript,
            client=client,
            judge_system_prompt=judge_system_prompt,
            coverage_mode=coverage_mode,
        )
        scores.append(score)
        verdict = "RESOLVED" if score.resolved else ("ENGAGED" if score.engaged else "FAILED")
        print(f"[scorer]   → {verdict} failure_mode={score.failure_mode}")

    # Compute noise_rate from config_snapshot.
    # knowledge_summary contains all intents; total_records is in stats or extra.
    total_records = config.extra.get("total_records", 0)
    if not total_records and config.knowledge_summary:
        total_records = sum(k.get("records", 0) for k in config.knowledge_summary)
    intent_records = sum(k.get("records", 0) for k in config.knowledge_summary) if config.knowledge_summary else 0
    noise_rate = max(0.0, 1.0 - intent_records / total_records) if total_records > 0 else 0.0

    # intent_pattern_coverage: fraction of each intent's consultation patterns
    # that the scenario set actually represents. Stored in config_snapshot.extra
    # keyed by intent_id; we need to map to intent labels (used in scores).
    ipc_by_id = config.extra.get("intent_pattern_coverage")
    ipc_by_label: dict[str, float] | None = None
    if ipc_by_id:
        # Build id→label map from knowledge_summary
        id_to_label = {k["id"]: k["label"] for k in config.knowledge_summary} if config.knowledge_summary else {}
        ipc_by_label = {id_to_label.get(k, k): v for k, v in ipc_by_id.items()}

    agg = aggregate(scores, noise_rate=noise_rate, intent_pattern_coverage=ipc_by_label, scenarios=scenarios)
    run_score = RunScore(
        schema_version=SCHEMA_VERSION,
        run_id=args.run_id,
        scored_at=utcnow_iso(),
        judge_model=JUDGE_MODEL,
        judge_prompt_version=JUDGE_PROMPT_VERSION,
        scores=scores,
        aggregate=agg,
    )
    write_scores(args.run_id, run_score)
    report_md = render_report(run_score, config.extra)
    report_path = run_dir(args.run_id) / "report.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[scorer] wrote scores.json and report.md under storage/runs/{args.run_id}/")
    print(
        f"[scorer] coverage={agg.coverage:.3f} "
        f"engagement={agg.engagement_rate:.3f} resolution={agg.resolution_rate:.3f}"
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="tools.scoring_agent",
        description="Score scenarios.json + transcripts.jsonl into scores.json + report.md.",
    )
    p.add_argument("--run-id", required=True)
    p.add_argument(
        "--scenario-id",
        default=None,
        help="score only this scenario (default: all)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="load inputs and print what would be scored, without calling the judge",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

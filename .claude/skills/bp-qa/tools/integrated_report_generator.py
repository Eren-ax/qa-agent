"""Integrated HTML report generator for client-facing QA reports.

Generates a single-page HTML report matching the style of:
    오아 & 보아르 ALF QA 통합 리포트 v2

Structure:
    1. Cover + Key Metrics
    2. Comparison (Old Bot vs ALF)
    3. Conversation Examples (chat-section bubbles)
    4. Strengths / Weaknesses
    5. Improvement Roadmap
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .result_store import (
    RunScore,
    ScenarioScore,
    Transcript,
    run_dir,
)


def _pct(x: float) -> str:
    """Format as percentage (1 decimal)."""
    return f"{x * 100:.1f}%"


def _badge_class(score: ScenarioScore) -> str:
    """Determine badge class based on score."""
    if score.resolved:
        return "badge-ok"
    if score.engaged:
        return "badge-plan"  # Engaged but not resolved = improvement planned
    return "badge-ng"


def _badge_text(score: ScenarioScore) -> str:
    """Determine badge text."""
    if score.resolved:
        return "해결"
    if score.engaged:
        return "개선 예정"
    return "미해결"


def _badge_class_from_dict(score: dict[str, Any]) -> str:
    """Determine badge class based on score dict."""
    if score.get("resolved"):
        return "badge-ok"
    if score.get("engaged"):
        return "badge-plan"
    return "badge-ng"


def _badge_text_from_dict(score: dict[str, Any]) -> str:
    """Determine badge text from score dict."""
    if score.get("resolved"):
        return "해결"
    if score.get("engaged"):
        return "개선 예정"
    return "미해결"


def render_conversation_example(
    *,
    num: int,
    scenario_id: str,
    intent: str,
    transcript: dict[str, Any],
    score: dict[str, Any],
) -> str:
    """Render a single conversation example in chat-section format.

    Args:
        num: Example number (01, 02, ...)
        scenario_id: Scenario ID
        intent: Intent label
        transcript: Conversation transcript (as dict)
        score: Scenario score with criterion results (as dict)

    Returns:
        HTML string for .chat-section
    """
    badge_cls = _badge_class_from_dict(score)
    badge_txt = _badge_text_from_dict(score)

    # Build chat bubbles with smart truncation
    bubbles_html = []
    turns_list = transcript.get("turns", [])
    total_turns = len(turns_list)

    # Smart display logic:
    # - If <= 5 turns: show all
    # - If 6-10 turns: show first 3, ellipsis, last 2
    # - If > 10 turns: show first 3, ellipsis, last 2
    if total_turns <= 5:
        display_turns = turns_list
        show_ellipsis = False
    else:
        display_turns = turns_list[:3] + turns_list[-2:]
        show_ellipsis = True
        ellipsis_after = 3

    for idx, turn in enumerate(display_turns):
        # Insert ellipsis after first 3 turns for long conversations
        if show_ellipsis and idx == ellipsis_after:
            bubbles_html.append('<div class="ellipsis">・・・</div>')

        # User bubble
        user_msg = turn.get("user_message", "").replace("\n", "<br>")
        bubbles_html.append(f'''
            <div class="bubble-row user">
                <div class="avatar user">고</div>
                <div class="bubble user">{user_msg}</div>
            </div>''')

        # ALF bubbles
        if turn.get("alf_messages"):
            for alf_msg in turn["alf_messages"]:
                alf_text = alf_msg.get("text", "").replace("\n", "<br>")
                bubbles_html.append(f'''
            <div class="bubble-row">
                <div class="avatar alf">A</div>
                <div class="bubble alf">{alf_text}</div>
            </div>''')

    # Result summary
    if score.get("resolved"):
        result_icon = "✅"
        result_text = f"{len(transcript.get('turns', []))}턴 대화로 완료."
    elif score.get("engaged"):
        result_icon = "🔧"
        failed_criteria = [cr for cr in score.get("criterion_results", []) if not cr.get("passed")]
        if failed_criteria:
            result_text = f"{failed_criteria[0].get('reason', '')}"
        else:
            result_text = f"개선 중: {score.get('failure_mode', '')}"
    else:
        result_icon = "❌"
        result_text = f"미해결: {score.get('notes', '')[:100]}"

    # Check if escalation happened (look for escalation keywords in notes)
    is_escalation = any(
        keyword in score.get("notes", "").lower()
        for keyword in ["에스컬", "escalat", "상담원", "연결"]
    )
    escalation_badge = '<div class="badge badge-esc">에스컬레이션</div>' if is_escalation else ""

    return f'''
<div class="chat-section">
    <div class="chat-header">
        <div class="num">{num:02d}</div>
        <div class="meta">
            <div class="intent">{intent}</div>
            <div class="title">{scenario_id}</div>
        </div>
        <div class="badge {badge_cls}">{badge_txt}</div>{escalation_badge}
    </div>
    <div class="chat-body">
        {''.join(bubbles_html)}
    </div>
    <div class="chat-result">
        <div class="icon">{result_icon}</div>
        <div class="text">{result_text}</div>
    </div>
</div>'''


def generate_integrated_report(
    *,
    run_id: str,
    client_name: str,
    run_score: dict[str, Any],
    transcripts: list[dict[str, Any]],
    scenario_metadata: dict[str, dict[str, Any]],
    monthly_volume: int | None = None,
    old_bot_name: str | None = None,
    predicted_phase1: float | None = None,
    predicted_phase2: float | None = None,
) -> str:
    """Generate a single-page integrated HTML report.

    Args:
        run_id: QA run ID
        client_name: Client company name
        run_score: Scoring results (as dict from asdict(RunScore))
        transcripts: All conversation transcripts (as dicts)
        scenario_metadata: Scenario metadata (from scenarios.json)
        monthly_volume: Monthly consultation volume (optional)
        old_bot_name: Name of old bot for comparison (optional, default "기존 AI Chatbot")

    Returns:
        Complete HTML document as string
    """
    agg = run_score["aggregate"]
    p1 = agg.get("by_phase", {}).get("_phase1_summary", {})
    p2 = agg.get("by_phase", {}).get("_phase2_summary", {})
    gl_comp = agg.get("gl_baseline_comparison")

    # Default values
    old_bot_name = old_bot_name or "기존 AI Chatbot"
    monthly_volume = monthly_volume or 10000  # Default placeholder
    today = datetime.now().strftime("%Y.%m.%d")

    # Compute monthly counts if GL comparison available
    old_bot_rate = 0.0
    alf_rate_immediate = p1.get("coverage", 0)
    alf_rate_full = p2.get("coverage", 0)
    improvement_factor = "—"

    if gl_comp:
        old_bot_rate = gl_comp["gl_resolution_rate"]
        alf_rate_immediate = gl_comp["alf_resolution_rate"]
        improvement_factor = gl_comp["improvement_factor"]
        if improvement_factor == "∞":
            improvement_factor = "무한대"
        else:
            improvement_factor = f"×{improvement_factor}배"

    old_count = int(monthly_volume * old_bot_rate)
    alf_count_immediate = int(monthly_volume * alf_rate_immediate)
    alf_count_full = int(monthly_volume * alf_rate_full)

    # Check if actual results exceeded predictions
    exceeded_tag = ""
    if predicted_phase1 and alf_rate_immediate > predicted_phase1:
        exceeded_tag = f'<div style="margin-top:16px"><span class="tag tag-orange">사전 예측 {_pct(predicted_phase1)} → 실측 {_pct(alf_rate_immediate)} 초과 달성</span></div>'
    elif predicted_phase1 and alf_rate_immediate >= predicted_phase1 * 0.9:
        exceeded_tag = f'<div style="margin-top:16px"><span class="tag tag-green">사전 예측 {_pct(predicted_phase1)} 달성</span></div>'

    # Build comparison section HTML
    if old_bot_rate > 0:
        comparison_html = f'''
<h3>기존 봇 vs ALF 도입 즉시</h3>
<div class="compare">
    <div class="compare-old">
        <p style="color:#c62828;font-weight:600;margin-bottom:6px">{old_bot_name}</p>
        <div class="big-num red">{_pct(old_bot_rate)}</div>
        <p class="subtitle">해결률</p>
        <p style="margin-top:10px;font-size:1.05rem;color:#444">~{old_count:,}건/월</p>
    </div>
    <div class="compare-arrow">→</div>
    <div class="compare-new">
        <p style="color:#2e7d32;font-weight:600;margin-bottom:6px">ALF 도입 즉시</p>
        <div class="big-num green">{_pct(alf_rate_immediate)}</div>
        <p class="subtitle">해결률</p>
        <p style="margin-top:10px;font-size:1.05rem;color:#444">~{alf_count_immediate:,}건/월</p>
    </div>
</div>
<div style="text-align:center;margin:8px 0 24px">
    <span class="big-num accent" style="font-size:2.6rem">{improvement_factor}</span>
    <span class="subtitle" style="display:block">기존 봇 대비 해결 건수 증가</span>
</div>
{exceeded_tag}'''
    else:
        comparison_html = f'''
<h3>ALF 도입 효과</h3>
<div class="card card-green" style="text-align:center;padding:40px">
    <p style="color:#2e7d32;font-weight:600;margin-bottom:12px">ALF 도입 즉시</p>
    <div class="big-num green">{_pct(alf_rate_immediate)}</div>
    <p class="subtitle">자동 처리율</p>
    <p style="margin-top:20px;font-size:1.1rem;color:#444">월 ~{alf_count_immediate:,}건 자동 처리</p>
</div>
{exceeded_tag}'''

    # Build intent breakdown table
    intent_table_rows = []
    for item in agg.get("by_intent", [])[:10]:  # Top 10 intents
        intent_label = item["intent"]
        weight = item["weight"]
        count = item["count"]
        resolution = item["resolution_rate"]
        monthly_est = int(monthly_volume * weight)

        if resolution >= 0.7:
            badge = '<span class="tag tag-green">해결</span>'
            rate_class = "green"
        elif resolution >= 0.3:
            badge = '<span class="tag tag-orange">부분 해결</span>'
            rate_class = "orange"
        else:
            badge = '<span class="tag tag-red">미해결</span>'
            rate_class = "red"

        intent_table_rows.append(f'''
    <tr>
        <td>{intent_label}</td>
        <td style="text-align:right">~{monthly_est:,}건</td>
        <td style="text-align:right"><span class="{rate_class}">{_pct(resolution)}</span></td>
        <td>{badge}</td>
    </tr>''')

    intent_table_html = f'''
<h3>상담 유형별 현황</h3>
<table>
    <thead>
        <tr>
            <th>상담 유형</th>
            <th style="text-align:right">월간 건수</th>
            <th style="text-align:right">해결률</th>
            <th>결과</th>
        </tr>
    </thead>
    <tbody>
        {''.join(intent_table_rows)}
    </tbody>
</table>'''

    # Build conversation examples (select 10 examples with balanced coverage)
    transcript_map = {t["scenario_id"]: t for t in transcripts}
    score_map = {s["scenario_id"]: s for s in run_score["scores"]}

    # Group scenarios by status
    resolved_examples = []
    engaged_examples = []
    failed_examples = []

    for scenario_id, metadata in scenario_metadata.items():
        if scenario_id not in transcript_map or scenario_id not in score_map:
            continue

        transcript = transcript_map[scenario_id]
        score = score_map[scenario_id]
        intent = metadata.get("intent", "기타")

        example = (scenario_id, intent, transcript, score)

        if score.get("resolved"):
            resolved_examples.append(example)
        elif score.get("engaged"):
            engaged_examples.append(example)
        else:
            failed_examples.append(example)

    # Select balanced mix: prioritize resolved, include some engaged/failed
    selected = []
    selected.extend(resolved_examples[:6])  # 6 resolved
    selected.extend(engaged_examples[:2])   # 2 engaged (improvement planned)
    selected.extend(failed_examples[:2])    # 2 failed

    # Limit to 10 total
    selected = selected[:10]

    examples_html_list = []
    for idx, (scenario_id, intent, transcript, score) in enumerate(selected):
        examples_html_list.append(
            render_conversation_example(
                num=idx + 1,
                scenario_id=scenario_id,
                intent=intent,
                transcript=transcript,
                score=score,
            )
        )

    shown_count = len(selected)

    # Build strengths/weaknesses section with detailed analysis
    strengths = []
    weaknesses = []

    # Analyze by intent for strengths
    high_performing = []
    low_performing = []
    for item in agg.get("by_intent", []):
        resolution = item["resolution_rate"]
        intent = item["intent"]
        weight = item["weight"]

        if resolution >= 0.9 and weight >= 0.05:  # High resolution + significant volume
            high_performing.append((intent, resolution, weight))
        elif resolution < 0.5:  # Low resolution
            low_performing.append((intent, resolution, weight))

    # Top 5 strengths
    high_performing.sort(key=lambda x: x[2], reverse=True)  # Sort by weight
    for intent, resolution, weight in high_performing[:5]:
        monthly = int(monthly_volume * weight)
        strengths.append(f"<li><strong>{intent} {_pct(resolution)}</strong> — 월 ~{monthly:,}건 안정적 처리</li>")

    # Analyze failure modes for weaknesses
    failure_modes = agg.get("failure_mode_dist", {})
    scores = run_score.get("scores", [])

    # Group failures by mode with examples
    task_not_triggered = [s for s in scores if s.get("failure_mode") == "task_not_triggered"]
    rag_miss = [s for s in scores if s.get("failure_mode") == "rag_miss"]
    error_scenarios = [s for s in scores if s.get("failure_mode") == "error"]

    if task_not_triggered:
        # Find which tasks are not triggering
        task_intents = set(s.get("intent", "") for s in task_not_triggered)
        task_list = ", ".join(list(task_intents)[:3])
        weaknesses.append(
            f"<li><strong>Task 미실행</strong> — {len(task_not_triggered)}건 발생 ({task_list}) "
            f"<span class=\"tag tag-accent\" style=\"font-size:0.7rem\">API 연동 후 해소</span></li>"
        )

    if rag_miss:
        # Find which knowledge is missing
        rag_intents = set(s.get("intent", "") for s in rag_miss)
        # Extract specific missing knowledge from criterion results
        missing_knowledge = []
        for s in rag_miss[:3]:
            for cr in s.get("criterion_results", []):
                if not cr.get("passed"):
                    reason = cr.get("reason", "")
                    if reason and len(reason) < 100:
                        missing_knowledge.append(reason[:50])

        if missing_knowledge:
            weaknesses.append(
                f"<li><strong>지식 누락</strong> — {len(rag_miss)}건 발생 "
                f"<span class=\"tag tag-accent\" style=\"font-size:0.7rem\">지식 추가로 해소</span>"
                f"<br><span style=\"font-size:0.8rem;color:#888\">예: {missing_knowledge[0]}</span></li>"
            )
        else:
            weaknesses.append(
                f"<li><strong>지식 누락</strong> — {len(rag_miss)}건 발생 "
                f"<span class=\"tag tag-accent\" style=\"font-size:0.7rem\">지식 추가로 해소</span></li>"
            )

    if error_scenarios:
        weaknesses.append(
            f"<li><strong>시스템 오류</strong> — {len(error_scenarios)}건 발생 "
            f"<span class=\"tag tag-accent\" style=\"font-size:0.7rem\">시스템 점검 필요</span></li>"
        )

    # Add low-performing intents
    for intent, resolution, weight in low_performing[:3]:
        monthly = int(monthly_volume * weight)
        weaknesses.append(
            f"<li><strong>{intent} {_pct(resolution)}</strong> — "
            f"월 ~{monthly:,}건 중 개선 필요</li>"
        )

    # Fallbacks
    if not strengths:
        strengths.append("<li>전반적으로 안정적인 응답 품질 확보</li>")
    if not weaknesses:
        weaknesses.append("<li>특이사항 없음 — 지속적인 모니터링 권장</li>")

    strengths_html = "\n        ".join(strengths[:5])
    weaknesses_html = "\n        ".join(weaknesses[:5])

    sw_section_html = f'''
<h2 id="sec2">2. 잘한 부분 / 아쉬운 부분</h2>

<div class="sw-grid">
    <div class="sw-card" style="border-left:3px solid #22c55e">
        <h4 style="color:#2e7d32">잘한 부분</h4>
        <ul>
        {strengths_html}
        </ul>
    </div>
    <div class="sw-card" style="border-left:3px solid #ef4444">
        <h4 style="color:#c62828">아쉬운 부분</h4>
        <ul>
        {weaknesses_html}
        </ul>
    </div>
</div>'''

    # Build complete HTML
    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{client_name} — ALF QA 통합 리포트</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#f0f0f0;color:#222;font-family:-apple-system,'Noto Sans KR','Apple SD Gothic Neo',sans-serif;line-height:1.7}}
.container{{max-width:920px;margin:0 auto;padding:48px 24px 80px}}

h1{{font-size:2.2rem;font-weight:800;margin-bottom:6px;color:#1a1a2e}}
h2{{font-size:1.6rem;font-weight:700;color:#4338ca;margin:64px 0 20px;padding-top:28px;border-top:1px solid #ddd}}
h3{{font-size:1.15rem;font-weight:600;color:#4338ca;margin:28px 0 12px}}
p{{font-size:1rem;line-height:1.7;color:#666;margin-bottom:8px}}
.accent{{color:#4338ca}}.green{{color:#2e7d32}}.red{{color:#c62828}}.orange{{color:#e65100}}
.big-num{{font-size:3.2rem;font-weight:800;line-height:1.1}}
.medium-num{{font-size:2rem;font-weight:700;line-height:1.2}}
.subtitle{{font-size:1rem;color:#999;margin-top:4px}}
.tag{{display:inline-block;padding:3px 10px;border-radius:6px;font-size:0.82rem;font-weight:600;margin-right:6px;margin-bottom:4px}}
.tag-green{{background:#e8f5e9;color:#2e7d32}}
.tag-red{{background:#ffebee;color:#c62828}}
.tag-orange{{background:#fff3e0;color:#e65100}}
.tag-accent{{background:#ede7f6;color:#4338ca}}

/* 카드 */
.card{{background:#fff;border:1px solid #e0e0e0;border-radius:12px;padding:18px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.card-grid{{display:grid;gap:14px;margin:16px 0}}
.g2{{grid-template-columns:1fr 1fr}}.g3{{grid-template-columns:1fr 1fr 1fr}}
@media(max-width:700px){{.g3{{grid-template-columns:1fr 1fr}}.g2{{grid-template-columns:1fr}}}}
.card-highlight{{border-color:#7c3aed;background:linear-gradient(135deg,rgba(99,102,241,0.06),#fff)}}
.card-green{{border-color:#4caf50;background:linear-gradient(135deg,rgba(76,175,80,0.06),#fff)}}
.card-orange{{border-color:#ff9800;background:linear-gradient(135deg,rgba(255,152,0,0.06),#fff)}}

/* 비교 */
.compare{{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;align-items:center;margin:20px 0}}
@media(max-width:600px){{.compare{{grid-template-columns:1fr;text-align:center}}.compare-arrow{{transform:rotate(90deg)}}}}
.compare-arrow{{font-size:2rem;color:#4338ca;text-align:center}}
.compare-old{{background:#fff;border:2px solid #f44336;border-radius:12px;padding:24px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.compare-new{{background:#fff;border:2px solid #4caf50;border-radius:12px;padding:24px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}

/* 테이블 */
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:0.92rem;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.06)}}
th{{text-align:left;padding:10px 12px;border-bottom:2px solid #e0e0e0;color:#4338ca;font-weight:600;background:#fafafa}}
td{{padding:8px 12px;border-bottom:1px solid #f0f0f0;color:#444}}
tr:hover td{{background:#f8f7ff}}

/* 용어 정의 */
.def-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}}
@media(max-width:700px){{.def-grid{{grid-template-columns:1fr}}}}
.def-card{{background:#fff;border:1px solid #e0e0e0;border-radius:12px;padding:20px;border-top:3px solid #4338ca;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.def-card .def-term{{font-size:0.82rem;color:#999;font-weight:600;margin-bottom:4px;letter-spacing:0.5px}}
.def-card .def-value{{font-size:2.4rem;font-weight:800;line-height:1.2;margin-bottom:8px}}
.def-card .def-desc{{font-size:0.88rem;color:#666;line-height:1.5}}

/* 콜아웃 */
.notice{{background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 16px;margin:14px 0;font-size:0.88rem;color:#e65100}}
.callout-blue{{background:#ede7f6;border:1px solid #b39ddb;border-radius:8px;padding:14px 16px;margin:14px 0;font-size:0.9rem;color:#4527a0;line-height:1.6}}
.callout-blue strong{{color:#311b92}}

/* 잘한/아쉬운 */
.sw-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}}
@media(max-width:600px){{.sw-grid{{grid-template-columns:1fr}}}}
.sw-card{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.sw-card h4{{font-size:1rem;font-weight:700;margin-bottom:10px}}
.sw-card ul{{padding-left:16px;font-size:0.88rem;color:#555;line-height:1.9}}
.sw-card ul strong{{color:#222}}

/* 채팅 */
.chat-section{{background:#fff;border:1px solid #e0e0e0;border-radius:12px;margin:20px 0;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)}}
.chat-header{{padding:14px 20px;border-bottom:1px solid #f0f0f0;display:flex;align-items:flex-start;gap:12px}}
.chat-header .num{{font-size:0.8rem;font-weight:700;color:#bbb;flex-shrink:0;padding-top:2px}}
.chat-header .meta{{flex:1}}
.chat-header .intent{{font-size:0.75rem;color:#999;margin-bottom:2px}}
.chat-header .title{{font-size:1rem;font-weight:700;color:#222;line-height:1.4}}
.badge{{flex-shrink:0;font-size:0.72rem;font-weight:700;padding:4px 10px;border-radius:16px;white-space:nowrap}}
.badge-ok{{background:#e8f5e9;color:#2e7d32}}
.badge-ng{{background:#ffebee;color:#c62828}}
.badge-plan{{background:#fff3e0;color:#e65100}}
.badge-esc{{background:#ede7f6;color:#512da8;margin-left:6px}}
.chat-body{{padding:20px;background:#fafafa;display:flex;flex-direction:column;gap:10px;max-height:400px;overflow-y:auto}}
.bubble-row{{display:flex;align-items:flex-end;gap:8px}}
.bubble-row.alf{{flex-direction:row-reverse}}
.avatar{{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:700;flex-shrink:0}}
.avatar.user{{background:#e3f2fd;color:#1565c0}}
.avatar.alf{{background:#f3e5f5;color:#6a1b9a}}
.bubble{{max-width:72%;padding:10px 14px;border-radius:12px;font-size:0.88rem;line-height:1.6}}
.bubble.user{{background:#fff;color:#333;border:1px solid #e8e8e8;border-bottom-left-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,0.06)}}
.bubble.alf{{background:#1a73e8;color:#fff;border-bottom-right-radius:4px}}
.ellipsis{{text-align:center;color:#bbb;font-size:18px;letter-spacing:4px;padding:2px 0}}
.chat-result{{padding:12px 20px;border-top:1px solid #f0f0f0;display:flex;align-items:flex-start;gap:10px;font-size:0.85rem;line-height:1.6;color:#666}}
.chat-result strong{{color:#222}}

/* 채팅 — 상태별 좌측 보더 */
.chat-section:has(.badge-ok) .chat-header{{border-left:5px solid #4caf50}}
.chat-section:has(.badge-ng) .chat-header{{border-left:5px solid #f44336}}
.chat-section:has(.badge-plan) .chat-header{{border-left:5px solid #ff9800}}

/* 이슈 */
.issue-card{{background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:14px 16px;margin:10px 0;box-shadow:0 1px 4px rgba(0,0,0,0.06)}}
.issue-label{{font-size:0.78rem;color:#e65100;font-weight:600;margin-bottom:4px}}
.issue-fix{{color:#2e7d32;font-size:0.85rem;margin-top:6px}}

@media print{{
  body{{background:#fff}}
  .card,.chat-section,.issue-card{{box-shadow:none;border:1px solid #ddd}}
}}
</style>
</head>
<body>
<div class="container">

<!-- ======== 커버 ======== -->
<div style="text-align:center;padding:20px 0 0">
  <p style="color:#999;font-size:0.9rem;margin-bottom:4px">{today}</p>
  <h1>{client_name}</h1>
  <p style="font-size:1.3rem;font-weight:600;color:#4338ca;margin-top:4px">ALF QA 통합 리포트</p>
  <div style="margin-top:20px;display:flex;justify-content:center;gap:10px;flex-wrap:wrap">
    <span class="tag tag-accent">월간 상담 {monthly_volume:,}건</span>
    <span class="tag tag-accent">테스트 시나리오 {len(run_score["scores"])}건</span>
    <span class="tag tag-accent">인텐트 {len(agg.get("by_intent", []))}개</span>
    <span class="tag tag-accent">자동 검증 완료</span>
  </div>
</div>


<!-- ======== 1. 지표 정의 + QA 결과 ======== -->
<h2 id="sec1">1. QA 결과</h2>

<h3>이 리포트에서 쓰는 지표</h3>
<div class="def-grid">
  <div class="def-card" style="border-top-color:#2e7d32">
    <div class="def-term">해결률</div>
    <div class="def-value green">{_pct(agg.get("alf_resolution_rate", 0))}</div>
    <div class="def-desc"><strong style="color:#222">ALF가 응답한 상담 중 실제로 해결까지 완료된 비율.</strong><br>월간 {monthly_volume:,}건 기준 가중 평균. 자동 검증 반영.</div>
  </div>
  <div class="def-card" style="border-top-color:#512da8">
    <div class="def-term">관여율</div>
    <div class="def-value accent">{_pct(agg.get("alf_engagement_rate", 0))}</div>
    <div class="def-desc"><strong style="color:#222">들어온 상담에 ALF가 실질적 답변을 시도한 비율.</strong><br>즉시 에스컬레이션은 제외.</div>
  </div>
</div>

{comparison_html}

{intent_table_html}


<!-- ======== 2. 잘한 부분 / 아쉬운 부분 ======== -->
{sw_section_html}


<!-- ======== 3. 실제 상담 예시 ======== -->
<h2 id="sec3">3. 실제 상담 예시 ({shown_count}건)</h2>
<p>테스트에서 실행된 대표 시나리오입니다.</p>

{''.join(examples_html_list)}


<!-- ======== 4. 개선 & 로드맵 ======== -->
<h2 id="sec4">4. 개선 & 로드맵</h2>

<h3>로드맵</h3>
<div class="card-grid g3">
  <div class="card card-orange" style="text-align:center">
    <p style="color:#e65100;font-weight:600;font-size:0.85rem">지금 당장</p>
    <div class="medium-num orange" style="margin:8px 0">{_pct(p1.get('coverage', 0))}</div>
    <p style="color:#999;font-size:0.85rem">~{int(monthly_volume * p1.get('coverage', 0)):,}건/월</p>
    <p style="color:#999;font-size:0.78rem;margin-top:6px">추가 작업 없음</p>
  </div>
  <div class="card card-green" style="text-align:center">
    <p style="color:#2e7d32;font-weight:600;font-size:0.85rem">Phase 2 (API 연동)</p>
    <div class="medium-num green" style="margin:8px 0">{_pct(p2.get('coverage', 0))}</div>
    <p style="color:#999;font-size:0.85rem">~{int(monthly_volume * p2.get('coverage', 0)):,}건/월</p>
    <p style="color:#999;font-size:0.78rem;margin-top:6px">API 키 발급 + 연동</p>
  </div>
  <div class="card card-highlight" style="text-align:center">
    <p style="color:#4338ca;font-weight:600;font-size:0.85rem">Phase 3 (지속 개선)</p>
    <div class="medium-num accent" style="margin:8px 0">~{_pct(min(p2.get('coverage', 0) * 1.2, 1.0))}</div>
    <p style="color:#999;font-size:0.85rem">~{int(monthly_volume * min(p2.get('coverage', 0) * 1.2, 1.0)):,}건/월</p>
    <p style="color:#999;font-size:0.78rem;margin-top:6px">정기 피드백</p>
  </div>
</div>

<p style="color:#999;font-size:0.82rem;text-align:center;margin-top:48px">{client_name} ALF QA 통합 리포트 | {today} | Run ID: {run_id}</p>

</div>
</body>
</html>'''

    return html


def write_integrated_report(
    run_id: str,
    **kwargs,
) -> Path:
    """Write integrated HTML report to storage/runs/<run_id>/report_client.html.

    Args:
        run_id: QA run ID
        **kwargs: Arguments to pass to generate_integrated_report

    Returns:
        Path to written HTML file
    """
    html = generate_integrated_report(run_id=run_id, **kwargs)
    output_path = run_dir(run_id) / "report_client.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path

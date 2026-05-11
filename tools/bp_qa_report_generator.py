"""Best Practice QA Report Generator - Generalized version.

Generates detailed BP vs ALF comparison reports with:
- Case-by-case Best Practice vs actual ALF conversation comparison
- 10-point QA scoring (accuracy 5 + completeness 3 + tone 2)
- Chat bubble UI for conversations
- Result categorization (success/partial/timeout/error)
- Both HTML and Markdown output

Usage:
    from tools.bp_qa_report_generator import generate_bp_qa_reports

    generate_bp_qa_reports(
        transcripts_path="storage/runs/run_xyz/transcripts.jsonl",
        output_dir="storage/runs/run_xyz",
        client_name="벨리에"
    )
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def calculate_qa_score(transcript: dict) -> tuple[float, list[str], str]:
    """Calculate QA score (10-point scale).

    Scoring:
    - Accuracy (5 points): Did ALF provide correct information?
    - Completeness (3 points): Did ALF cover all necessary information?
    - Tone (2 points): Was the tone appropriate and friendly?

    Args:
        transcript: Single transcript with turns and metadata

    Returns:
        (score, reasons, evaluation)
    """
    score = 0
    reasons = []

    status = transcript.get('terminated_reason', transcript.get('status', 'unknown'))
    turns = transcript.get('turns', [])
    bp_intent = transcript.get('bp_intent', '')
    bp_classification = transcript.get('bp_classification', '')

    # Critical errors
    if status == 'error':
        reasons.append("❌ 치명적 오류: error 상태로 종료")
        return 0.0, reasons, "치명적 오류로 0점 처리"

    # Check for </thinking> exposure
    for turn in turns:
        alf_messages = turn.get('alf_messages', [])
        for msg in alf_messages:
            text = msg.get('text', '')
            if '</thinking>' in text:
                reasons.append("❌ 치명적 오류: </thinking> 태그 노출")
                return 0.0, reasons, "내부 사고 과정이 고객에게 노출됨"

    # Check for no response
    if len(turns) == 0:
        reasons.append("❌ 치명적 오류: ALF 응답 없음")
        return 0.0, reasons, "고객 문의에 대한 응답이 전혀 없음"

    has_alf_response = any(turn.get('alf_messages', []) for turn in turns)
    if not has_alf_response:
        reasons.append("❌ 치명적 오류: ALF 응답 없음")
        return 0.0, reasons, "고객 문의에 대한 응답이 전혀 없음"

    # Accuracy (5 points)
    if status == 'completed':
        score += 5
        reasons.append("✅ 정확성 5/5: 고객 문의를 완전히 해결")
    elif status == 'escalated' or status == 'agent_escalated':
        if 'RAG' in bp_classification or 'Text Task' in bp_classification:
            # Should have been handled by bot
            score += 3
            reasons.append("⚠️ 정확성 3/5: 봇으로 처리 가능했으나 상담원 연결")
        else:
            # Function Task - escalation expected
            score += 5
            reasons.append("✅ 정확성 5/5: API 연동 필요 케이스, 상담원 연결 적절")
    elif status == 'max_turns':
        score += 2
        reasons.append("⚠️ 정확성 2/5: 타임아웃으로 완결하지 못함")
    else:
        score += 1
        reasons.append("❌ 정확성 1/5: 알 수 없는 상태")

    # Completeness (3 points)
    num_turns = len(turns)
    if status == 'completed':
        if num_turns <= 3:
            score += 3
            reasons.append("✅ 완결성 3/3: 짧은 대화로 빠르게 해결")
        elif num_turns <= 5:
            score += 2.5
            reasons.append("✅ 완결성 2.5/3: 적절한 대화로 해결")
        else:
            score += 2
            reasons.append("⚠️ 완결성 2/3: 대화가 다소 길었으나 해결")
    elif status == 'escalated' or status == 'agent_escalated':
        score += 2
        reasons.append("⚠️ 완결성 2/3: 상담원 연결로 일부 정보 제공")
    else:
        score += 1
        reasons.append("⚠️ 완결성 1/3: 정보 제공이 불완전함")

    # Tone (2 points)
    alf_messages = []
    for turn in turns:
        for msg in turn.get('alf_messages', []):
            alf_messages.append(msg.get('text', ''))

    # Check for negative patterns (but appropriate apologies are fine)
    has_appropriate_tone = True
    negative_patterns = ['오류', '실패', '문제가 발생']

    for msg in alf_messages:
        if any(pattern in msg for pattern in negative_patterns):
            has_appropriate_tone = False
            break

    if has_appropriate_tone:
        score += 2
        reasons.append("✅ 톤&매너 2/2: 친근하고 자연스러운 톤")
    else:
        score += 1.5
        reasons.append("⚠️ 톤&매너 1.5/2: 대체로 적절하나 일부 개선 필요")

    # Overall evaluation
    if score >= 9:
        evaluation = "🟢 우수: BP와 거의 동일한 수준의 응대"
    elif score >= 7:
        evaluation = "🟡 양호: 대부분 적절하나 일부 개선 필요"
    elif score >= 5:
        evaluation = "🟠 보통: 기본적인 응대는 하나 개선 여지 많음"
    else:
        evaluation = "🔴 미흡: 상당한 개선 필요"

    return score, reasons, evaluation


def categorize_result(status: str, score: float) -> str:
    """Categorize test result."""
    if status == 'error':
        return '🔴 오류'
    elif status == 'max_turns':
        return '🟠 타임아웃'
    elif status == 'completed' and score >= 8:
        return '🟢 성공'
    elif status in ['escalated', 'agent_escalated'] or (status == 'completed' and score >= 5):
        return '🟡 부분 성공'
    else:
        return '🔴 오류'


def calculate_metrics(transcript: dict) -> dict[str, Any]:
    """Calculate conversation metrics."""
    turns = transcript.get('turns', [])
    started_at = transcript.get('started_at')
    ended_at = transcript.get('ended_at')

    num_turns = len(turns)

    # Calculate response time
    if started_at and ended_at:
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
            response_time = (end - start).total_seconds()
        except:
            response_time = 0
    else:
        response_time = 0

    avg_response = response_time / num_turns if num_turns > 0 else 0

    return {
        'num_turns': num_turns,
        'response_time': response_time,
        'avg_response': avg_response
    }


def format_chat_bubble_html(turns: list[dict]) -> str:
    """Generate ChannelTalk-style chat bubble HTML."""
    if not turns:
        return '<p style="color: #999;">대화 내역 없음</p>'

    html = '<div style="max-width: 800px; margin: 20px 0;">'

    for turn in turns:
        user_message = turn.get('user_message', '').strip()
        alf_messages = turn.get('alf_messages', [])

        # User message
        if user_message:
            html += f'''
<div style="margin: 10px 0; text-align: left;">
    <div style="display: inline-block; max-width: 70%; background: white; border: 1px solid #e0e0e0; border-radius: 18px; padding: 12px 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
        <div style="font-size: 10px; color: #666; font-weight: 600; margin-bottom: 4px;">고객</div>
        <div style="line-height: 1.5; color: #333;">{user_message}</div>
    </div>
</div>
'''

        # ALF messages
        if alf_messages:
            alf_texts = [msg.get('text', '').strip() for msg in alf_messages if msg.get('text', '').strip()]
            if alf_texts:
                combined = '<br><br>'.join(alf_texts)
                html += f'''
<div style="margin: 10px 0; text-align: right;">
    <div style="display: inline-block; max-width: 70%; background: #e3f2fd; border-radius: 18px; padding: 12px 16px; text-align: left; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
        <div style="font-size: 10px; color: #1976d2; font-weight: 600; margin-bottom: 4px;">ALF</div>
        <div style="line-height: 1.5; color: #333;">{combined}</div>
    </div>
</div>
'''

    html += '</div>'
    return html


def format_chat_bubble_markdown(turns: list[dict]) -> str:
    """Format conversation for Markdown."""
    if not turns:
        return '*대화 내역 없음*\n'

    md = ''

    for turn in turns:
        user_message = turn.get('user_message', '').strip()
        alf_messages = turn.get('alf_messages', [])

        # User message
        if user_message:
            md += f'\n**고객:** {user_message}\n'

        # ALF messages
        if alf_messages:
            md += '\n**ALF:**\n'
            for msg in alf_messages:
                text = msg.get('text', '').strip()
                if text:
                    md += f'> {text}\n\n'

    return md


def generate_html_report(
    transcripts: list[dict],
    client_name: str,
    report_date: str | None = None,
) -> str:
    """Generate HTML report.

    Args:
        transcripts: List of transcript dicts from transcripts.jsonl
        client_name: Client name for the report
        report_date: Report generation date (default: today)

    Returns:
        Complete HTML document as string
    """
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{client_name} Best Practice QA 리포트</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ font-size: 32px; color: #1976d2; margin-bottom: 10px; }}
        .meta {{ color: #666; margin-bottom: 30px; font-size: 14px; }}
        h2 {{
            font-size: 28px;
            margin: 40px 0 20px 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 8px;
        }}
        h3 {{
            font-size: 20px;
            margin: 30px 0 15px 0;
            padding: 15px;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            border-radius: 6px;
        }}
        h4 {{ font-size: 16px; margin: 20px 0 10px 0; color: #1976d2; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; font-weight: 600; }}
        .case {{
            background: #fafafa;
            border-left: 4px solid #1976d2;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .case-header {{ font-size: 18px; font-weight: 600; margin-bottom: 10px; color: #1976d2; }}
        .case-meta {{ font-size: 14px; color: #666; margin-bottom: 15px; }}
        .metric {{ display: inline-block; background: #e3f2fd; padding: 8px 12px; margin: 5px; border-radius: 4px; font-size: 14px; }}
        .score {{ font-size: 24px; font-weight: 700; color: #4caf50; }}
        .score.low {{ color: #f44336; }}
        .score.medium {{ color: #ff9800; }}
        ul {{ margin: 10px 0 10px 20px; }}
        li {{ margin: 5px 0; }}
        .section-success {{ border-left-color: #4caf50; }}
        .section-partial {{ border-left-color: #ff9800; }}
        .section-timeout {{ border-left-color: #ff9800; }}
        .section-error {{ border-left-color: #f44336; }}
        a {{ color: #1976d2; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .bp-section {{ background: #f9f9f9; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .bp-message {{ margin: 5px 0; padding: 8px; border-left: 3px solid #ccc; background: white; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{client_name} Best Practice QA 리포트</h1>
        <div class="meta">
            <strong>생성일:</strong> {report_date}<br>
            <strong>총 케이스:</strong> {len(transcripts)}개
        </div>

        <h2>📊 전체 요약</h2>
"""

    # Analyze cases by result
    cases_by_result = defaultdict(list)

    for transcript in transcripts:
        score, reasons, evaluation = calculate_qa_score(transcript)
        metrics = calculate_metrics(transcript)

        status = transcript.get('terminated_reason', transcript.get('status', 'unknown'))
        result_category = categorize_result(status, score)

        cases_by_result[result_category].append({
            'transcript': transcript,
            'score': score,
            'reasons': reasons,
            'evaluation': evaluation,
            'metrics': metrics
        })

    # Summary table
    total = len(transcripts)
    summary_order = ['🟢 성공', '🟡 부분 성공', '🟠 타임아웃', '🔴 오류']

    html += "<table><thead><tr><th>결과</th><th>건수</th><th>비율</th><th>평균 QA Score</th></tr></thead><tbody>"

    for result in summary_order:
        cases = cases_by_result[result]
        count = len(cases)
        ratio = (count / total * 100) if total > 0 else 0
        avg_score = sum(c['score'] for c in cases) / count if count > 0 else 0
        html += f"<tr><td>{result}</td><td>{count}건</td><td>{ratio:.1f}%</td><td>{avg_score:.1f}점</td></tr>"

    html += "</tbody></table>"

    # Cases by result category
    section_classes = {
        '🟢 성공': 'section-success',
        '🟡 부분 성공': 'section-partial',
        '🟠 타임아웃': 'section-timeout',
        '🔴 오류': 'section-error'
    }

    for result in summary_order:
        cases = cases_by_result[result]
        if not cases:
            continue

        html += f"<h2>{result} ({len(cases)}건)</h2>"

        if result == '🟢 성공':
            html += "<p>ALF가 고객 문의를 완전히 해결한 케이스</p>"
        elif result == '🟡 부분 성공':
            html += "<p>일부 정보 제공 또는 상담원 연결로 처리한 케이스</p>"
        elif result == '🟠 타임아웃':
            html += "<p>대화가 최대 턴 수에 도달하여 종료된 케이스</p>"
        else:
            html += "<p>오류가 발생한 케이스</p>"

        for i, case in enumerate(cases, 1):
            transcript = case['transcript']

            bp_url = transcript.get('bp_url', '')
            bp_intent = transcript.get('bp_intent', '(의도 정보 없음)')
            bp_classification = transcript.get('bp_classification', '')
            initial_message = transcript.get('initial_message', '')

            section_class = section_classes.get(result, '')

            html += f'<div class="case {section_class}">'
            html += f'<div class="case-header">{i}. {bp_intent}</div>'
            html += f'<div class="case-meta">'
            if bp_url:
                html += f'<strong>Best Practice User Chat:</strong> <a href="{bp_url}" target="_blank">{bp_url}</a><br>'
            html += f'<strong>분류:</strong> {bp_classification}<br>'
            html += f'<strong>Scenario ID:</strong> {transcript.get("scenario_id", "N/A")}'
            html += f'</div>'

            # BP section
            html += '<h4>📋 Best Practice</h4>'
            html += '<div class="bp-section">'
            html += f'<div style="margin-bottom: 10px;"><strong>👤 고객 의도:</strong></div>'
            html += f'<div class="bp-message">{bp_intent}</div>'
            if initial_message:
                html += f'<div style="margin-top: 10px;"><strong>📝 시나리오 초기 메시지:</strong></div>'
                html += f'<div class="bp-message">{initial_message}</div>'
            html += '</div>'

            # Actual conversation
            html += '<h3>💬 실제 대화 내역</h3>'
            html += format_chat_bubble_html(transcript.get('turns', []))

            # Metrics
            metrics = case['metrics']
            html += '<h3>📈 메트릭</h3>'
            html += f'<div class="metric">턴 수: {metrics["num_turns"]}턴</div>'
            html += f'<div class="metric">응대 시간: {metrics["response_time"]:.1f}초</div>'
            html += f'<div class="metric">평균 응답 시간: {metrics["avg_response"]:.1f}초</div>'

            # QA scoring
            html += '<h3>📊 QA 채점</h3>'
            html += '<ul>'
            for reason in case['reasons']:
                html += f'<li>{reason}</li>'
            html += '</ul>'

            score_class = 'score'
            if case['score'] < 5:
                score_class += ' low'
            elif case['score'] < 8:
                score_class += ' medium'

            html += f'<p><strong>QA Score:</strong> <span class="{score_class}">{case["score"]:.1f}/10</span></p>'
            html += f'<p><strong>평가:</strong> {case["evaluation"]}</p>'

            html += '</div>'

    html += """
    </div>
</body>
</html>
"""

    return html


def generate_markdown_report(
    transcripts: list[dict],
    client_name: str,
    report_date: str | None = None,
) -> str:
    """Generate Markdown report.

    Args:
        transcripts: List of transcript dicts from transcripts.jsonl
        client_name: Client name for the report
        report_date: Report generation date (default: today)

    Returns:
        Markdown document as string
    """
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    md = f"""# {client_name} Best Practice QA 리포트

**생성일:** {report_date}
**총 케이스:** {len(transcripts)}개

---

## 📊 전체 요약

"""

    # Analyze cases
    cases_by_result = defaultdict(list)

    for transcript in transcripts:
        score, reasons, evaluation = calculate_qa_score(transcript)
        metrics = calculate_metrics(transcript)

        status = transcript.get('terminated_reason', transcript.get('status', 'unknown'))
        result_category = categorize_result(status, score)

        cases_by_result[result_category].append({
            'transcript': transcript,
            'score': score,
            'reasons': reasons,
            'evaluation': evaluation,
            'metrics': metrics
        })

    # Summary table
    total = len(transcripts)
    summary_order = ['🟢 성공', '🟡 부분 성공', '🟠 타임아웃', '🔴 오류']

    md += "| 결과 | 건수 | 비율 | 평균 QA Score |\n"
    md += "|------|------|------|---------------|\n"

    for result in summary_order:
        cases = cases_by_result[result]
        count = len(cases)
        ratio = (count / total * 100) if total > 0 else 0
        avg_score = sum(c['score'] for c in cases) / count if count > 0 else 0
        md += f"| {result} | {count}건 | {ratio:.1f}% | {avg_score:.1f}점 |\n"

    md += "\n---\n\n"

    # Cases by result category
    for result in summary_order:
        cases = cases_by_result[result]
        if not cases:
            continue

        md += f"# {result} ({len(cases)}건)\n\n"

        if result == '🟢 성공':
            md += "ALF가 고객 문의를 완전히 해결한 케이스\n\n"
        elif result == '🟡 부분 성공':
            md += "일부 정보 제공 또는 상담원 연결로 처리한 케이스\n\n"
        elif result == '🟠 타임아웃':
            md += "대화가 최대 턴 수에 도달하여 종료된 케이스\n\n"
        else:
            md += "오류가 발생한 케이스\n\n"

        for i, case in enumerate(cases, 1):
            transcript = case['transcript']

            bp_url = transcript.get('bp_url', '')
            bp_intent = transcript.get('bp_intent', '(의도 정보 없음)')
            bp_classification = transcript.get('bp_classification', '')
            initial_message = transcript.get('initial_message', '')

            md += f"## {i}. {bp_intent}\n\n"
            if bp_url:
                md += f"**Best Practice User Chat:** [{bp_url}]({bp_url})  \n"
            md += f"**분류:** {bp_classification}  \n"
            md += f"**Scenario ID:** {transcript.get('scenario_id', 'N/A')}  \n\n"

            # BP section
            md += "#### 📋 Best Practice\n\n"
            md += f"**👤 고객 의도:**\n> {bp_intent}\n\n"
            if initial_message:
                md += f"**📝 시나리오 초기 메시지:**\n> {initial_message}\n\n"

            md += "---\n\n"

            # Actual conversation
            md += "### 💬 실제 대화 내역\n\n"
            md += format_chat_bubble_markdown(transcript.get('turns', []))
            md += "\n"

            # Metrics
            metrics = case['metrics']
            md += "### 📈 메트릭\n\n"
            md += f"- **턴 수:** {metrics['num_turns']}턴\n"
            md += f"- **응대 시간:** {metrics['response_time']:.1f}초\n"
            md += f"- **평균 응답 시간:** {metrics['avg_response']:.1f}초\n\n"

            # QA scoring
            md += "### 📊 QA 채점\n\n"
            for reason in case['reasons']:
                md += f"- {reason}\n"
            md += f"\n**QA Score:** {case['score']:.1f}/10\n\n"
            md += f"**평가:** {case['evaluation']}\n\n"

            md += "---\n\n"

    return md


def generate_bp_qa_reports(
    transcripts_path: str | Path,
    output_dir: str | Path,
    client_name: str,
    report_date: str | None = None,
) -> tuple[Path, Path]:
    """Generate both HTML and Markdown QA reports.

    Args:
        transcripts_path: Path to transcripts.jsonl
        output_dir: Directory to save reports
        client_name: Client name for the report
        report_date: Report generation date (default: today)

    Returns:
        (html_path, markdown_path)
    """
    transcripts_path = Path(transcripts_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load transcripts
    transcripts = []
    with open(transcripts_path, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            # Handle both nested and flat structures
            if 'transcript' in data:
                transcript = data['transcript']
                # Merge top-level metadata
                for key in ['bp_url', 'bp_intent', 'bp_classification', 'layer', 'initial_message', 'scenario_id']:
                    if key in data:
                        transcript[key] = data[key]
                transcripts.append(transcript)
            else:
                transcripts.append(data)

    # Generate reports
    html_content = generate_html_report(transcripts, client_name, report_date)
    md_content = generate_markdown_report(transcripts, client_name, report_date)

    # Write files
    html_path = output_dir / f"QA_REPORT_{client_name.replace(' ', '_')}.html"
    md_path = output_dir / f"QA_REPORT_{client_name.replace(' ', '_')}.md"

    html_path.write_text(html_content, encoding='utf-8')
    md_path.write_text(md_content, encoding='utf-8')

    return html_path, md_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python -m tools.bp_qa_report_generator <transcripts.jsonl> <output_dir> <client_name>")
        sys.exit(1)

    transcripts_path = sys.argv[1]
    output_dir = sys.argv[2]
    client_name = sys.argv[3]

    html_path, md_path = generate_bp_qa_reports(transcripts_path, output_dir, client_name)

    print(f"✅ HTML 리포트 생성: {html_path}")
    print(f"✅ Markdown 리포트 생성: {md_path}")

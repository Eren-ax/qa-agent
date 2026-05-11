#!/usr/bin/env python3
"""
차란 Best Practice QA 분석 리포트 생성 스크립트
"""
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter

def calculate_qa_score(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    케이스별 QA Score 계산 (10점 만점)
    - 정확성: 5점
    - 완결성: 3점
    - 톤&매너: 2점
    """
    score_breakdown = {
        'accuracy': 0,  # 정확성 (5점)
        'completeness': 0,  # 완결성 (3점)
        'tone': 0,  # 톤&매너 (2점)
    }
    issues = []

    # 기본 정보 추출
    transcript = case.get('transcript', {}).get('transcript', {})
    terminated_reason = transcript.get('terminated_reason', '')
    turns = transcript.get('turns', [])

    # 모든 turn에서 ALF 메시지 수집
    alf_messages = []
    for turn in turns:
        alf_messages.extend(turn.get('alf_messages', []))

    bp_bot_response = case.get('best_practice', {}).get('bot_response', '')
    bp_agent_response = case.get('best_practice', {}).get('agent_response', '')

    # 치명적 오류 체크
    alf_text = ' '.join([msg.get('text', '') for msg in alf_messages])

    # 1. Error로 종료된 경우
    if terminated_reason == 'error':
        issues.append('❌ 대화가 오류로 종료됨 (error)')
        return {
            'total': 0,
            'breakdown': score_breakdown,
            'issues': issues,
            'summary': '치명적 오류: 대화 오류 종료'
        }

    # 2. 내부 토큰 노출 체크
    if '</thinking>' in alf_text or '<thinking>' in alf_text:
        issues.append('❌ 내부 토큰 노출 (</thinking>)')
        return {
            'total': 0,
            'breakdown': score_breakdown,
            'issues': issues,
            'summary': '치명적 결함: 내부 토큰 노출'
        }

    # 3. ALF 메시지가 없는 경우
    if not alf_messages:
        issues.append('❌ ALF 응답 없음')
        return {
            'total': 0,
            'breakdown': score_breakdown,
            'issues': issues,
            'summary': '응답 없음'
        }

    # 정상 케이스 분석
    # 정확성 평가 (5점)
    accuracy_score = 5

    # Best Practice와 비교
    bp_expected = bp_bot_response or bp_agent_response

    # 상담원 연결 제안 여부 체크
    agent_mention_keywords = ['상담원', '담당자', '연결', '전달', '도움 받으실', '문의하시']
    alf_mentions_agent = any(keyword in alf_text for keyword in agent_mention_keywords)

    if alf_mentions_agent and bp_bot_response and not any(keyword in bp_bot_response for keyword in agent_mention_keywords):
        issues.append('⚠️  BP는 봇 단독 해결인데 ALF는 상담원 연결 제안')
        accuracy_score -= 2

    # 정보 제공 여부 (키워드 기반 간단 체크)
    if len(alf_text.strip()) < 50:
        issues.append('⚠️  응답이 너무 짧음 (정보 부족 가능성)')
        accuracy_score -= 1

    # 완결성 평가 (3점)
    completeness_score = 3

    # BP 응답과 길이 비교
    if bp_expected:
        bp_length = len(bp_expected)
        alf_length = len(alf_text)

        if alf_length < bp_length * 0.5:
            issues.append('⚠️  BP 대비 응답 길이 부족 (정보 누락 가능성)')
            completeness_score -= 1

    # 불완전 종료 체크
    if terminated_reason == 'max_turns':
        issues.append('ℹ️  max_turns 도달 (대화 길어짐)')
        completeness_score -= 0.5

    # 톤&매너 평가 (2점)
    tone_score = 2

    # 친근한 표현 체크
    friendly_keywords = ['감사합니다', '도움', '확인', '안내', '문의', '요', '~']
    has_friendly = any(keyword in alf_text for keyword in friendly_keywords)

    if not has_friendly:
        issues.append('⚠️  친근한 톤 부족')
        tone_score -= 0.5

    # 최종 점수
    score_breakdown['accuracy'] = accuracy_score
    score_breakdown['completeness'] = completeness_score
    score_breakdown['tone'] = tone_score

    total_score = accuracy_score + completeness_score + tone_score

    summary = '정상'
    if total_score >= 9:
        summary = '✅ 우수'
    elif total_score >= 7:
        summary = '✓ 양호'
    elif total_score >= 5:
        summary = '△ 보통'
    elif total_score >= 3:
        summary = '▽ 미흡'
    else:
        summary = '✗ 불량'

    return {
        'total': round(total_score, 1),
        'breakdown': score_breakdown,
        'issues': issues,
        'summary': summary
    }

def generate_markdown_report(data: List[Dict[str, Any]], output_path: Path):
    """Markdown 리포트 생성"""

    # 각 케이스별 점수 계산
    case_results = []
    for idx, case in enumerate(data, 1):
        score_result = calculate_qa_score(case)
        case_results.append({
            'index': idx,
            'case': case,
            'score': score_result
        })

    # 통계 계산
    total_cases = len(case_results)
    avg_score = sum(r['score']['total'] for r in case_results) / total_cases if total_cases > 0 else 0

    score_distribution = Counter()
    for result in case_results:
        score = int(result['score']['total'])
        score_distribution[score] += 1

    # 우선순위 케이스 분리
    priority_cases = [r for r in case_results if r['case'].get('best_practice', {}).get('priority') == '⭐']
    normal_cases = [r for r in case_results if r['case'].get('best_practice', {}).get('priority') != '⭐']

    priority_avg = sum(r['score']['total'] for r in priority_cases) / len(priority_cases) if priority_cases else 0
    normal_avg = sum(r['score']['total'] for r in normal_cases) / len(normal_cases) if normal_cases else 0

    # Markdown 작성
    lines = [
        "# 차란 Best Practice QA 분석 리포트",
        "",
        f"**분석일:** 2026-05-07",
        f"**총 케이스 수:** {total_cases}",
        f"**평균 QA Score:** {avg_score:.1f} / 10.0",
        "",
        "---",
        "",
        "## 📊 전체 요약",
        "",
        "### Score 분포",
        "",
        "| Score | 케이스 수 |",
        "|-------|----------|",
    ]

    for score in range(10, -1, -1):
        count = score_distribution.get(score, 0)
        lines.append(f"| {score}점 | {count}건 |")

    lines.extend([
        "",
        "### 우선순위별 분석",
        "",
        f"- **⭐ 우선순위 케이스:** {len(priority_cases)}건 (평균 {priority_avg:.1f}점)",
        f"- **일반 케이스:** {len(normal_cases)}건 (평균 {normal_avg:.1f}점)",
        "",
        "### 주요 이슈 패턴",
        "",
    ])

    # 이슈 집계
    all_issues = []
    for result in case_results:
        all_issues.extend(result['score']['issues'])

    issue_counter = Counter(all_issues)
    top_issues = issue_counter.most_common(10)

    if top_issues:
        for issue, count in top_issues:
            lines.append(f"- **{issue}** ({count}건)")
    else:
        lines.append("- 특이사항 없음")

    lines.extend([
        "",
        "---",
        "",
        "## 📋 케이스별 상세 분석",
        "",
    ])

    # 케이스별 상세 분석
    for result in case_results:
        idx = result['index']
        case = result['case']
        score = result['score']

        bp = case.get('best_practice', {})
        priority = bp.get('priority', '')
        intent = bp.get('intent', 'N/A')
        bot_response = bp.get('bot_response', '')
        agent_response = bp.get('agent_response', '')

        transcript = case.get('transcript', {})
        userchat_url = transcript.get('bp_url', 'N/A')

        transcript_data = transcript.get('transcript', {})
        terminated_reason = transcript_data.get('terminated_reason', 'N/A')
        turns = transcript_data.get('turns', [])

        # 모든 turn에서 ALF 메시지 수집
        alf_messages = []
        for turn in turns:
            alf_messages.extend(turn.get('alf_messages', []))

        lines.extend([
            f"### {priority} 케이스 #{idx}",
            "",
            f"**UserChat URL:** {userchat_url}",
            "",
            f"**고객 의도:** {intent}",
            "",
            "**Best Practice 기대 응대:**",
            "",
        ])

        if bot_response:
            lines.extend([
                "```",
                "[봇 응답]",
                bot_response.strip(),
                "```",
                "",
            ])

        if agent_response:
            lines.extend([
                "```",
                "[상담원 응답]",
                agent_response.strip(),
                "```",
                "",
            ])

        lines.extend([
            "**ALF 실제 응대:**",
            "",
        ])

        if alf_messages:
            lines.append("```")
            for msg in alf_messages:
                content = msg.get('text', '').strip()
                if content:
                    lines.append(content)
                    lines.append("")
            lines.append("```")
        else:
            lines.append("```")
            lines.append("(응답 없음)")
            lines.append("```")

        lines.extend([
            "",
            "**비교 분석:**",
            "",
            f"- **정확성 (5점):** {score['breakdown']['accuracy']:.1f}점",
            f"- **완결성 (3점):** {score['breakdown']['completeness']:.1f}점",
            f"- **톤&매너 (2점):** {score['breakdown']['tone']:.1f}점",
            "",
            f"**QA Score:** {score['total']:.1f} / 10.0 ({score['summary']})",
            "",
        ])

        if score['issues']:
            lines.extend([
                "**문제점 및 개선사항:**",
                "",
            ])
            for issue in score['issues']:
                lines.append(f"- {issue}")
            lines.append("")

        lines.extend([
            f"**종료 사유:** {terminated_reason}",
            "",
            "---",
            "",
        ])

    # 파일 저장
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"✅ Markdown 리포트 생성 완료: {output_path}")

def generate_html_report(data: List[Dict[str, Any]], output_path: Path):
    """HTML 리포트 생성"""

    # 각 케이스별 점수 계산
    case_results = []
    for idx, case in enumerate(data, 1):
        score_result = calculate_qa_score(case)
        case_results.append({
            'index': idx,
            'case': case,
            'score': score_result
        })

    # 통계 계산
    total_cases = len(case_results)
    avg_score = sum(r['score']['total'] for r in case_results) / total_cases if total_cases > 0 else 0

    score_distribution = Counter()
    for result in case_results:
        score = int(result['score']['total'])
        score_distribution[score] += 1

    # 우선순위 케이스 분리
    priority_cases = [r for r in case_results if r['case'].get('best_practice', {}).get('priority') == '⭐']
    normal_cases = [r for r in case_results if r['case'].get('best_practice', {}).get('priority') != '⭐']

    priority_avg = sum(r['score']['total'] for r in priority_cases) / len(priority_cases) if priority_cases else 0
    normal_avg = sum(r['score']['total'] for r in normal_cases) / len(normal_cases) if normal_cases else 0

    # HTML 생성
    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='ko'>",
        "<head>",
        "<meta charset='UTF-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "<title>차란 Best Practice QA 분석 리포트</title>",
        "<style>",
        "body { font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }",
        "h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }",
        "h2 { color: #34495e; margin-top: 40px; border-left: 5px solid #3498db; padding-left: 15px; }",
        "h3 { color: #555; margin-top: 30px; }",
        ".summary { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; }",
        ".case { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
        ".score-badge { display: inline-block; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 0.9em; }",
        ".score-excellent { background: #27ae60; color: white; }",
        ".score-good { background: #2ecc71; color: white; }",
        ".score-fair { background: #f39c12; color: white; }",
        ".score-poor { background: #e74c3c; color: white; }",
        ".score-fail { background: #c0392b; color: white; }",
        ".bp-response { background: #ecf0f1; padding: 15px; border-left: 4px solid #3498db; margin: 10px 0; white-space: pre-wrap; }",
        ".alf-response { background: #e8f5e9; padding: 15px; border-left: 4px solid #27ae60; margin: 10px 0; white-space: pre-wrap; }",
        ".analysis { background: #fff9e6; padding: 15px; border-radius: 5px; margin: 10px 0; }",
        ".issue { color: #e74c3c; margin: 5px 0; }",
        ".priority-star { color: #f39c12; font-size: 1.2em; }",
        "table { width: 100%; border-collapse: collapse; margin: 20px 0; background: white; }",
        "th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }",
        "th { background: #3498db; color: white; }",
        "tr:hover { background: #f5f5f5; }",
        ".metadata { color: #7f8c8d; font-size: 0.9em; }",
        "</style>",
        "</head>",
        "<body>",
        "",
        "<h1>차란 Best Practice QA 분석 리포트</h1>",
        "",
        "<div class='summary'>",
        f"<p><strong>분석일:</strong> 2026-05-07</p>",
        f"<p><strong>총 케이스 수:</strong> {total_cases}</p>",
        f"<p><strong>평균 QA Score:</strong> {avg_score:.1f} / 10.0</p>",
        "</div>",
        "",
        "<h2>📊 전체 요약</h2>",
        "",
        "<h3>Score 분포</h3>",
        "<table>",
        "<tr><th>Score</th><th>케이스 수</th></tr>",
    ]

    for score in range(10, -1, -1):
        count = score_distribution.get(score, 0)
        html_parts.append(f"<tr><td>{score}점</td><td>{count}건</td></tr>")

    html_parts.extend([
        "</table>",
        "",
        "<h3>우선순위별 분석</h3>",
        "<ul>",
        f"<li><strong><span class='priority-star'>⭐</span> 우선순위 케이스:</strong> {len(priority_cases)}건 (평균 {priority_avg:.1f}점)</li>",
        f"<li><strong>일반 케이스:</strong> {len(normal_cases)}건 (평균 {normal_avg:.1f}점)</li>",
        "</ul>",
        "",
        "<h3>주요 이슈 패턴</h3>",
        "<ul>",
    ])

    # 이슈 집계
    all_issues = []
    for result in case_results:
        all_issues.extend(result['score']['issues'])

    issue_counter = Counter(all_issues)
    top_issues = issue_counter.most_common(10)

    if top_issues:
        for issue, count in top_issues:
            html_parts.append(f"<li><strong>{issue}</strong> ({count}건)</li>")
    else:
        html_parts.append("<li>특이사항 없음</li>")

    html_parts.extend([
        "</ul>",
        "",
        "<h2>📋 케이스별 상세 분석</h2>",
        "",
    ])

    # 케이스별 상세 분석
    for result in case_results:
        idx = result['index']
        case = result['case']
        score = result['score']

        bp = case.get('best_practice', {})
        priority = bp.get('priority', '')
        intent = bp.get('intent', 'N/A')
        bot_response = bp.get('bot_response', '')
        agent_response = bp.get('agent_response', '')

        transcript = case.get('transcript', {})
        userchat_url = transcript.get('bp_url', 'N/A')

        transcript_data = transcript.get('transcript', {})
        terminated_reason = transcript_data.get('terminated_reason', 'N/A')
        turns = transcript_data.get('turns', [])

        # 모든 turn에서 ALF 메시지 수집
        alf_messages = []
        for turn in turns:
            alf_messages.extend(turn.get('alf_messages', []))

        # Score 배지 클래스 결정
        score_class = 'score-fail'
        if score['total'] >= 9:
            score_class = 'score-excellent'
        elif score['total'] >= 7:
            score_class = 'score-good'
        elif score['total'] >= 5:
            score_class = 'score-fair'
        elif score['total'] >= 3:
            score_class = 'score-poor'

        priority_badge = f"<span class='priority-star'>{priority}</span> " if priority == '⭐' else ''

        html_parts.extend([
            "<div class='case'>",
            f"<h3>{priority_badge}케이스 #{idx}</h3>",
            "",
            f"<p class='metadata'><strong>UserChat URL:</strong> <a href='{userchat_url}' target='_blank'>{userchat_url}</a></p>",
            f"<p><strong>고객 의도:</strong> {intent}</p>",
            "",
            "<h4>Best Practice 기대 응대</h4>",
        ])

        if bot_response:
            html_parts.append(f"<div class='bp-response'><strong>[봇 응답]</strong><br>{bot_response.strip()}</div>")

        if agent_response:
            html_parts.append(f"<div class='bp-response'><strong>[상담원 응답]</strong><br>{agent_response.strip()}</div>")

        html_parts.append("<h4>ALF 실제 응대</h4>")

        if alf_messages:
            alf_text = '<br><br>'.join([msg.get('text', '').strip() for msg in alf_messages if msg.get('text', '').strip()])
            if alf_text:
                html_parts.append(f"<div class='alf-response'>{alf_text}</div>")
            else:
                html_parts.append("<div class='alf-response'>(응답 없음)</div>")
        else:
            html_parts.append("<div class='alf-response'>(응답 없음)</div>")

        html_parts.extend([
            "",
            "<div class='analysis'>",
            "<h4>비교 분석</h4>",
            "<ul>",
            f"<li><strong>정확성 (5점):</strong> {score['breakdown']['accuracy']:.1f}점</li>",
            f"<li><strong>완결성 (3점):</strong> {score['breakdown']['completeness']:.1f}점</li>",
            f"<li><strong>톤&매너 (2점):</strong> {score['breakdown']['tone']:.1f}점</li>",
            "</ul>",
            f"<p><strong>QA Score:</strong> <span class='score-badge {score_class}'>{score['total']:.1f} / 10.0</span> ({score['summary']})</p>",
        ])

        if score['issues']:
            html_parts.append("<h4>문제점 및 개선사항</h4>")
            html_parts.append("<ul>")
            for issue in score['issues']:
                html_parts.append(f"<li class='issue'>{issue}</li>")
            html_parts.append("</ul>")

        html_parts.extend([
            f"<p class='metadata'><strong>종료 사유:</strong> {terminated_reason}</p>",
            "</div>",
            "</div>",
            "",
        ])

    html_parts.extend([
        "</body>",
        "</html>",
    ])

    # 파일 저장
    output_path.write_text('\n'.join(html_parts), encoding='utf-8')
    print(f"✅ HTML 리포트 생성 완료: {output_path}")

def main():
    # 경로 설정
    input_file = Path('/Users/eren/qa-agent/storage/bp_test/merged_analysis.json')
    md_output = Path('/Users/eren/qa-agent/storage/bp_test/QA_REPORT_차란_Best_Practice.md')
    html_output = Path('/Users/eren/qa-agent/storage/bp_test/QA_REPORT_차란_Best_Practice.html')

    # 데이터 로드
    print(f"📂 데이터 로드 중: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"✓ 총 {len(data)}개 케이스 로드됨")

    # 리포트 생성
    print("\n📝 Markdown 리포트 생성 중...")
    generate_markdown_report(data, md_output)

    print("\n🌐 HTML 리포트 생성 중...")
    generate_html_report(data, html_output)

    print("\n✅ 모든 리포트 생성 완료!")
    print(f"   - Markdown: {md_output}")
    print(f"   - HTML: {html_output}")

if __name__ == '__main__':
    main()

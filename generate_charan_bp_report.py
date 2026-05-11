#!/usr/bin/env python3
"""
차란 Best Practice QA 리포트 생성 스크립트
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import re

# 경로 설정
TRANSCRIPTS_PATH = Path("/Users/eren/qa-agent/storage/bp_test_20260508_v2/transcripts.jsonl")
EXCEL_PATH = Path("/Users/eren/Downloads/차란 - Best Practice.xlsx")
OUTPUT_DIR = Path("/Users/eren/qa-agent/storage/bp_test_20260508_v2")

def load_transcripts():
    """transcripts.jsonl 로드 및 구조 정규화"""
    transcripts = []
    with open(TRANSCRIPTS_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            # transcript 객체 내부의 데이터를 최상위로 끌어올림
            if 'transcript' in data:
                transcript = data['transcript']
                # 추가 메타데이터 병합
                transcript['bp_url'] = data.get('bp_url', '')
                transcript['bp_intent'] = data.get('bp_intent', '')
                transcript['bp_classification'] = data.get('bp_classification', '')
                transcript['layer'] = data.get('layer', 0)
                transcript['initial_message'] = data.get('initial_message', '')
                transcripts.append(transcript)
            else:
                # 이미 평탄화된 구조
                transcripts.append(data)
    return transcripts

def load_excel():
    """Excel 로드 및 bp_url 키로 매핑"""
    df = pd.read_excel(EXCEL_PATH)
    # 링크 컬럼을 bp_url로 사용
    bp_dict = {}
    for _, row in df.iterrows():
        url = row.get('링크')
        if pd.notna(url):
            bp_dict[url] = {
                'priority': row.get('우선순위', ''),
                'category': row.get('유형', ''),
                'subcategory': row.get('세부유형', ''),
                'classification': row.get('분류', ''),
                'intent': row.get('고객 의도', ''),
                'bot_response': row.get('봇 응대', ''),
                'agent_response': row.get('상담원 응대', ''),
                'responder': row.get('답변자', ''),
                'score': row.get('스코어', 0),
                'reason': row.get('베스트 사유', ''),
                'priority_reason': row.get('우선순위 사유', '')
            }
    return bp_dict

def calculate_qa_score(transcript, bp_info):
    """QA 점수 계산 (10점 만점)"""
    score = 0
    reasons = []

    status = transcript.get('terminated_reason', transcript.get('status', 'unknown'))
    turns = transcript.get('turns', [])

    # 치명적 오류 체크
    if status == 'error':
        reasons.append("❌ 치명적 오류: error 상태로 종료")
        return 0, reasons, "치명적 오류로 0점 처리"

    # ALF 응답에서 </thinking> 노출 체크
    for turn in turns:
        alf_messages = turn.get('alf_messages', [])
        for msg in alf_messages:
            text = msg.get('text', '')
            if '</thinking>' in text:
                reasons.append("❌ 치명적 오류: </thinking> 태그 노출")
                return 0, reasons, "내부 사고 과정이 고객에게 노출됨"

    # 응답 없음 체크
    if len(turns) == 0:
        reasons.append("❌ 치명적 오류: ALF 응답 없음")
        return 0, reasons, "고객 문의에 대한 응답이 전혀 없음"

    # 모든 턴에 ALF 응답이 없는 경우
    has_alf_response = False
    for turn in turns:
        if turn.get('alf_messages', []):
            has_alf_response = True
            break

    if not has_alf_response:
        reasons.append("❌ 치명적 오류: ALF 응답 없음")
        return 0, reasons, "고객 문의에 대한 응답이 전혀 없음"

    # 정확성 (5점)
    bot_response = bp_info.get('bot_response', '')
    responder = bp_info.get('responder', '')

    if status == 'completed':
        if '로봇 단독' in responder or '로봇→상담원' in responder:
            score += 5
            reasons.append("✅ 정확성 5/5: BP와 동일하게 정보 제공")
        else:
            score += 4
            reasons.append("⚠️ 정확성 4/5: 정보는 제공했으나 BP와 약간 다름")
    elif status == 'escalated':
        if '상담원 단독' in responder:
            score += 5
            reasons.append("✅ 정확성 5/5: BP와 동일하게 상담원 연결")
        elif '로봇 단독' in responder:
            score += 3
            reasons.append("⚠️ 정확성 3/5: BP는 봇 단독인데 상담원 연결 제안")
        else:
            score += 4
            reasons.append("⚠️ 정확성 4/5: 상담원 연결은 했으나 BP와 차이")
    elif status == 'max_turns':
        score += 2
        reasons.append("⚠️ 정확성 2/5: 타임아웃으로 완결하지 못함")
    else:
        score += 1
        reasons.append("❌ 정확성 1/5: 알 수 없는 상태")

    # 완결성 (3점)
    if pd.notna(bot_response) and bot_response:
        # BP 봇 응대 내용과 비교
        if status == 'completed':
            score += 3
            reasons.append("✅ 완결성 3/3: 필요한 정보 모두 포함")
        elif status == 'escalated':
            score += 2
            reasons.append("⚠️ 완결성 2/3: 상담원 연결로 일부 정보 제공")
        else:
            score += 1
            reasons.append("⚠️ 완결성 1/3: 정보 제공이 불완전함")
    else:
        score += 2
        reasons.append("⚠️ 완결성 2/3: BP에 봇 응대 정보 없음")

    # 톤&매너 (2점)
    # 실제 대화 내용 분석 (간단히 부정적 표현 체크)
    alf_messages = []
    for turn in turns:
        for msg in turn.get('alf_messages', []):
            alf_messages.append(msg.get('text', ''))

    negative_patterns = ['죄송', '불편', '문제', '오류', '실패']

    if any(pattern in msg for msg in alf_messages for pattern in negative_patterns):
        # 부정적 표현이 있어도 문맥상 적절하면 만점
        score += 2
        reasons.append("✅ 톤&매너 2/2: 적절한 사과 및 친근한 톤")
    else:
        score += 2
        reasons.append("✅ 톤&매너 2/2: 친근하고 자연스러운 톤")

    # 종합 평가
    if score >= 9:
        evaluation = "🟢 우수: BP와 거의 동일한 수준의 응대"
    elif score >= 7:
        evaluation = "🟡 양호: 대부분 적절하나 일부 개선 필요"
    elif score >= 5:
        evaluation = "🟠 보통: 기본적인 응대는 하나 개선 여지 많음"
    else:
        evaluation = "🔴 미흡: 상당한 개선 필요"

    return score, reasons, evaluation

def format_chat_bubble_html(turns):
    """채널톡 스타일 말풍선 HTML 생성"""
    if not turns:
        return '<p style="color: #999;">대화 내역 없음</p>'

    html = '<div style="max-width: 800px; margin: 20px 0;">'

    for turn in turns:
        user_message = turn.get('user_message', '').strip()
        alf_messages = turn.get('alf_messages', [])

        # 고객 메시지
        if user_message:
            html += f'''
<div style="margin: 10px 0; text-align: left;">
    <div style="display: inline-block; max-width: 70%; background: white; border: 1px solid #e0e0e0; border-radius: 18px; padding: 12px 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
        <div style="font-size: 10px; color: #666; font-weight: 600; margin-bottom: 4px;">고객</div>
        <div style="line-height: 1.5; color: #333;">{user_message}</div>
    </div>
</div>
'''

        # ALF 메시지들 (하나의 말풍선에 모두 합침)
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

def format_chat_bubble_markdown(turns):
    """Markdown용 대화 내역 포맷"""
    if not turns:
        return '*대화 내역 없음*\n'

    md = ''

    for turn in turns:
        user_message = turn.get('user_message', '').strip()
        alf_messages = turn.get('alf_messages', [])

        # 고객 메시지
        if user_message:
            md += f'\n**고객:** {user_message}\n'

        # ALF 메시지들
        if alf_messages:
            md += '\n**ALF:**\n'
            for msg in alf_messages:
                text = msg.get('text', '').strip()
                if text:
                    md += f'> {text}\n\n'

    return md

def categorize_result(status, score):
    """결과 분류"""
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

def calculate_metrics(transcript):
    """메트릭 계산"""
    turns = transcript.get('turns', [])
    started_at = transcript.get('started_at')
    ended_at = transcript.get('ended_at')

    num_turns = len(turns)

    # 응대 시간 계산
    if started_at and ended_at:
        try:
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
            response_time = (end - start).total_seconds()
        except:
            response_time = 0
    else:
        response_time = 0

    # 평균 응답 시간 (간단히 총 시간 / 턴 수)
    avg_response = response_time / num_turns if num_turns > 0 else 0

    return {
        'num_turns': num_turns,
        'response_time': response_time,
        'avg_response': avg_response
    }

def generate_markdown_report(transcripts, bp_dict):
    """Markdown 리포트 생성"""
    md = f"""# 차란 Best Practice QA 리포트 (리뉴얼 채널)

**생성일:** 2026-05-08
**총 케이스:** {len(transcripts)}개

---

## 📊 전체 요약

"""

    # 케이스별 분석
    cases_by_result = defaultdict(list)

    for transcript in transcripts:
        bp_url = transcript.get('bp_url', '')
        bp_info = bp_dict.get(bp_url, {})

        score, reasons, evaluation = calculate_qa_score(transcript, bp_info)
        metrics = calculate_metrics(transcript)

        status = transcript.get('terminated_reason', transcript.get('status', 'unknown'))
        result_category = categorize_result(status, score)

        cases_by_result[result_category].append({
            'transcript': transcript,
            'bp_info': bp_info,
            'score': score,
            'reasons': reasons,
            'evaluation': evaluation,
            'metrics': metrics
        })

    # 요약 테이블
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

    # 각 결과 그룹별로 케이스 나열
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
            bp_info = case['bp_info']
            bp_url = transcript.get('bp_url', '')

            intent = bp_info.get('intent', '(의도 정보 없음)')
            category = bp_info.get('category', '')
            subcategory = bp_info.get('subcategory', '')
            classification = bp_info.get('classification', '')

            md += f"## {i}. {intent}\n\n"
            md += f"**Best Practice User Chat:** [{bp_url}]({bp_url})  \n"
            md += f"**카테고리:** {category} > {subcategory}  \n"
            md += f"**분류:** {classification}  \n\n"

            # BP 유저챗 섹션 추가
            md += "#### 📋 Best Practice 유저챗\n\n"
            md += f"**👤 고객:**\n> {intent}\n\n"

            bot_response = bp_info.get('bot_response', '')
            agent_response = bp_info.get('agent_response', '')

            if pd.notna(bot_response) and bot_response:
                md += f"**🎯 BP 봇:**\n> {bot_response}\n\n"

            if pd.notna(agent_response) and agent_response:
                md += f"**👨‍💼 BP 상담원:**\n> {agent_response}\n\n"

            if not (pd.notna(bot_response) and bot_response) and not (pd.notna(agent_response) and agent_response):
                md += "*BP 응대 정보 없음*\n\n"

            md += "---\n\n"

            # 대화 내역
            md += "### 💬 실제 대화 내역\n\n"
            md += format_chat_bubble_markdown(transcript.get('turns', []))
            md += "\n"

            # 메트릭
            metrics = case['metrics']
            md += "### 📈 메트릭\n\n"
            md += f"- **턴 수:** {metrics['num_turns']}턴\n"
            md += f"- **응대 시간:** {metrics['response_time']:.1f}초\n"
            md += f"- **평균 응답 시간:** {metrics['avg_response']:.1f}초\n\n"

            # QA 채점
            md += "### 📊 QA 채점\n\n"
            for reason in case['reasons']:
                md += f"- {reason}\n"
            md += f"\n**QA Score:** {case['score']}/10\n\n"
            md += f"**평가:** {case['evaluation']}\n\n"

            md += "---\n\n"

    return md

def generate_html_report(transcripts, bp_dict):
    """HTML 리포트 생성"""
    html = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>차란 Best Practice QA 리포트</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        h1 { font-size: 32px; color: #1976d2; margin-bottom: 10px; }
        .meta { color: #666; margin-bottom: 30px; font-size: 14px; }
        h2 {
            font-size: 28px;
            margin: 40px 0 20px 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 8px;
        }
        h3 {
            font-size: 20px;
            margin: 30px 0 15px 0;
            padding: 15px;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            border-radius: 6px;
        }
        h4 { font-size: 16px; margin: 20px 0 10px 0; color: #1976d2; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f5f5f5; font-weight: 600; }
        .case {
            background: #fafafa;
            border-left: 4px solid #1976d2;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .case-header { font-size: 18px; font-weight: 600; margin-bottom: 10px; color: #1976d2; }
        .case-meta { font-size: 14px; color: #666; margin-bottom: 15px; }
        .metric { display: inline-block; background: #e3f2fd; padding: 8px 12px; margin: 5px; border-radius: 4px; font-size: 14px; }
        .score { font-size: 24px; font-weight: 700; color: #4caf50; }
        .score.low { color: #f44336; }
        .score.medium { color: #ff9800; }
        ul { margin: 10px 0 10px 20px; }
        li { margin: 5px 0; }
        .section-success { border-left-color: #4caf50; }
        .section-partial { border-left-color: #ff9800; }
        .section-timeout { border-left-color: #ff9800; }
        .section-error { border-left-color: #f44336; }
        a { color: #1976d2; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>차란 Best Practice QA 리포트 (리뉴얼 채널)</h1>
        <div class="meta">
            <strong>생성일:</strong> 2026-05-08<br>
            <strong>총 케이스:</strong> """ + str(len(transcripts)) + """개
        </div>

        <h2>📊 전체 요약</h2>
"""

    # 케이스별 분석
    cases_by_result = defaultdict(list)

    for transcript in transcripts:
        bp_url = transcript.get('bp_url', '')
        bp_info = bp_dict.get(bp_url, {})

        score, reasons, evaluation = calculate_qa_score(transcript, bp_info)
        metrics = calculate_metrics(transcript)

        status = transcript.get('terminated_reason', transcript.get('status', 'unknown'))
        result_category = categorize_result(status, score)

        cases_by_result[result_category].append({
            'transcript': transcript,
            'bp_info': bp_info,
            'score': score,
            'reasons': reasons,
            'evaluation': evaluation,
            'metrics': metrics
        })

    # 요약 테이블
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

    # 각 결과 그룹별로 케이스 나열
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
            bp_info = case['bp_info']
            bp_url = transcript.get('bp_url', '')

            intent = bp_info.get('intent', '(의도 정보 없음)')
            category = bp_info.get('category', '')
            subcategory = bp_info.get('subcategory', '')
            classification = bp_info.get('classification', '')

            section_class = section_classes.get(result, '')

            html += f'<div class="case {section_class}">'
            html += f'<div class="case-header">{i}. {intent}</div>'
            html += f'<div class="case-meta">'
            html += f'<strong>Best Practice User Chat:</strong> <a href="{bp_url}" target="_blank">{bp_url}</a><br>'
            html += f'<strong>카테고리:</strong> {category} &gt; {subcategory}<br>'
            html += f'<strong>분류:</strong> {classification}'
            html += f'</div>'

            # BP 유저챗 섹션 추가
            html += '<h4>📋 Best Practice 유저챗</h4>'
            html += '<div style="background: #f9f9f9; padding: 15px; border-radius: 8px; margin: 15px 0;">'
            html += f'<div style="margin-bottom: 10px;"><strong>👤 고객:</strong><br><blockquote style="margin: 5px 0; padding: 8px; border-left: 3px solid #ccc; background: white;">{intent}</blockquote></div>'

            bot_response = bp_info.get('bot_response', '')
            agent_response = bp_info.get('agent_response', '')

            if pd.notna(bot_response) and bot_response:
                bot_html = bot_response.replace('\n', '<br>')
                html += f'<div style="margin-bottom: 10px;"><strong>🎯 BP 봇:</strong><br><blockquote style="margin: 5px 0; padding: 8px; border-left: 3px solid #4caf50; background: white;">{bot_html}</blockquote></div>'

            if pd.notna(agent_response) and agent_response:
                agent_html = agent_response.replace('\n', '<br>')
                html += f'<div style="margin-bottom: 10px;"><strong>👨‍💼 BP 상담원:</strong><br><blockquote style="margin: 5px 0; padding: 8px; border-left: 3px solid #2196f3; background: white;">{agent_html}</blockquote></div>'

            if not (pd.notna(bot_response) and bot_response) and not (pd.notna(agent_response) and agent_response):
                html += '<div style="color: #999; font-style: italic;">BP 응대 정보 없음</div>'

            html += '</div>'

            # 대화 내역
            html += '<h3>💬 실제 대화 내역</h3>'
            html += format_chat_bubble_html(transcript.get('turns', []))

            # 메트릭
            metrics = case['metrics']
            html += '<h3>📈 메트릭</h3>'
            html += f'<div class="metric">턴 수: {metrics["num_turns"]}턴</div>'
            html += f'<div class="metric">응대 시간: {metrics["response_time"]:.1f}초</div>'
            html += f'<div class="metric">평균 응답 시간: {metrics["avg_response"]:.1f}초</div>'

            # QA 채점
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

            html += f'<p><strong>QA Score:</strong> <span class="{score_class}">{case["score"]}/10</span></p>'
            html += f'<p><strong>평가:</strong> {case["evaluation"]}</p>'

            html += '</div>'

    html += """
    </div>
</body>
</html>
"""

    return html

def main():
    """메인 실행"""
    print("📊 차란 Best Practice QA 리포트 생성 시작...")

    # 데이터 로드
    print("📂 데이터 로드 중...")
    transcripts = load_transcripts()
    bp_dict = load_excel()

    print(f"✅ Transcripts: {len(transcripts)}개")
    print(f"✅ BP 데이터: {len(bp_dict)}개")

    # 리포트 생성
    print("\n📝 Markdown 리포트 생성 중...")
    markdown_report = generate_markdown_report(transcripts, bp_dict)

    print("📝 HTML 리포트 생성 중...")
    html_report = generate_html_report(transcripts, bp_dict)

    # 파일 저장
    md_path = OUTPUT_DIR / "QA_REPORT_차란_리뉴얼_v2.md"
    html_path = OUTPUT_DIR / "QA_REPORT_차란_리뉴얼_v2.html"

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(markdown_report)
    print(f"✅ Markdown 저장: {md_path}")

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_report)
    print(f"✅ HTML 저장: {html_path}")

    print("\n🎉 리포트 생성 완료!")

if __name__ == '__main__':
    main()
